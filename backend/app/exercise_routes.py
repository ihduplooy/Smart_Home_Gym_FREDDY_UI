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
    # Max-extension length in meters, from home -- requested 24 July 2026 so
    # the header status card can show the actual calibrated value instead of
    # just "set" (the raw turns figure alone isn't meaningful to read live).
    max_extension_length_m = (
        cs.spool_geometry.length_from_turns_delta(cs.max_turns - cs.home_turns) if (cs.is_homed and cs.has_max) else None
    )
    return {
        "is_homed": cs.is_homed,
        "has_max": cs.has_max,
        "home_turns": cs.home_turns,
        "max_turns": cs.max_turns,
        "marked_max_turns": cs.marked_max_turns,
        "max_extension_length_m": max_extension_length_m,
        "homing_in_progress": cs.homing_in_progress,
        "max_calibration_in_progress": cs.max_calibration_in_progress,
        "last_homing_fault": cs.last_homing_fault,
        "k": cs.k,
        "r0": cs.r0,
        # Developer visibility (train tab calibration overhaul item 6): the
        # active spool model, its equations (numbers substituted in), the
        # piecewise segments (if any), the saved/pending experimental
        # growth-calibration points, and the k bounds currently enforced --
        # everything needed to verify/troubleshoot the calibration without
        # reading source.
        "spool_model": {
            "type": cs.spool_geometry.active_model,
            "r0": cs.r0,
            "k": cs.k,
            "k_bounds": list(board_constants.SPOOL_CORRECTION_K_BOUNDS),
            "min_effective_radius_m": board_constants.SPOOL_MIN_EFFECTIVE_RADIUS_M,
            "growth_points": [{"turns_from_home": t, "length_m": length_m} for t, length_m in cs.spool_growth_points],
            "pending_growth_points": [
                {"turns_from_home": t, "length_m": length_m} for t, length_m in cs.pending_growth_points
            ],
            "segments": cs.spool_geometry.segments_summary(),
            "equations": cs.spool_geometry.describe(),
            "r_eff_at_current_position_m": (
                cs.spool_geometry.r_eff_at_turns_delta(cable_position_turns) if cable_position_turns is not None else None
            ),
            "spool_growth_calibration_in_progress": cs.spool_growth_calibration_in_progress,
        },
        "homing_current_threshold_a": cs.homing_current_threshold_a,
        "homing_velocity_turns_s": cs.homing_velocity_turns_s,
        "homing_current_limit_a": cs.homing_current_limit_a,
        "calib_hold_force_n": cs.calib_hold_force_n,
        # Force/safety "feel" settings -- live-adjustable via
        # update_force_settings below, surfaced here the same way the
        # homing settings already are.
        "letgo_velocity_turns_s": cs.letgo_velocity_turns_s,
        "letgo_debounce_samples": cs.letgo_debounce_samples,
        "hold_duration_s": cs.hold_duration_s,
        "force_ramp_in_s": cs.force_ramp_in_s,
        "force_ramp_out_s": cs.force_ramp_out_s,
        "isokinetic_governor_gain": cs.isokinetic_governor_gain,
        "isokinetic_velocity_filter_alpha": cs.isokinetic_velocity_filter_alpha,
        "max_extension_force_taper_m": cs.max_extension_force_taper_m,
        "position_guard_warning_turns": cs.position_guard_warning_turns,
        "position_guard_hard_turns": cs.position_guard_hard_turns,
        # Zeroed-at-home position, distinct from the raw absolute encoder
        # reading in latest_sample.position -- requested 23 July 2026 (the
        # raw encoder value is whatever arbitrary number it was at power-on,
        # not 0 at home, which was confusing to read live).
        "cable_position_turns": cable_position_turns,
    }


