"""Thin adapter routes for the Control tab (and, Session 3, the Profiles tab).
Zero control logic here — argument parsing + core.control.session.ControlSession
/ core.profiles calls + JSON only. All actual state/behaviour lives in core/
(see core/README.md's split rule).
"""

import json
import logging
import time
from dataclasses import asdict

from flask import jsonify, request

from core.cable import CableState, ExerciseMode
from core.control.modes import MODES_BY_NAME
from core.control.session import ControlSession, DEFAULT_HARDWARE_FACTORIES
from core.hardware.odrive_hw import OdriveHardware
from core.profiles import PROFILE_REGISTRY, OverloadWrapper, Phase

from . import device_manager

log = logging.getLogger(__name__)


def _real_hardware_factory() -> OdriveHardware:
    """Built here (not core/) so OdriveHardware reuses device_manager's
    already-cached USB connection/lock instead of opening a second,
    independent one — see core/hardware/odrive_hw.py's module docstring and
    docs/decisions.md (22 July 2026) for why that mattered live."""
    return OdriveHardware(
        find_any_fn=lambda timeout: device_manager.get_shared_handle(timeout=timeout),
        lock_provider=device_manager.get_shared_io_lock,
    )


# Exercise tab (Layer A): home/max/k live here, not inside ExerciseMode --
# ControlSession.stop() destroys the mode handler on every stop(), but
# "Reset Position" (exercise_tab_build_spec_layerA.md §3.5) must work while
# idle, against a home reference from a *previous* run. Same process
# lifetime as control_session below; constructed once. See docs/decisions.md
# ("Exercise tab Layer A" entry) for the full reasoning.
cable_state = CableState()

# Single ControlSession instance for the whole backend process — the Control
# tab's one stateful orchestrator. Defaults to real hardware: this project only
# ever runs against the real board now that it's wired up (the sim/real
# switcher was removed from the GUI, though set_hardware_source()/the
# /api/control/hardware-source route are still there for scripting/tests).
control_session = ControlSession(
    hardware_source="real",
    hardware_factories={**DEFAULT_HARDWARE_FACTORIES, "real": _real_hardware_factory},
    mode_factories={**MODES_BY_NAME, "exercise": lambda: ExerciseMode(cable_state)},
)

# Telemetry websocket push rate (spec: ~10 Hz batches).
_WS_PUSH_INTERVAL_S = 0.1


def _build_profile_target(body: dict):
    """Builds the ResistanceProfile instance for a `mode: "profile"` start
    request: {profile: <name>, params: {...}, overload: {enabled, ratio,
    target_phase} | null}. Composes OverloadWrapper server-side when
    requested (spec §7) — the frontend never constructs a wrapper directly."""
    profile_name = body.get("profile")
    factory = PROFILE_REGISTRY.get(profile_name)
    if factory is None:
        raise ValueError(f"Unknown profile: {profile_name!r} (expected one of {list(PROFILE_REGISTRY)})")
    if factory.IS_WRAPPER:
        raise ValueError(f"{profile_name!r} is a wrapper, not a selectable base profile")

    params = body.get("params") or {}
    profile = factory(**params)

    overload = body.get("overload")
    if overload and overload.get("enabled"):
        wrapper_kwargs = {"wrapped": profile, "target_phase": Phase(overload.get("target_phase", "eccentric"))}
        if overload.get("ratio") is not None:
            wrapper_kwargs["ratio"] = overload["ratio"]
        profile = OverloadWrapper(**wrapper_kwargs)

    return profile


def register(app, sock) -> None:
    @app.route("/api/profiles", methods=["GET"])
    def list_profiles():
        """Registry-driven profile list for the Profiles tab picker — name,
        parameter schema (label/value/default/min/max per parameter, from
        each profile's own describe()), and whether it's a wrapper. Never
        hardcoded in the frontend."""
        return jsonify([factory().describe() for factory in PROFILE_REGISTRY.values()])

    @app.route("/api/control/status", methods=["GET"])
    def control_status():
        return jsonify(control_session.status())

    @app.route("/api/control/start", methods=["POST"])
    def control_start():
        body = request.get_json(silent=True) or {}
        mode = body.get("mode")
        if mode is None:
            return jsonify({"error": "mode required"}), 400
        try:
            if mode == "profile":
                target = _build_profile_target(body)
            else:
                target = body.get("target")
                if target is None:
                    return jsonify({"error": "mode and target required"}), 400
            control_session.start(mode, target)
            return jsonify(control_session.status())
        except Exception as e:
            log.exception("control/start failed")
            return jsonify({"error": str(e)}), 400

    @app.route("/api/control/target", methods=["POST"])
    def control_target():
        body = request.get_json(silent=True) or {}
        value = body.get("value")
        if value is None:
            return jsonify({"error": "value required"}), 400
        try:
            control_session.set_target(value)
            return jsonify(control_session.status())
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/control/stop", methods=["POST"])
    def control_stop():
        control_session.stop()
        return jsonify(control_session.status())

    @app.route("/api/control/hardware-source", methods=["GET", "POST"])
    def control_hardware_source():
        if request.method == "GET":
            return jsonify({"hardware_source": control_session.get_hardware_source()})
        body = request.get_json(silent=True) or {}
        source = body.get("hardware_source")
        if not source:
            return jsonify({"error": "hardware_source required"}), 400
        try:
            control_session.set_hardware_source(source)
            return jsonify({"hardware_source": control_session.get_hardware_source()})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/control/telemetry", methods=["GET"])
    def control_telemetry_rest():
        """REST fallback for the /ws/control-telemetry stream."""
        since = request.args.get("since", type=float)
        samples = control_session.samples_since(since)
        return jsonify([asdict(s) for s in samples])

    @sock.route("/ws/control-telemetry")
    def ws_control_telemetry(ws):
        try:
            _control_telemetry_session(ws)
        except Exception as e:
            try:
                ws.send(json.dumps({"error": str(e)}))
            except Exception:
                pass


def _control_telemetry_session(ws) -> None:
    """Push status + new ring-buffer samples at ~10 Hz. One-way stream (the
    Control tab issues commands over the REST routes above, not this
    socket) — receive() doubles as the pacing sleep AND the close check.

    simple_websocket runs a background thread per connection that processes
    incoming frames (including the client's close handshake) independently
    of this loop. A non-blocking receive() + a separate time.sleep() leaves a
    window, up to the whole sleep duration, where that background thread can
    detect the client's close and start writing its own close-ack to the
    socket while this thread is still asleep and about to call send() into
    the same connection — two threads writing the same socket unsynchronized
    can interleave bytes, which surfaces client-side as a confusing "Invalid
    frame header" WS error instead of a clean close. Blocking in receive()
    for the pacing interval instead collapses that window to a couple of
    Python statements: receive() is woken immediately when the background
    thread signals the close (before it starts sending), so the close is
    almost always observed and this loop breaks before it ever calls send()
    again. The Control tab opens/closes this socket on every tab switch (far
    more often than the per-device telemetry socket), so this window is hit
    often here, not just theoretically. send() is still guarded as a
    backstop for whatever race remains.
    """
    last_t = None
    while True:
        try:
            ws.receive(timeout=_WS_PUSH_INTERVAL_S)
        except Exception:
            break

        samples = control_session.samples_since(last_t)
        if samples:
            last_t = samples[-1].t
        try:
            ws.send(json.dumps({
                "timestamp": int(time.time() * 1000),
                "status": control_session.status(),
                "samples": [asdict(s) for s in samples],
            }))
        except Exception:
            break
