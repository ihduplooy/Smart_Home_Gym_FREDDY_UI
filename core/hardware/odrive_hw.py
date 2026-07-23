"""Real HardwareInterface implementation, wrapping the `odrive` package.

Deliberately does NOT import backend.app.device_manager (core/ never imports
backend/ — see core/README.md's split rule). Instead, the two optional
constructor hooks below let the backend inject its own device discovery and
locking without this file knowing backend/ exists:

  - `find_any_fn(timeout) -> odrv | None`: how to obtain a device handle in
    connect(). Defaults to a fresh `odrive.find_any(timeout=...)` call (the
    original standalone behaviour — still what `core/README.md`'s snippets
    and `core/tests/` get, since nothing there injects this).
  - `lock_provider() -> context manager`: resolved fresh on every hardware
    call (not cached), so it always reflects whatever's currently the "right"
    lock. Defaults to a no-op (`contextlib.nullcontext`).

Resolved this way, confirmed live on real hardware, 22 July 2026 (docs/
decisions.md): this used to be a second, independent `odrive.find_any()`
call site racing `backend/app/device_manager`'s own — `odrive.find_any()`
performs a real USB bus reset every call, so starting a Control-tab run could
reset the bus out from under the sidebar's already-open per-device telemetry
connection, corrupting it (looked like "the UI doesn't show the error" — the
sidebar's connection had actually broken, not failed to detect anything).
`backend/app/control_routes.py` now injects `device_manager.get_shared_handle`
as `find_any_fn`, so a Control run reuses the sidebar's already-cached
connection (zero extra resets in the common case) instead of opening a rival
one, and `device_manager.get_shared_io_lock` as `lock_provider`, so Control's
hardware reads/writes serialize against the sidebar/Inspector's own reads on
the same physical USB channel — the same `io_lock` `backend/app/telemetry.py`
already uses for that.

`stop()` deliberately does NOT take the lock — see its docstring.

Only does runtime control. Never writes config/calibration properties — that
is the wizard's and the 1B script's job.
"""

