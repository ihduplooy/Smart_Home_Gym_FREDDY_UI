"""Thin adapter routes for the Train tab (train_tab_build_spec.md §2). Zero
control logic here, same split as control_routes.py/exercise_routes.py.

Unlike Force Feedback (merged into ExerciseMode's action set), Train is its
own `ControlSession` mode ("train", registered in control_routes.py's
mode_factories) with a real start/stop lifecycle -- so these routes mirror
control_routes.py's start/target/stop shape for the lifecycle bits and
exercise_routes.py's action-dispatch shape for set_profile.

Manual jogging (a "move"/"stop_move" action pair) used to live here too;
removed 25 July 2026 at the user's request in favour of the Control tab's
own Position mode, which already covers manual moves better (PI tuning,
velocity control) without being coupled to a Train session's lifecycle. See
docs/decisions.md ("Train tab refinements").

Homing, max-extension calibration, and spool calibration are deliberately
NOT duplicated here (spec §3): the Train tab's Settings section calls
/api/exercise/{home,abort_homing,start_max_calibration,confirm_max,
cancel_max_calibration,calibrate_k,...} directly, the same routes
ExerciseTab.jsx already uses, since they operate on the same shared
`cable_state` regardless of which mode is currently running. A Train session
can only start once already homed (TrainMode._apply_run validates this) --
home via the Exercise tab (or Train's embedded copy of that same UI), stop
that session, then start Train.
"""

import logging

from flask import jsonify, request

from core.cable.train_profiles import TrainProfile

from . import control_routes
from . import exercise_routes

log = logging.getLogger(__name__)


def _status_dict() -> dict:
    cs = control_routes.cable_state
    return {
        "control": control_routes.control_session.status(),
        "cable": {
            **exercise_routes._cable_status_dict(),
            "train_max_extension_enforced": cs.train_max_extension_enforced,
            "train_home_guard_enforced": cs.train_home_guard_enforced,
            "train_telemetry_buffer_s": cs.train_telemetry_buffer_s,
        },
    }


def _profile_from_body(body: dict) -> TrainProfile:
    profile_data = body.get("profile")
    if profile_data is None:
        return TrainProfile(name="empty", segments=[])
    return TrainProfile.from_dict(profile_data)


def register(app) -> None:
    @app.route("/api/train/status", methods=["GET"])
    def train_status():
        return jsonify(_status_dict())

    @app.route("/api/train/start", methods=["POST"])
    def train_start():
        body = request.get_json(silent=True) or {}
        try:
            profile = _profile_from_body(body)
            control_routes.control_session.start(mode="train", target={"action": "run", "profile": profile})
            return jsonify(_status_dict())
        except Exception as e:
            log.exception("train/start failed")
            return jsonify({"error": str(e)}), 400

    @app.route("/api/train/stop", methods=["POST"])
    def train_stop():
        """The always-available Stop -- a thin alias for the same
        control_session.stop() every other tab's Stop already calls."""
        control_routes.control_session.stop()
        return jsonify(_status_dict())

    def _dispatch_action(action: str, extra_fields: dict = None):
        try:
            value = {"action": action, **(extra_fields or {})}
            control_routes.control_session.set_target(value)
            return jsonify(_status_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/train/set_profile", methods=["POST"])
    def train_set_profile():
        """Live retarget while a Train session is running (spec §4: the
        profile editor's "Apply" button) -- swaps the active profile in
        place, no motor interruption."""
        body = request.get_json(silent=True) or {}
        try:
            profile = _profile_from_body(body)
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400
        return _dispatch_action("set_profile", {"profile": profile})

    @app.route("/api/train/update_settings", methods=["POST"])
    def train_update_settings():
        """Live-adjustable Train settings (spec §1/§3): the max-extension and
        home-guard enforcement toggles (independent, split 25 July 2026) and
        the graph telemetry buffer duration. Any subset; persisted via
        CableState the same way homing/force settings already are."""
        body = request.get_json(silent=True) or {}
        try:
            control_routes.cable_state.set_train_settings(
                max_extension_enforced=body.get("max_extension_enforced"),
                home_guard_enforced=body.get("home_guard_enforced"),
                telemetry_buffer_s=body.get("telemetry_buffer_s"),
            )
            return jsonify(_status_dict())
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/train/preview_profile", methods=["POST"])
    def train_preview_profile():
        """Pure evaluation, no hardware/session involved -- the profile
        editor's live curve (spec §4) and, with the same request shape, the
        live torque-vs-position overlay's static "planned" curve. Body:
        {profile, position_range_m: [lo, hi], n_points?}."""
        body = request.get_json(silent=True) or {}
        position_range_m = body.get("position_range_m")
        if not isinstance(position_range_m, list) or len(position_range_m) != 2:
            return jsonify({"error": "position_range_m must be [lo, hi]"}), 400
        try:
            profile = _profile_from_body(body)
            n_points = int(body.get("n_points", 200))
            points = profile.preview((float(position_range_m[0]), float(position_range_m[1])), n_points=n_points)
            return jsonify({"points": [{"position_m": p, "force_n": f} for p, f in points]})
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400
