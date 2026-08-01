"""Thin adapter routes for anti-cogging calibration. Zero calibration logic
here (that's core/hardware/anticogging.py) -- argument parsing + device_manager
calls + JSON only, same split as every other routes module.

Routes through device_manager.get_shared_handle()/get_shared_io_lock() -- the
exact same choke point core/hardware/odrive_hw.py's OdriveHardware is
injected with (backend/app/control_routes.py::_real_hardware_factory) -- so
no new odrive.find_any() call site is introduced.

GET /api/anticogging/status is the one place that drives the state machine
forward: if a calibration is RUNNING, it polls the live calib_anticogging
flag on every call (core.hardware.anticogging.AnticoggingCalibration.poll()),
and the moment that flips to finished, THIS call runs the whole
restore-gains/pre_calibrated/save_configuration sequence inline. Since
save_configuration() reboots the board, device_manager's cached handle is
stale the instant that happens -- forget_all() is called right after a
DONE transition so the rest of the app (Inspector, sidebar, any other tab)
reconnects on its very next access instead of waiting for the ambient ~3s
sidebar poll to notice the dead handle on its own (see
device_manager._serialize_cache_if_alive's docstring for that ambient path).
"""

import logging

from flask import jsonify, request

from config import board_constants
from core.hardware.anticogging import AnticoggingCalibration, AnticoggingState

from . import control_routes
from . import device_manager

log = logging.getLogger(__name__)

anticogging = AnticoggingCalibration()


def _axis(odrv):
    return getattr(odrv, f"axis{board_constants.ACTIVE_AXIS}")


def _read_diagnostics(odrv):
    """Live axis0.controller.config.anticogging.* reads that don't depend on
    the calibration state machine -- always available so the enabled/disabled
    toggle and "anticogging_valid" indicator work regardless of whether a
    calibration has ever been run this session."""
    if odrv is None:
        return {"anticogging_enabled": None, "pre_calibrated": None, "anticogging_valid": None}
    try:
        axis = _axis(odrv)
        cfg = axis.controller.config.anticogging
        return {
            "anticogging_enabled": bool(cfg.anticogging_enabled),
            "pre_calibrated": bool(cfg.pre_calibrated),
            "anticogging_valid": bool(getattr(axis.controller, "anticogging_valid", False)),
        }
    except Exception:
        log.exception("Failed to read anticogging diagnostics")
        return {"anticogging_enabled": None, "pre_calibrated": None, "anticogging_valid": None}


def _status_dict():
    odrv = device_manager.get_shared_handle()

    if odrv is not None and anticogging.state == AnticoggingState.RUNNING:
        with device_manager.get_shared_io_lock():
            anticogging.poll(odrv)
        if anticogging.state == AnticoggingState.DONE:
            log.info("Anti-cogging calibration saved; dropping cached device handle (board is rebooting).")
            device_manager.forget_all()
            odrv = None  # the handle we already had is the now-stale pre-reboot one

    return {
        **anticogging.status(),
        **_read_diagnostics(odrv),
        "control_session_running": control_routes.control_session.status()["running"],
    }


def register(app) -> None:
    @app.route("/api/anticogging/status", methods=["GET"])
    def anticogging_status():
        return jsonify(_status_dict())

    @app.route("/api/anticogging/start", methods=["POST"])
    def anticogging_start():
        if control_routes.control_session.status()["running"]:
            return jsonify({"error": "A Control/Train/Testing session is running -- stop it before calibrating."}), 400

        body = request.get_json(silent=True) or {}
        odrv = device_manager.get_shared_handle()
        if odrv is None:
            return jsonify({"error": "No ODrive device found"}), 400

        try:
            with device_manager.get_shared_io_lock():
                anticogging.start(
                    odrv,
                    pos_gain_multiplier=body.get("pos_gain_multiplier"),
                    vel_integrator_gain_multiplier=body.get("vel_integrator_gain_multiplier"),
                    calib_pos_threshold=body.get("calib_pos_threshold"),
                    calib_vel_threshold=body.get("calib_vel_threshold"),
                )
            return jsonify(_status_dict())
        except Exception as e:
            log.exception("anticogging/start failed")
            return jsonify({"error": str(e)}), 400

    @app.route("/api/anticogging/abort", methods=["POST"])
    def anticogging_abort():
        odrv = device_manager.get_shared_handle()
        if odrv is None:
            return jsonify({"error": "No ODrive device found"}), 400
        with device_manager.get_shared_io_lock():
            anticogging.abort(odrv)
        return jsonify(_status_dict())

    @app.route("/api/anticogging/set_enabled", methods=["POST"])
    def anticogging_set_enabled():
        """Independent of the calibration state machine -- toggling this off
        doesn't lose the saved map, it just stops the controller from adding
        it to the torque output (spec: needed to diagnose whether the map
        itself is causing bad behavior)."""
        body = request.get_json(silent=True) or {}
        if "enabled" not in body:
            return jsonify({"error": "enabled required"}), 400
        odrv = device_manager.get_shared_handle()
        if odrv is None:
            return jsonify({"error": "No ODrive device found"}), 400
        try:
            axis = _axis(odrv)
            with device_manager.get_shared_io_lock():
                axis.controller.config.anticogging.anticogging_enabled = bool(body["enabled"])
            return jsonify(_status_dict())
        except Exception as e:
            log.exception("anticogging/set_enabled failed")
            return jsonify({"error": str(e)}), 400
