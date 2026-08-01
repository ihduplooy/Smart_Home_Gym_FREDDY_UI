"""Thin adapter routes for the Exercise tab's Force Feedback section.
Zero control logic here, same split as control_routes.py/exercise_routes.py.

Force feedback used to be a separate ControlSession mode ("force"),
mutually exclusive with Exercise. Merged 24 July 2026 (see
core/cable/exercise_mode.py's module docstring): engage/disengage/
update_params/resume are now just actions on the one running "exercise"
session, dispatched the exact same way exercise_routes.py's own actions
are -- no separate start/stop here anymore, no separate session to arm.
Every route still returns {"control": ..., "cable": ...}, matching
exercise_routes.py's routes exactly.
"""

import logging

from flask import jsonify, request

from . import control_routes
from . import exercise_routes

log = logging.getLogger(__name__)


def _status_dict() -> dict:
    return {"control": control_routes.control_session.status(), "cable": exercise_routes._cable_status_dict()}


def register(app) -> None:
    def _dispatch_action(action: str, extra_fields: dict = None):
        try:
            value = {"action": action, **(extra_fields or {})}
            control_routes.control_session.set_target(value)
            return jsonify(_status_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    def _force_params_extra(body: dict) -> dict:
        mode = body.get("mode")
        extra = {
            "mode": mode,
            "concentric_force_n": body.get("concentric_force_n"),
            "eccentric_force_n": body.get("eccentric_force_n"),
        }
        if body.get("velocity_target_turns_s") is not None:
            extra["velocity_target_turns_s"] = body["velocity_target_turns_s"]
        # Configurable active sub-range (requested 23 July 2026) -- either,
        # both, or neither may be given; omitted ones default to the full
        # home->max range (see ExerciseMode._resolve_range).
        if body.get("start_length_m") is not None:
            extra["start_length_m"] = body["start_length_m"]
        if body.get("end_length_m") is not None:
            extra["end_length_m"] = body["end_length_m"]
        return extra

    @app.route("/api/force/engage", methods=["POST"])
    def force_engage():
        body = request.get_json(silent=True) or {}
        if body.get("mode") is None or body.get("concentric_force_n") is None or body.get("eccentric_force_n") is None:
            return jsonify({"error": "mode, concentric_force_n and eccentric_force_n required"}), 400
        return _dispatch_action("engage", _force_params_extra(body))

    @app.route("/api/force/update_params", methods=["POST"])
    def force_update_params():
        body = request.get_json(silent=True) or {}
        if body.get("mode") is None or body.get("concentric_force_n") is None or body.get("eccentric_force_n") is None:
            return jsonify({"error": "mode, concentric_force_n and eccentric_force_n required"}), 400
        return _dispatch_action("update_params", _force_params_extra(body))

    @app.route("/api/force/disengage", methods=["POST"])
    def force_disengage():
        return _dispatch_action("disengage")

    @app.route("/api/force/resume", methods=["POST"])
    def force_resume():
        """Manual resume from FAULT -- confirmation is the frontend's job (a
        confirm dialog), lighter than re-homing: force parameters and
        CableState's home/max are untouched. Moves ExerciseMode's force
        state machine to SETTLING (not straight back to ARMED) -- Engage
        stays refused until measured velocity has actually settled, see
        core/cable/exercise_mode.py."""
        return _dispatch_action("resume")