import contextlib
import logging
import time
from typing import Callable, List, Optional

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
    def __init__(
        self,
        find_timeout: float = 2.0,
        find_any_fn: Optional[Callable[[float], object]] = None,
        lock_provider: Optional[Callable[[], object]] = None,
    ):
        self._find_timeout = find_timeout
        self._find_any_fn = find_any_fn
        self._lock_provider = lock_provider or (lambda: contextlib.nullcontext())
        self._odrv = None
        self._axis = None

    def connect(self) -> None:
        ensure_macos_libusb_path()
        if self._find_any_fn is not None:
            found = self._find_any_fn(self._find_timeout)
        else:
            import odrive  # lazy import; only needed with real hardware
            found = odrive.find_any(timeout=self._find_timeout)
        if found is None:
            raise RuntimeError("No ODrive device found")
        self._odrv = found
        self._axis = getattr(found, f"axis{board_constants.ACTIVE_AXIS}")
        # Backstop for the Exercise tab's homing mode (spec §4 item 4):
        # reassert the documented operating current limit on every fresh
        # connection, regardless of what a previous session (this process or
        # a crashed one) left the live device at. Homing temporarily lowers
        # this and is responsible for restoring it on every one of its own
        # exit paths, but a session torn down before that cleanup runs
        # (e.g. the global Stop firing mid-homing) must not be able to leak
        # a lowered limit into the next Control/Profiles session.
        with self._lock_provider():
            self._axis.motor.config.current_lim = board_constants.MOTOR_CURRENT_LIM

    def disconnect(self) -> None:
        self._odrv = None
        self._axis = None

    @property
    def is_connected(self) -> bool:
        return self._axis is not None

    def get_state(self) -> TelemetrySample:
        axis = self._require_axis()
        with self._lock_provider():
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
        with self._lock_provider():
            if mode == ControlMode.IDLE:
                axis.requested_state = enums.AXIS_STATE_IDLE
                return
            if mode == ControlMode.VELOCITY:
                axis.controller.config.control_mode = enums.CONTROL_MODE_VELOCITY_CONTROL
                axis.controller.config.input_mode = enums.INPUT_MODE_PASSTHROUGH
            elif mode == ControlMode.TORQUE:
                axis.controller.config.control_mode = enums.CONTROL_MODE_TORQUE_CONTROL
                axis.controller.config.input_mode = enums.INPUT_MODE_PASSTHROUGH
                # Open item #8, resolved (Layer B §3.1) -- reasserted on every
                # torque-mode entry, not a one-time NVM write, so it applies
                # uniformly to Control's TorqueMode, Profiles' ProfileMode,
                # and Layer B's ForceMode alike (same relationship connect()
                # already has with current_lim: the runtime code is the
                # source of truth, not whatever a prior session happened to
                # leave saved). See board_constants.py's
                # ENABLE_TORQUE_MODE_VEL_LIMIT comment for the full
                # reasoning and the live-verification checklist this
                # property belongs to -- unconfirmed against a live board as
                # of this write; if this property name doesn't exist on this
                # firmware, this raises loudly and immediately on first
                # torque-mode entry rather than silently no-op-ing.
                axis.controller.config.enable_torque_mode_vel_limit = board_constants.ENABLE_TORQUE_MODE_VEL_LIMIT
            elif mode == ControlMode.POSITION:
                # Trapezoidal Trajectory (not Passthrough) so the move is
                # shaped by trap_traj's vel/accel/decel limits (set via
                # set_position_target()) instead of jumping straight there.
                axis.controller.config.control_mode = enums.CONTROL_MODE_POSITION_CONTROL
                axis.controller.config.input_mode = enums.INPUT_MODE_TRAP_TRAJ
            else:
                raise ValueError(f"Unknown control mode: {mode}")
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
        with self._lock_provider():
            axis.controller.input_vel = clamped

    def set_torque_target(self, nm: float) -> None:
        axis = self._require_axis()
        clamped = max(-_TORQUE_LIMIT_NM, min(_TORQUE_LIMIT_NM, nm))
        if clamped != nm:
            log.warning(
                "Torque target %.4f Nm clamped to %.4f (current_lim=%.2fA * torque_constant=%.4f)",
                nm, clamped, board_constants.MOTOR_CURRENT_LIM, board_constants.MOTOR_TORQUE_CONSTANT,
            )
        with self._lock_provider():
            axis.controller.input_torque = clamped

    def set_position_target(
        self,
        turns: float,
        move_velocity: float,
        accel_decel: float,
        torque_limit: float = None,
    ) -> None:
        axis = self._require_axis()
        with self._lock_provider():
            if torque_limit is not None:
                clamped_torque = max(0.0, min(_TORQUE_LIMIT_NM, torque_limit))
                if clamped_torque != torque_limit:
                    log.warning(
                        "Position-move torque limit %.4f Nm clamped to %.4f (current_lim=%.2fA * torque_constant=%.4f)",
                        torque_limit, clamped_torque, board_constants.MOTOR_CURRENT_LIM, board_constants.MOTOR_TORQUE_CONSTANT,
                    )
                axis.motor.config.torque_lim = clamped_torque
            axis.trap_traj.config.vel_limit = abs(move_velocity)
            axis.trap_traj.config.accel_limit = abs(accel_decel)
            axis.trap_traj.config.decel_limit = abs(accel_decel)
            axis.controller.input_pos = turns

    def set_current_limit(self, amps: float) -> None:
        axis = self._require_axis()
        with self._lock_provider():
            axis.motor.config.current_lim = amps

    def stop(self) -> None:
        """Safe to call at any time, from any thread, repeatedly — including
        when never connected or already disconnected.

        Deliberately does NOT take `self._lock_provider()`. This is the
        emergency path ControlSession.stop() calls first, before its own
        session lock, specifically so a wedged get_state() elsewhere can
        never block it (see core/control/session.py's docstring and
        test_stop_reaches_hardware_even_if_telemetry_thread_wedged). Adding a
        lock acquisition here would reopen exactly that hole for real
        hardware. The accepted tradeoff: a stop() that lands in the same
        instant as another thread's locked read/write on the same shared USB
        connection could interleave at the protocol level — narrow (the lock
        holder's critical sections are single scalar reads/writes, not long
        operations) and preferred over a stop() that can hang.
        """
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
            with self._lock_provider():
                return _decode_errors(axis)
        except Exception:
            log.exception("Failed to read/decode axis errors")
            return []

    def _require_axis(self):
        if self._axis is None:
            raise RuntimeError("Not connected to an ODrive device")
        return self._axis
