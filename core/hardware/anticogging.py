"""Anti-cogging calibration — a maintenance/calibration action, deliberately
separate from ControlSession's velocity/torque/position/profile/train/
exercise modes (core/control/modes.py, core/cable/). Those all model a
continuous per-tick control loop; this is a one-shot ODrive-firmware-driven
routine (the motor spins through ~1 turn autonomously once
`start_anticogging_calibration()` is called — nothing here commands it tick
by tick) that writes NVM config and reboots the board. That's exactly the
"config/calibration writes" territory core/hardware/odrive_hw.py's own
docstring says belongs to "the wizard's and the 1B script's job", not to a
ControlSession HardwareInterface — so this lives in its own module instead of
being bolted onto OdriveHardware.

Still routes through the one real choke point: callers pass in the `odrv`
handle from backend/app/device_manager.get_shared_handle() (the same shared
handle core/hardware/odrive_hw.py's OdriveHardware is injected with) — this
module never calls odrive.find_any() itself.

Firmware v0.5.1 property paths (axis{n}.controller.config.anticogging.*),
corroborated against frontend/src/utils/odriveApiReference05x.json:
  pre_calibrated, calib_anticogging, calib_pos_threshold, calib_vel_threshold,
  anticogging_enabled — all confirmed present in that reference, alongside
  axis{n}.controller.start_anticogging_calibration().

Sequence (a stateful, request-driven state machine — no background thread;
the Flask route layer drives start()/poll()/abort() per HTTP request, same
REST-polling convention as every other tab in this app):
  IDLE -> start() -> RUNNING -> poll() [repeated, cheap] -> DONE | ABORTED | FAILED

start(): captures the current pos_gain/vel_integrator_gain so they can be
restored exactly (not restored to board_constants' tuned values -- if the
board has since been re-tuned, THAT is what "restore" should mean), sets
control_mode/input_mode/thresholds/raised gains, enters closed-loop control,
and calls start_anticogging_calibration(). Requires the axis to already have
a valid motor+encoder calibration (checked via axis.motor.is_calibrated /
axis.encoder.is_ready) -- this deliberately never re-runs motor/encoder
calibration itself (that's config/odrive_config.py's job, run once at
bring-up).

poll(): cheap, side-effect-free while calib_anticogging is still True. The
moment it reads False, this SAME call performs the finish sequence (restore
gains, set pre_calibrated=True, save_configuration()) inline -- no separate
"saving" phase to poll for, since the whole sequence is a handful of fast
property writes plus one RPC. save_configuration() reboots the board
mid-call; the expected fibre.protocol.ChannelBrokenException is caught here
exactly like config/odrive_config.py's call_and_reconnect() does, and NOT
treated as a failure. The caller (backend/app/anticogging_routes.py) is
responsible for dropping device_manager's now-stale cached handle so the
next access anywhere in the app forces a fresh reconnect, rather than waiting
for the ambient ~3s sidebar poll to notice the dead handle on its own.

Absolute encoder note (AS5047P / SPI_ABS_AMS): no index-search step is
triggered anywhere here, and none should be -- the saved map loads directly
off absolute position at boot once pre_calibrated=True is saved, per the
build task's own note.
"""

import logging
from enum import Enum
from typing import Any, Dict, Optional

from config import board_constants

log = logging.getLogger(__name__)


class AnticoggingState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ABORTED = "aborted"
    FAILED = "failed"


def _axis(odrv):
    return getattr(odrv, f"axis{board_constants.ACTIVE_AXIS}")


