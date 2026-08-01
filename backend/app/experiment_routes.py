"""Thin adapter routes for the Testing tab (Testing tab Build Spec §7). Zero
control logic here, same split as train_routes.py/control_routes.py.

Homing, max-extension, and spool calibration are deliberately NOT duplicated
here (same convention as train_routes.py's own header note): the Testing
tab's prerequisite banner reads the same `exercise_routes._cable_status_dict()`
every other tab already reads, and calibration itself happens via the Train
tab's existing /api/exercise/* routes against the same shared `cable_state`.
"""

import logging

from flask import jsonify, request

from core.experiments import EXPERIMENT_REGISTRY

from . import control_routes
from . import exercise_routes

log = logging.getLogger(__name__)


def _current_position_m():
    cs = control_routes.cable_state
    if not cs.is_homed:
        return None
    latest = control_routes.control_session.status().get("latest_sample")
    if latest is None:
        return None
    return cs.spool_geometry.length_from_turns_delta(latest["position"] - cs.home_turns)


def _status_dict() -> dict:
    return {
        "control": control_routes.control_session.status(),
        "cable": exercise_routes._cable_status_dict(),
        "current_position_m": _current_position_m(),
    }


def register(app) -> None:
    @app.route("/api/experiments", methods=["GET"])
    def list_experiments():
        """Registry-driven experiment list for the Testing tab's selector --
        name, label, and per-field config schema, from each experiment's own
        describe(). Never hardcoded in the frontend (mirrors /api/profiles)."""
        cable_state = control_routes.cable_state
        return jsonify([factory(cable_state).describe() for factory in EXPERIMENT_REGISTRY.values()])

    @app.route("/api/experiments/status", methods=["GET"])
    def experiments_status():
        return jsonify(_status_dict())

    @app.route("/api/experiments/configure", methods=["POST"])
    def experiments_configure():
        """Safe, zero-motion step (Testing tab Build Spec §5): validates the
        config and arms the experiment, but never energizes the motor -- that
        only happens via the separate /confirm_start route below."""
        body = request.get_json(silent=True) or {}
        experiment = body.get("experiment")
        config = body.get("config")
        try:
            control_routes.control_session.start(
                mode="experiment",
                target={"action": "configure", "experiment": experiment, "config": config},
            )
            return jsonify(_status_dict())
        except Exception as e:
            log.exception("experiments/configure failed")
            return jsonify({"error": str(e)}), 400

    @app.route("/api/experiments/confirm_start", methods=["POST"])
    def experiments_confirm_start():
        """The explicit human-confirmation route (spec §5) -- the only call
        that begins RAMPING and commands non-zero torque."""
        try:
            control_routes.control_session.set_target({"action": "confirm_start"})
            return jsonify(_status_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/experiments/stop", methods=["POST"])
    def experiments_stop():
        """The always-available Stop -- a thin alias for the same
        control_session.stop() every other tab's Stop already calls."""
        control_routes.control_session.stop()
        return jsonify(_status_dict())
