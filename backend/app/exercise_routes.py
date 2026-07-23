"""Thin adapter routes for the Exercise tab (Layer A — cable-attached
positioning & safety, exercise_tab_build_spec_layerA.md). Zero control logic
here, same split as control_routes.py: argument parsing + core.cable /
core.control.session.ControlSession calls + JSON only.

Mirrors control_routes.py's structure (spec §2.3) rather than extending it —
the Exercise tab's action set (home/abort/calibrate/move/reset) doesn't fit
the existing {mode, target} shape control_routes.py's routes were built
around. Shares the same `control_session` singleton (so the `find_any()`
choke point stays a single call site) and the module-level `cable_state`
from control_routes.py.

REST polling only, no websocket (spec §2.3) — matches the precedent already
established for Control/Profiles (see frontend/src/hooks/useControlTelemetry
.js's header comment on why the websocket route was abandoned there).
"""

import logging

from flask import jsonify, request

from config import board_constants
from core.cable.geometry import calibrate_k

from . import control_routes

log = logging.getLogger(__name__)


def _cable_status_dict() -> dict:
    cs = control_routes.cable_state
    latest = control_routes.control_session.status().get("latest_sample")
    cable_position_turns = (latest["position"] - cs.home_turns) if (latest and cs.is_homed) else None
    return {
        "is_homed": cs.is_homed,
        "has_max": cs.has_max,
        "home_turns": cs.home_turns,
        "max_turns": cs.max_turns,
        "marked_max_turns": cs.marked_max_turns,
        "homing_in_progress": cs.homing_in_progress,
        "max_calibration_in_progress": cs.max_calibration_in_progress,
        "last_homing_fault": cs.last_homing_fault,
        "k": cs.k,
        "r0": cs.r0,
        "homing_current_threshold_a": cs.homing_current_threshold_a,
        "homing_velocity_turns_s": cs.homing_velocity_turns_s,
        "homing_current_limit_a": cs.homing_current_limit_a,
        "calib_hold_force_n": cs.calib_hold_force_n,
        # Zeroed-at-home position, distinct from the raw absolute encoder
        # reading in latest_sample.position -- requested 23 July 2026 (the
        # raw encoder value is whatever arbitrary number it was at power-on,
        # not 0 at home, which was confusing to read live).
        "cable_position_turns": cable_position_turns,
    }


def _exercise_action_running() -> bool:
    status = control_routes.control_session.status()
    return bool(status["running"] and status["mode"] == "exercise")


