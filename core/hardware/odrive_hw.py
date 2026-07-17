"""Real HardwareInterface implementation, wrapping the `odrive` package
directly with its own find_any() call.

Deliberately does NOT import backend.app.device_manager — after this file the
repo has exactly two find_any() call sites (this one, plus
device_manager._find_any()) and the standalone config/odrive_config.py 1B
script. See docs/decisions.md for the two-connection flag: the Flask backend
keeps device_manager for the raw-testing tabs (Inspector/console/wizard); the
Control tab path goes through here. Both grabbing the same USB device at once
is a real conflict risk — flagged, not solved, pending real hardware in 2A.

Only does runtime control. Never writes config/calibration properties — that
is the wizard's and the 1B script's job.
"""

import logging
import time
from typing import List, Optional

from config import board_constants

from ._macos_usb import ensure_macos_libusb_path
from .interface import ControlMode, HardwareInterface, TelemetrySample

log = logging.getLogger(__name__)

_TORQUE_LIMIT_NM = board_constants.MOTOR_CURRENT_LIM * board_constants.MOTOR_TORQUE_CONSTANT


def _decode_errors(axis) -> List[str]:
    """Decode ODrive 0.5.1 axis/motor/encoder/controller error bitmasks into
    human-readable strings. Lazily imports odrive.enums (only needed with
    real hardware)."""
    import odrive.enums as enums

    out: List[str] = []
    _decode_bitmask(getattr(axis, "error", 0), enums, "AXIS_ERROR_", "axis", out)
    _decode_bitmask(getattr(axis.motor, "error", 0), enums, "MOTOR_ERROR_", "motor", out)
    _decode_bitmask(getattr(axis.encoder, "error", 0), enums, "ENCODER_ERROR_", "encoder", out)
    _decode_bitmask(getattr(axis.controller, "error", 0), enums, "CONTROLLER_ERROR_", "controller", out)
    return out


def _decode_bitmask(value: int, enums_module, prefix: str, label: str, out: List[str]) -> None:
    if not value:
        return
    for name in dir(enums_module):
        if not name.startswith(prefix) or name.endswith("_NONE"):
            continue
        bit = getattr(enums_module, name)
        if bit and (value & bit) == bit:
            out.append(f"{label}: {name}")


class OdriveHardware(HardwareInterface):
    def __init__(self, find_timeout: float = 2.0):
        self._find_timeout = find_timeout
        self._odrv = None
        self._axis = None

    def connect(self) -> None:
        ensure_macos_libusb_path()
        import odrive  # lazy import; only needed with real hardware

        # TODO(2A): reconcile with backend/app/device_manager's independent
        # connection — both may try to open the same USB device at once.
        found = odrive.find_any(timeout=self._find_timeout)
        if found is None:
            raise RuntimeError("No ODrive device found")
        self._odrv = found
        self._axis = getattr(found, f"axis{board_constants.ACTIVE_AXIS}")

    def disconnect(self) -> None:
        self._odrv = None
        self._axis = None

    @property
    def is_connected(self) -> bool:
        return self._axis is not None

    def get_state(self) -> TelemetrySample:
        axis = self._require_axis()
        current_iq = float(axis.motor.current_control.Iq_measured)
        return TelemetrySample(
            t=time.monotonic(),
            position=float(axis.encoder.pos_estimate),
            velocity=float(axis.encoder.vel_estimate),
            current_iq=current_iq,
            torque_est=board_constants.MOTOR_TORQUE_CONSTANT * current_iq,
        )

    def set_mode(self, mode: ControlMode) -> None:
        import odrive.enums as enums

        axis = self._require_axis()
        if mode == ControlMode.IDLE:
            axis.requested_state = enums.AXIS_STATE_IDLE
            return
        if mode == ControlMode.VELOCITY:
            axis.controller.config.control_mode = enums.CONTROL_MODE_VELOCITY_CONTROL
        elif mode == ControlMode.TORQUE:
            axis.controller.config.control_mode = enums.CONTROL_MODE_TORQUE_CONTROL
        else:
            raise ValueError(f"Unknown control mode: {mode}")
        axis.controller.config.input_mode = enums.INPUT_MODE_PASSTHROUGH
        axis.requested_state = enums.AXIS_STATE_CLOSED_LOOP_CONTROL

    def set_velocity_target(self, turns_per_s: float) -> None:
        axis = self._require_axis()
        limit = board_constants.CONTROLLER_VEL_LIMIT
        clamped = max(-limit, min(limit, turns_per_s))
        if clamped != turns_per_s:
            log.warning(
                "Velocity target %.4f turns/s clamped to %.4f (vel_limit=%.4f)",
                turns_per_s, clamped, limit,
            )
        axis.controller.input_vel = clamped

    def set_torque_target(self, nm: float) -> None:
        axis = self._require_axis()
        clamped = max(-_TORQUE_LIMIT_NM, min(_TORQUE_LIMIT_NM, nm))
        if clamped != nm:
            log.warning(
                "Torque target %.4f Nm clamped to %.4f (current_lim=%.2fA * torque_constant=%.4f)",
                nm, clamped, board_constants.MOTOR_CURRENT_LIM, board_constants.MOTOR_TORQUE_CONSTANT,
            )
        axis.controller.input_torque = clamped

    def stop(self) -> None:
        """Safe to call at any time, from any thread, repeatedly — including
        when never connected or already disconnected."""
        axis = self._axis
        if axis is None:
            return
        try:
            axis.controller.input_vel = 0.0
            axis.controller.input_torque = 0.0
        except Exception:
            log.exception("Failed to zero targets during stop()")
        try:
            import odrive.enums as enums
            axis.requested_state = enums.AXIS_STATE_IDLE
        except Exception:
            log.exception("Failed to request AXIS_STATE_IDLE during stop()")

    def get_errors(self) -> List[str]:
        axis = self._axis
        if axis is None:
            return []
        try:
            return _decode_errors(axis)
        except Exception:
            log.exception("Failed to read/decode axis errors")
            return []

    def _require_axis(self):
        if self._axis is None:
            raise RuntimeError("Not connected to an ODrive device")
        return self._axis
