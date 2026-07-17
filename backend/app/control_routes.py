"""Thin adapter routes for the Control tab. Zero control logic here —
argument parsing + core.control.session.ControlSession calls + JSON only.
All actual state/behaviour lives in core/ (see core/README.md's split rule).
"""

import json
import logging
import time
from dataclasses import asdict

from flask import jsonify, request

from core.control.session import ControlSession

log = logging.getLogger(__name__)

# Single ControlSession instance for the whole backend process — the Control
# tab's one stateful orchestrator.
control_session = ControlSession(hardware_source="sim")

# Telemetry websocket push rate (spec: ~10 Hz batches).
_WS_PUSH_INTERVAL_S = 0.1


def register(app, sock) -> None:
    @app.route("/api/control/status", methods=["GET"])
    def control_status():
        return jsonify(control_session.status())

    @app.route("/api/control/start", methods=["POST"])
    def control_start():
        body = request.get_json(silent=True) or {}
        mode = body.get("mode")
        target = body.get("target")
        if mode is None or target is None:
            return jsonify({"error": "mode and target required"}), 400
        try:
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
