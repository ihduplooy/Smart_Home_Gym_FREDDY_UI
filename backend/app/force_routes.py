"""Thin adapter routes for the Exercise tab's Force Feedback section (Layer B
Session B1 — concentric force feedback, exercise_tab_build_spec_layerB.md).
Zero control logic here, same split as control_routes.py/exercise_routes.py.

Mirrors exercise_routes.py's structure rather than extending it — Force's
action set (engage/disengage/update_params/resume) doesn't fit either
control_routes.py's {mode, target} shape or exercise_routes.py's own
action set. Shares the same `control_session` singleton (so the
`find_any()` choke point stays a single call site) and the module-level
`cable_state` from control_routes.py.

No dedicated status route — /api/exercise/status is already generic
(control_session.status() + cable_state fields, regardless of which mode
is active) and is reused unchanged for Force's live status too. Every route
here still returns {"control": ..., "cable": ...} in its own response body
(same shape /api/exercise/status returns), matching exercise_routes.py's
routes exactly, so callers get a consistent shape regardless of which
action route they just posted to.
"""

import logging

from flask import jsonify, request

from . import control_routes
from . import exercise_routes

log = logging.getLogger(__name__)


def _status_dict() -> dict:
    return {"control": control_routes.control_session.status(), "cable": exercise_routes._cable_status_dict()}


def register(app) -> None:
    @app.route("/api/force/start", methods=["POST"])
    def force_start():
        """Arms the Force session -- zero torque (spec §6 item 1: no torque
        without explicit engagement)."""
        try:
            control_routes.control_session.start(mode="force", target={"action": "arm"})
            return jsonify(_status_dict())
        except Exception as e:
            log.exception("force/start failed")
            return jsonify({"error": str(e)}), 400

    def _dispatch_action(action: str, extra_fields: dict = None):
        try:
            value = {"action": action, **(extra_fields or {})}
            control_routes.control_session.set_target(value)
            return jsonify(_status_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    def _force_params_extra(body: dict) -> dict:
        mode = body.get("mode")
        force_n = body.get("force_n")
        extra = {"mode": mode, "force_n": force_n}
        if body.get("velocity_target_turns_s") is not None:
            extra["velocity_target_turns_s"] = body["velocity_target_turns_s"]
        # Configurable active sub-range (requested 23 July 2026) -- either,
        # both, or neither may be given; omitted ones default to the full
        # home->max range (see ForceMode._resolve_range).
        if body.get("start_length_m") is not None:
            extra["start_length_m"] = body["start_length_m"]
        if body.get("end_length_m") is not None:
            extra["end_length_m"] = body["end_length_m"]
        return extra

    @app.route("/api/force/engage", methods=["POST"])
    def force_engage():
        body = request.get_json(silent=True) or {}
        if body.get("mode") is None or body.get("force_n") is None:
            return jsonify({"error": "mode and force_n required"}), 400
        return _dispatch_action("engage", _force_params_extra(body))

    @app.route("/api/force/update_params", methods=["POST"])
    def force_update_params():
        body = request.get_json(silent=True) or {}
        if body.get("mode") is None or body.get("force_n") is None:
            return jsonify({"error": "mode and force_n required"}), 400
        return _dispatch_action("update_params", _force_params_extra(body))

    @app.route("/api/force/disengage", methods=["POST"])
    def force_disengage():
        return _dispatch_action("disengage")

    @app.route("/api/force/resume", methods=["POST"])
    def force_resume():
        """Manual resume from FAULT (spec §4.6) -- confirmation is the
        frontend's job (a confirm dialog), lighter than re-homing: force
        parameters and CableState's home/max are untouched, only
        ForceMode's own state machine moves, back to ARMED not ENGAGED."""
        return _dispatch_action("resume")

    @app.route("/api/force/stop", methods=["POST"])
    def force_stop():
        """The always-available Stop (spec §6 item 9) -- a thin alias for
        the same control_session.stop() every other tab's Stop already
        calls, so nothing new needs to be trusted here."""
        control_routes.control_session.stop()
        return jsonify(_status_dict())