def _any_session_running() -> bool:
    """Used for gates that must hold regardless of which mode is live, not
    just Exercise (added for the Train tab's Reset control,
    train_tab_build_spec.md "calibration overhaul" item 1; replaces a
    narrower `_exercise_action_running()` that only checked
    `status['mode'] == 'exercise'`). reset_position previously only blocked
    while an Exercise session was running, which meant a live *Train*
    session (a different `status['mode']`) could reset home/max out from
    under TrainMode.tick() while it was still reading them every tick at
    50Hz -- it fails safe (is_homed flips False, tick() just zeroes torque
    and returns) but resetting mid-session was never the intent. Same
    `control_routes.cable_state` singleton either way, so this is a strict
    widening of an existing gate, not a new mechanism."""
    status = control_routes.control_session.status()
    return bool(status["running"])


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
        erase-config modal); idle-gating is enforced here. Gated on ANY
        session running (_any_session_running(), not just Exercise) since
        this route is now also called from the Train tab's own Reset
        control -- see that function's docstring. Also drops any
        not-yet-saved spool-growth calibration points: they're an
        in-progress session artifact (core/cable/state.py's own
        pending_growth_points docstring), the same character as home/max,
        not a persisted/calibrated value."""
        if _any_session_running():
            return jsonify({"error": "Cannot reset while a session is running -- stop it first"}), 400
        control_routes.cable_state.reset()
        control_routes.cable_state.clear_pending_growth_points()
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
            # Additional to the coarse fat-finger bound above: an exact check
            # against the cable's ACTUAL calibrated travel range, not a
            # static guess (core/cable/state.py::check_k_against_travel_range).
            cs.check_k_against_travel_range(k)
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

    @app.route("/api/exercise/update_spool_k", methods=["POST"])
    def exercise_update_spool_k():
        """Direct entry of the wrap-growth correction factor k (added 25 July
        2026), as an alternative to /api/exercise/calibrate_k's back-
        computation from one measured length -- for a k value already known
        from elsewhere (a previous calibration, a spec sheet, a value worked
        out by hand). Still checked against the same physical-plausibility
        bounds calibrate_k uses (SPOOL_CORRECTION_K_BOUNDS); this route only
        skips the length-based derivation step, not the safety check -- a k
        outside that range makes the r_eff=r0+k*theta model go non-physical
        (negative effective radius) within the cable's real travel range."""
        body = request.get_json(silent=True) or {}
        k = body.get("k")
        if k is None:
            return jsonify({"error": "k required"}), 400
        try:
            k = float(k)
        except (TypeError, ValueError):
            return jsonify({"error": f"k must be numeric, got {k!r}"}), 400
        k_min, k_max = board_constants.SPOOL_CORRECTION_K_BOUNDS
        if not (k_min <= k <= k_max):
            return jsonify({"error": f"k={k!r} is outside the plausible range [{k_min!r}, {k_max!r}]"}), 400
        try:
            control_routes.cable_state.check_k_against_travel_range(k)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        control_routes.cable_state.set_k(k)
        return jsonify({"cable": _cable_status_dict()})

    @app.route("/api/exercise/update_calib_hold_force", methods=["POST"])
    def exercise_update_calib_hold_force():
        """Live-adjustable max-extension calibration hold force (requested
        23 July 2026) -- was a fixed CALIB_HOLD_FORCE_N constant (spec §3.2:
        must stay trivially overcome by hand; this route doesn't relax that
        expectation, just makes the exact value adjustable). Takes effect
        immediately, including mid-pull: ExerciseMode re-applies this value
        every tick while max_calibrating (exercise_mode.py
        _tick_max_calibrating)."""
        body = request.get_json(silent=True) or {}
        force_n = body.get("force_n")
        if force_n is None:
            return jsonify({"error": "force_n required"}), 400
        try:
            control_routes.cable_state.set_calib_hold_force(float(force_n))
            return jsonify({"cable": _cable_status_dict()})
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/exercise/update_force_settings", methods=["POST"])
    def exercise_update_force_settings():
        """Live-adjustable force/safety "feel" settings (requested 24 July
        2026, same pattern as update_homing_settings) -- let-go threshold/
        debounce, hold duration, force ramp rates, isokinetic governor
        gain/filter, max-extension force taper, and the two-tier position
        guard tolerances. Any subset may be given; omitted ones are left
        as-is. Deliberately does NOT cover hard hardware ceilings
        (FORCE_MAX_N, REGEN_POWER_BUDGET_W, MOTOR_CURRENT_LIM, DC bus regen
        limits) -- those stay fixed board_constants, see core/cable/state.py."""
        body = request.get_json(silent=True) or {}
        try:
            control_routes.cable_state.set_force_settings(
                letgo_velocity_turns_s=body.get("letgo_velocity_turns_s"),
                letgo_debounce_samples=body.get("letgo_debounce_samples"),
                hold_duration_s=body.get("hold_duration_s"),
                force_ramp_in_s=body.get("force_ramp_in_s"),
                force_ramp_out_s=body.get("force_ramp_out_s"),
                isokinetic_governor_gain=body.get("isokinetic_governor_gain"),
                isokinetic_velocity_filter_alpha=body.get("isokinetic_velocity_filter_alpha"),
                max_extension_force_taper_m=body.get("max_extension_force_taper_m"),
                position_guard_warning_turns=body.get("position_guard_warning_turns"),
                position_guard_hard_turns=body.get("position_guard_hard_turns"),
            )
            return jsonify({"cable": _cable_status_dict()})
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400

    # ---- Train tab calibration overhaul: manual max-extension entry ----

    @app.route("/api/exercise/set_max_extension_manual", methods=["POST"])
    def exercise_set_max_extension_manual():
        """Manual max-extension entry (item 1) -- an alternative to the
        physical-pull start_max_calibration/confirm_max flow above, for when
        the max extension is already known. Direct CableState mutation, no
        session/action needed (same shape as calibrate_k -- "doesn't need
        the motor moving")."""
        body = request.get_json(silent=True) or {}
        length_m = body.get("length_m")
        if length_m is None:
            return jsonify({"error": "length_m required"}), 400
        try:
            control_routes.cable_state.set_max_extension_manual(float(length_m))
            return jsonify({"cable": _cable_status_dict()})
        except (ValueError, TypeError, RuntimeError) as e:
            return jsonify({"error": str(e)}), 400

    # ---- Train tab calibration overhaul: experimental multi-point spool-
    # growth calibration (item 4/5) ----

    @app.route("/api/exercise/start_spool_growth_calibration", methods=["POST"])
    def exercise_start_spool_growth_calibration():
        return _dispatch_action("start_spool_growth_calibration")

    @app.route("/api/exercise/record_growth_point", methods=["POST"])
    def exercise_record_growth_point():
        """Records one (turns_from_home, measured length) point during an
        in-progress spool-growth calibration -- direct CableState mutation,
        same shape as calibrate_k, not a mode action (the motor doesn't need
        to do anything new to record a point, it's already holding taut from
        start_spool_growth_calibration above)."""
        body = request.get_json(silent=True) or {}
        length_m = body.get("length_m")
        if length_m is None:
            return jsonify({"error": "length_m required"}), 400

        cs = control_routes.cable_state
        if not cs.is_homed:
            return jsonify({"error": "Cable is not homed -- home before calibrating"}), 400

        status = control_routes.control_session.status()
        latest = status.get("latest_sample")
        if not latest or status.get("mode") != "exercise" or status.get("extra", {}).get("action") != "spool_growth_calibrating":
            return jsonify({"error": "Spool-growth calibration is not in progress -- start it first"}), 400

        try:
            length_m = float(length_m)
        except (TypeError, ValueError):
            return jsonify({"error": f"length_m must be numeric, got {length_m!r}"}), 400
        if length_m < 0:
            return jsonify({"error": f"length_m must be non-negative, got {length_m!r}"}), 400

        turns_from_home = latest["position"] - cs.home_turns
        cs.add_pending_growth_point(turns_from_home, length_m)
        return jsonify({"cable": _cable_status_dict()})

    @app.route("/api/exercise/remove_growth_point", methods=["POST"])
    def exercise_remove_growth_point():
        body = request.get_json(silent=True) or {}
        index = body.get("index")
        if index is None:
            return jsonify({"error": "index required"}), 400
        try:
            control_routes.cable_state.remove_pending_growth_point(int(index))
            return jsonify({"cable": _cable_status_dict()})
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/exercise/clear_growth_points", methods=["POST"])
    def exercise_clear_growth_points():
        """Clears the in-progress pending point list without ending the
        calibration hold -- lets the user restart the point list mid-session."""
        control_routes.cable_state.clear_pending_growth_points()
        return jsonify({"cable": _cable_status_dict()})

    @app.route("/api/exercise/cancel_spool_growth_calibration", methods=["POST"])
    def exercise_cancel_spool_growth_calibration():
        """Discards everything recorded this session and ends the hold."""
        control_routes.cable_state.clear_pending_growth_points()
        return _dispatch_action("end_spool_growth_calibration")

    @app.route("/api/exercise/save_growth_calibration", methods=["POST"])
    def exercise_save_growth_calibration():
        """Fits and persists the piecewise growth model from the points
        recorded this session (core/cable/geometry.py::build_growth_segments,
        surfaced via CableState.set_growth_points), then ends the hold the
        same way cancel does."""
        cs = control_routes.cable_state
        status = control_routes.control_session.status()
        if status.get("extra", {}).get("action") != "spool_growth_calibrating":
            return jsonify({"error": "Spool-growth calibration is not in progress -- start it first"}), 400
        if not cs.pending_growth_points:
            return jsonify({"error": "No points recorded yet -- record at least one before saving"}), 400

        try:
            cs.set_growth_points(sorted(cs.pending_growth_points))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        cs.clear_pending_growth_points()
        return _dispatch_action("end_spool_growth_calibration")

    @app.route("/api/exercise/clear_growth_calibration", methods=["POST"])
    def exercise_clear_growth_calibration():
        """Always available (no active session needed) -- wipes the SAVED
        growth calibration, reverting to the plain r0/k model. The "start
        over" button."""
        control_routes.cable_state.set_growth_points([])
        return jsonify({"cable": _cable_status_dict()})