class AnticoggingCalibration:
    def __init__(self):
        self._state = AnticoggingState.IDLE
        self._orig_pos_gain: Optional[float] = None
        self._orig_vel_integrator_gain: Optional[float] = None
        self._error_message: Optional[str] = None

    @property
    def state(self) -> AnticoggingState:
        return self._state

    def status(self) -> Dict[str, Any]:
        return {"state": self._state.value, "error_message": self._error_message}

    def start(
        self,
        odrv: Any,
        pos_gain_multiplier: float = None,
        vel_integrator_gain_multiplier: float = None,
        calib_pos_threshold: float = None,
        calib_vel_threshold: float = None,
    ) -> Dict[str, Any]:
        if self._state == AnticoggingState.RUNNING:
            raise RuntimeError("Anti-cogging calibration is already running")

        pos_gain_multiplier = (
            board_constants.ANTICOGGING_POS_GAIN_MULTIPLIER_DEFAULT
            if pos_gain_multiplier is None
            else pos_gain_multiplier
        )
        vel_integrator_gain_multiplier = (
            board_constants.ANTICOGGING_VEL_INTEGRATOR_GAIN_MULTIPLIER_DEFAULT
            if vel_integrator_gain_multiplier is None
            else vel_integrator_gain_multiplier
        )
        calib_pos_threshold = (
            board_constants.ANTICOGGING_CALIB_POS_THRESHOLD_DEFAULT
            if calib_pos_threshold is None
            else calib_pos_threshold
        )
        calib_vel_threshold = (
            board_constants.ANTICOGGING_CALIB_VEL_THRESHOLD_DEFAULT
            if calib_vel_threshold is None
            else calib_vel_threshold
        )
        if pos_gain_multiplier <= 0:
            raise ValueError(f"pos_gain_multiplier must be positive, got {pos_gain_multiplier!r}")
        if vel_integrator_gain_multiplier <= 0:
            raise ValueError(f"vel_integrator_gain_multiplier must be positive, got {vel_integrator_gain_multiplier!r}")
        if calib_pos_threshold <= 0:
            raise ValueError(f"calib_pos_threshold must be positive, got {calib_pos_threshold!r}")
        if calib_vel_threshold <= 0:
            raise ValueError(f"calib_vel_threshold must be positive, got {calib_vel_threshold!r}")

        axis = _axis(odrv)

        if not axis.motor.is_calibrated:
            raise RuntimeError(
                "Motor is not calibrated -- run the motor/encoder calibration in "
                "config/odrive_config.py first (this never re-runs that itself)."
            )
        if not axis.encoder.is_ready:
            raise RuntimeError(
                "Encoder is not ready -- run the motor/encoder calibration in "
                "config/odrive_config.py first (this never re-runs that itself)."
            )

        import odrive.enums as enums

        self._orig_pos_gain = float(axis.controller.config.pos_gain)
        self._orig_vel_integrator_gain = float(axis.controller.config.vel_integrator_gain)

        axis.controller.config.control_mode = enums.CONTROL_MODE_POSITION_CONTROL
        axis.controller.config.input_mode = enums.INPUT_MODE_PASSTHROUGH
        axis.controller.config.anticogging.calib_pos_threshold = calib_pos_threshold
        axis.controller.config.anticogging.calib_vel_threshold = calib_vel_threshold
        axis.controller.config.pos_gain = self._orig_pos_gain * pos_gain_multiplier
        axis.controller.config.vel_integrator_gain = self._orig_vel_integrator_gain * vel_integrator_gain_multiplier

        axis.requested_state = enums.AXIS_STATE_CLOSED_LOOP_CONTROL
        axis.controller.start_anticogging_calibration()

        self._state = AnticoggingState.RUNNING
        self._error_message = None
        return self.status()

    def poll(self, odrv: Any) -> Dict[str, Any]:
        if self._state != AnticoggingState.RUNNING:
            return self.status()

        axis = _axis(odrv)
        try:
            still_calibrating = bool(axis.controller.config.anticogging.calib_anticogging)
        except Exception as e:
            log.exception("Failed to read calib_anticogging mid-calibration")
            self._restore_gains_best_effort(axis)
            self._state = AnticoggingState.FAILED
            self._error_message = f"Failed to read calibration status: {e}"
            return self.status()

        if still_calibrating:
            return self.status()

        return self._finish(odrv, axis)

    def abort(self, odrv: Any) -> Dict[str, Any]:
        if self._state != AnticoggingState.RUNNING:
            return self.status()

        axis = _axis(odrv)
        try:
            import odrive.enums as enums
            axis.requested_state = enums.AXIS_STATE_IDLE
        except Exception:
            log.exception("Failed to request AXIS_STATE_IDLE during anti-cogging abort")
        self._restore_gains_best_effort(axis)

        self._state = AnticoggingState.ABORTED
        self._error_message = None
        return self.status()

    # ---- internal ----

    def _finish(self, odrv: Any, axis: Any) -> Dict[str, Any]:
        try:
            self._restore_gains(axis)
            axis.controller.config.anticogging.pre_calibrated = True
        except Exception as e:
            log.exception("Failed to finalize anti-cogging calibration")
            self._state = AnticoggingState.FAILED
            self._error_message = f"Failed to finalize calibration: {e}"
            return self.status()

        try:
            import fibre.protocol
            try:
                odrv.save_configuration()
            except fibre.protocol.ChannelBrokenException:
                pass  # expected: save_configuration() reboots the board mid-call
        except Exception as e:
            log.exception("save_configuration() failed during anti-cogging finish")
            self._state = AnticoggingState.FAILED
            self._error_message = f"save_configuration() failed: {e}"
            return self.status()

        self._state = AnticoggingState.DONE
        self._error_message = None
        return self.status()

    def _restore_gains(self, axis: Any) -> None:
        if self._orig_pos_gain is not None:
            axis.controller.config.pos_gain = self._orig_pos_gain
        if self._orig_vel_integrator_gain is not None:
            axis.controller.config.vel_integrator_gain = self._orig_vel_integrator_gain

    def _restore_gains_best_effort(self, axis: Any) -> None:
        try:
            self._restore_gains(axis)
        except Exception:
            log.exception("Failed to restore gains after anti-cogging calibration stopped")