def register(app) -> None:
    @app.route("/api/exercise/status", methods=["GET"])
    def exercise_status():
        return jsonify({
            "control": control_routes.control_session.status(),
            "cable": _cable_status_dict(),
        })

    @app.route("/api/exercise/start", methods=["POST"])
    def exercise_start():
        """Arms the Exercise session -- zero motion (spec §4 item 1: motion
        never starts from session start). Homing/moves only ever begin from
        a later, explicit action route below."""
        try:
            control_routes.control_session.start(mode="exercise", target={"action": "arm"})
            return jsonify({"control": control_routes.control_session.status(), "cable": _cable_status_dict()})
        except Exception as e:
            log.exception("exercise/start failed")
            return jsonify({"error": str(e)}), 400

    def _dispatch_action(action: str, extra_fields: dict = None):
        try:
            value = {"action": action, **(extra_fields or {})}
            control_routes.control_session.set_target(value)
            return jsonify({"control": control_routes.control_session.status(), "cable": _cable_status_dict()})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/exercise/home", methods=["POST"])
    def exercise_home():
        return _dispatch_action("home")

    @app.route("/api/exercise/abort_homing", methods=["POST"])
    def exercise_abort_homing():
        return _dispatch_action("abort_homing")

    @app.route("/api/exercise/start_max_calibration", methods=["POST"])
    def exercise_start_max_calibration():
        return _dispatch_action("start_max_calibration")

    @app.route("/api/exercise/confirm_max", methods=["POST"])
    def exercise_confirm_max():
        return _dispatch_action("confirm_max")

    @app.route("/api/exercise/cancel_max_calibration", methods=["POST"])
    def exercise_cancel_max_calibration():
        return _dispatch_action("cancel_max_calibration")

    @app.route("/api/exercise/move", methods=["POST"])
    def exercise_move():
        body = request.get_json(silent=True) or {}
        target_length_m = body.get("target_length_m")
        if target_length_m is None:
            return jsonify({"error": "target_length_m required"}), 400
        extra = {"target_length_m": target_length_m}
        if body.get("move_velocity_turns_s") is not None:
            extra["move_velocity_turns_s"] = body["move_velocity_turns_s"]
        if body.get("accel_decel_turns_s2") is not None:
            extra["accel_decel_turns_s2"] = body["accel_decel_turns_s2"]
        return _dispatch_action("move", extra)

    @app.route("/api/exercise/stop", methods=["POST"])
    def exercise_stop():
        """The always-available Stop (spec §4 item 7) -- a thin alias for
        the same control_session.stop() every other tab's Stop already
        calls, so nothing new needs to be trusted here."""
        control_routes.control_session.stop()
        return jsonify({"control": control_routes.control_session.status(), "cable": _cable_status_dict()})

    @app.route("/api/exercise/reset_position", methods=["POST"])
    def exercise_reset_position():
        """Manual position reset (spec §3.5) -- confirmation is the
        frontend's job (a confirm dialog, same pattern as the existing
        erase-config modal); idle-gating is enforced here."""
        if _exercise_action_running():
            return jsonify({"error": "Cannot reset while an Exercise session is running -- stop it first"}), 400
        control_routes.cable_state.reset()
        return jsonify({"cable": _cable_status_dict()})

    @app.route("/api/exercise/calibrate_k", methods=["POST"])
    def exercise_calibrate_k():
        """Spool correction-factor calibration (spec §3.3) -- indirect UX:
        the user reels out to some position (via /api/exercise/move or by
        hand under an active session) and physically measures the actual
        cable length; this route back-computes k from that one measurement.
        Never takes a raw k from the caller."""
        body = request.get_json(silent=True) or {}
        measured_length_m = body.get("measured_length_m")
        if measured_length_m is None:
            return jsonify({"error": "measured_length_m required"}), 400

        cs = control_routes.cable_state
        if not cs.is_homed:
            return jsonify({"error": "Cable is not homed -- home before calibrating"}), 400

        status = control_routes.control_session.status()
        latest = status.get("latest_sample")
        if not latest or status.get("mode") != "exercise":
            return jsonify({"error": "No live Exercise telemetry available -- start an Exercise session first"}), 400

        theta_m_turns = latest["position"] - cs.home_turns
        try:
            k = calibrate_k(
                theta_m_turns,
                float(measured_length_m),
                cs.r0,
                min_theta_m_rad=board_constants.SPOOL_CALIBRATION_MIN_THETA_M_RAD,
                k_bounds=board_constants.SPOOL_CORRECTION_K_BOUNDS,
            )
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400

        cs.set_k(k)
        return jsonify({"cable": _cable_status_dict()})

    @app.route("/api/exercise/update_homing_settings", methods=["POST"])
    def exercise_update_homing_settings():
        """Live-adjustable homing tuning (requested 23 July 2026, after the
        first live-hardware session) -- current detection threshold,
        reel-in velocity, and the reduced current limit applied during
        homing. Any subset; validated together (limit must exceed
        threshold, stay under the board's operating current limit) and
        persisted the same way spool correction factor k already is.
        Takes effect on the *next* Home action, not retroactively on one
        already in progress."""
        body = request.get_json(silent=True) or {}
        try:
            control_routes.cable_state.set_homing_settings(
                current_threshold_a=body.get("current_threshold_a"),
                velocity_turns_s=body.get("velocity_turns_s"),
                current_limit_a=body.get("current_limit_a"),
            )
            return jsonify({"cable": _cable_status_dict()})
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/exercise/update_spool_radius", methods=["POST"])
    def exercise_update_spool_radius():
        """Live-adjustable spool radius (requested 23 July 2026) -- affects
        every force<->torque and cable-velocity conversion from this point
        on (core/profiles/units.py, core/cable/force_mode.py), not just
        display. Prefer the Advanced Spool Calibration flow
        (/api/exercise/calibrate_k) for the wrap-growth correction factor;
        this route is for the base radius itself."""
        body = request.get_json(silent=True) or {}
        r0 = body.get("r0")
        if r0 is None:
            return jsonify({"error": "r0 required"}), 400
        try:
            control_routes.cable_state.set_r0(float(r0))
            return jsonify({"cable": _cable_status_dict()})
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/exercise/update_calib_hold_force", methods=["POST"])
    def exercise_update_calib_hold_force():
        """Live-adjustable max-extension calibration hold force (requested
        23 July 2026) -- was a fixed CALIB_HOLD_FORCE_N constant (spec §3.2:
        must stay trivially overcome by hand; this route doesn't relax that
        expectation, just makes the exact value adjustable)."""
        body = request.get_json(silent=True) or {}
        force_n = body.get("force_n")
        if force_n is None:
            return jsonify({"error": "force_n required"}), 400
        try:
            control_routes.cable_state.set_calib_hold_force(float(force_n))
            return jsonify({"cable": _cable_status_dict()})
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400
