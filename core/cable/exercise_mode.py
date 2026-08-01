"""ExerciseMode — the single, unified Exercise tab mode. Merges what used to
be two mutually-exclusive ControlSession modes (Layer A's ExerciseMode:
homing/max-extension/moves, and Layer B's ForceMode: concentric force
feedback) into one, after live testing showed the split itself was the
problem: homing/moving and force feedback are used together in one workout,
not as alternatives, and forcing a full session stop/restart between them
(hardware disconnect + reconnect, CSV log rotation) just to switch was the
actual complaint (requested 24 July 2026, see docs/decisions.md).

Runs inside ControlSession's existing 50 Hz loop, following the ProfileMode
precedent (core/control/modes.py) — no second thread, no second rate.

Two parallel state fields, genuinely orthogonal:
  - `_action` ("idle"/"homing"/"moving"/"max_calibrating"): which Layer A
    positioning activity, if any, currently owns the hardware's control loop.
  - `_force_state` (ForceState.ARMED/ENGAGED/HOLDING/FAULT/SETTLING): whether
    force resistance is currently being applied.

Gating between them (this is what removes the old "stop Exercise to use
Force" problem): Layer A actions (home/move/start_max_calibration) require
`_force_state == ARMED` -- reject with a clear error otherwise, no session
stop needed, just Disengage first. `engage` requires `_action == "idle"`.
Because of that gating, `_force_state` can only ever be non-ARMED while
`_action == "idle"` -- so tick()'s force-side branch only runs there, and
hardware writes from the two sides never fight.

Actions (the `value` passed to start()/set_target()) are small dicts:
{"action": "arm" | "home" | "abort_homing" | "start_max_calibration" |
"confirm_max" | "cancel_max_calibration" | "move" | "engage" | "disengage" |
"update_params" | "resume", ...}. "arm" is the only action the backend's
/api/exercise/start route ever sends as the *initial* start() target --
motion/resistance only ever begin from a later, explicit set_target() call.

calibrate_k and reset_position are deliberately NOT actions here -- they
don't need the motor moving and are handled directly against CableState by
backend/app/exercise_routes.py, bypassing ControlSession entirely.
"""

import logging
import math
from enum import Enum
from typing import Any, Dict

from config import board_constants
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles.detectors import CABLE_SIGN, Phase, PhaseDetector
from core.profiles.units import force_to_torque, torque_to_force

from ..control.modes import BaseMode
from .geometry import speed_m_s_from_turns_s
from .governor import governed_force
from .homing import HomingState, HomingStateMachine
from .letgo import LetGoDetector
from .limits import (
    check_position_tiers,
    check_runtime_guard,
    clamp_target_turns,
    clamp_to_home,
    excess_beyond_range,
    validate_homed,
    validate_max_extension_candidate,
)
from .power_limiter import apply_power_limit, estimate_regen_power_w
from .ramps import slew_toward, taper_factor
from .state import CableState

log = logging.getLogger(__name__)

_LAYER_A_ACTIONS = frozenset({
    "arm",
    "home",
    "abort_homing",
    "start_max_calibration",
    "confirm_max",
    "cancel_max_calibration",
    "move",
    # Experimental multi-point spool-growth calibration (train tab
    # calibration overhaul item 4) -- same hold-torque shape as
    # start_max_calibration/cancel_max_calibration above, but recording
    # points doesn't itself need a mode action (backend/app/exercise_routes
    # .py's record_growth_point mutates CableState directly, the same way
    # calibrate_k already does).
    "start_spool_growth_calibration",
    "end_spool_growth_calibration",
})
_FORCE_ACTIONS = frozenset({"engage", "disengage", "update_params", "resume"})
_VALID_ACTIONS = _LAYER_A_ACTIONS | _FORCE_ACTIONS
_VALID_FORCE_MODES = frozenset({"constant", "isokinetic"})

# Position-mode move completion tolerance -- reuses the runtime guard's hard
# tolerance rather than inventing a second small-position-epsilon constant;
# both express "close enough to not matter" at the same physical scale.
_MOVE_DONE_TOLERANCE_TURNS = board_constants.POSITION_GUARD_TOLERANCE_TURNS


class ForceState(Enum):
    ARMED = "armed"
    ENGAGED = "engaged"
    HOLDING = "holding"
    FAULT = "fault"
    # Between a FAULT's Resume and Engage becoming available again: added 24
    # July 2026 after live testing showed Resume->Engage could immediately
    # re-fault -- FAULT's hardware.stop() drives the axis fully IDLE (zero
    # holding torque), so the cable can drift freely for the whole fault
    # window, and re-engaging force fast against whatever velocity that left
    # behind re-triggered the same let-go detector instantly. SETTLING
    # requires measured velocity to sit below the let-go threshold for a
    # debounce window (same shape as LetGoDetector/HomingStateMachine) before
    # Engage is accepted again.
    SETTLING = "settling"


_RESISTING_STATES = (ForceState.ENGAGED, ForceState.HOLDING)


class ExerciseMode(BaseMode):
    hardware_mode = ControlMode.VELOCITY  # initial hardware.set_mode() call; "arm" holds 0
    unit = "exercise"

    def __init__(self, cable_state: CableState):
        self.cable_state = cable_state

        # ---- Layer A (positioning) state ----
        self._action = "idle"
        self._homing_sm = None
        self._move_target_turns = None

        # ---- Layer B (force feedback) state ----
        self._force_state = ForceState.ARMED
        self._phase_detector = PhaseDetector()
        self._letgo = LetGoDetector(cable_state.letgo_velocity_turns_s, cable_state.letgo_debounce_samples)
        self._settle_consecutive = 0

        self._force_mode = "constant"
        self._concentric_force_n = board_constants.FORCE_MIN_N
        self._eccentric_force_n = board_constants.FORCE_MIN_N
        self._isokinetic_velocity_target_turns_s = board_constants.ISOKINETIC_VELOCITY_TARGET_TURNS_S
        # Sub-range of the home->max travel where resistance is active;
        # absolute encoder turns, set at engage/update_params time. None
        # until the first engage -- defaults to the full home->max range
        # there.
        self._range_start_turns = None
        self._range_end_turns = None

        self._filtered_velocity_turns_s = None
        self._commanded_force_n = 0.0
        self._target_force_n = 0.0
        self._hold_start_t = None
        self._last_force_tick_t = None
        self._last_fault_reason = None
        self._power_limiter_active = False
        self._last_regen_power_w = 0.0

    # ---- BaseMode contract ----

    def validate_target(self, value) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError(f"Exercise target must be a dict, got {value!r}")
        action = value.get("action")
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Unknown exercise action: {action!r} (expected one of {sorted(_VALID_ACTIONS)})")
        return value

    def apply_target(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        action = value["action"]
        handler = getattr(self, f"_apply_{action}")
        handler(hardware, value)

    def tick(self, hardware: HardwareInterface, sample: TelemetrySample) -> Dict[str, Any]:
        cable_velocity_turns_s = CABLE_SIGN * sample.velocity  # + = paying out

        # Telemetry that's meaningful regardless of what's currently active;
        # the action-specific branches below may override force_state/
        # commanded_force_n/etc, but these defaults keep every key present
        # on every tick (CSV logger and the frontend both read these
        # unconditionally).
        extra: Dict[str, Any] = {
            "force_state": self._force_state.value,
            "commanded_force_n": 0.0,
            "estimated_force_n": torque_to_force(sample.torque_est, r0=self.cable_state.r0),
            "cable_velocity_m_s": speed_m_s_from_turns_s(cable_velocity_turns_s, self.cable_state.r0),
            "regen_power_w": 0.0,
            "power_limiter_active": False,
            "phase": None,
            "fault_reason": self._last_fault_reason,
            "range_start_length_m": None,
            "range_end_length_m": None,
        }

        # Two-tier position guard (spec: warning band added 24 July 2026 --
        # a hard stop on first overrun was too abrupt). Computed once, up
        # front, so the force branch below can use the warning to actively
        # brake, and the raise at the bottom uses the same result.
        position_warning = False
        position_violated = False
        if self.cable_state.is_homed and self.cable_state.has_max:
            position_warning, position_violated = check_position_tiers(
                sample.position,
                self.cable_state.home_turns,
                self.cable_state.max_turns,
                self.cable_state.position_guard_warning_turns,
                self.cable_state.position_guard_hard_turns,
            )
        extra["position_warning"] = position_warning

        if self._action == "homing" and self._homing_sm is not None:
            self._tick_homing(hardware, sample, extra)
        elif self._action == "moving":
            self._tick_moving(sample, extra)
        elif self._action in ("max_calibrating", "spool_growth_calibrating"):
            self._tick_max_calibrating(hardware)
        elif self._action == "idle":
            self._tick_force(hardware, sample, cable_velocity_turns_s, position_warning, extra)

        if position_violated:
            raise RuntimeError(
                f"Cable position ({sample.position:.4f} turns) left the "
                f"permitted range [home={self.cable_state.home_turns:.4f}, "
                f"max={self.cable_state.max_turns:.4f}] beyond the hard "
                f"tolerance ({self.cable_state.position_guard_hard_turns:.4f}) "
                f"-- safety stop."
            )

        extra["action"] = self._action
        extra["is_homed"] = self.cable_state.is_homed
        extra["has_max"] = self.cable_state.has_max
        extra["home_turns"] = self.cable_state.home_turns
        extra["max_turns"] = self.cable_state.max_turns
        extra["cable_length_m"] = (
            self.cable_state.spool_geometry.length_from_turns_delta(sample.position - self.cable_state.home_turns)
            if self.cable_state.is_homed
            else None
        )
        return extra

    # ---- Layer A action handlers ----

    def _require_layer_a_available(self, action_label: str) -> None:
        if self._action != "idle":
            raise RuntimeError(f"Cannot {action_label} while {self._action}")
        if self._force_state != ForceState.ARMED:
            raise RuntimeError(
                f"Cannot {action_label} while force feedback is {self._force_state.value} -- disengage first"
            )

    def _apply_arm(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        hardware.set_mode(ControlMode.VELOCITY)
        hardware.set_velocity_target(0.0)
        self._action = "idle"

    def _apply_home(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        self._require_layer_a_available("start homing")
        hardware.set_current_limit(self.cable_state.homing_current_limit_a)
        hardware.set_mode(ControlMode.VELOCITY)
        hardware.set_velocity_target(0.0)
        self._homing_sm = HomingStateMachine(
            velocity_turns_s=self.cable_state.homing_velocity_turns_s,
            current_threshold_a=self.cable_state.homing_current_threshold_a,
        )
        self._action = "homing"
        self.cable_state.homing_in_progress = True
        self.cable_state.last_homing_fault = None

    def _apply_abort_homing(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self._action != "homing" or self._homing_sm is None:
            return  # nothing to abort -- safe no-op
        self._homing_sm.abort()
        hardware.set_velocity_target(0.0)
        hardware.set_current_limit(board_constants.MOTOR_CURRENT_LIM)
        self._action = "idle"
        self.cable_state.homing_in_progress = False

    def _apply_start_max_calibration(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        validate_homed(self.cable_state.is_homed)
        self._require_layer_a_available("start max-extension calibration")
        hardware.set_mode(ControlMode.TORQUE)
        hold_torque = force_to_torque(self.cable_state.calib_hold_force_n, r0=self.cable_state.r0)
        hardware.set_torque_target(-CABLE_SIGN * hold_torque)
        self._action = "max_calibrating"
        self.cable_state.max_calibration_in_progress = True

    def _apply_confirm_max(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self._action != "max_calibrating":
            raise RuntimeError("Max-extension calibration is not in progress")
        marked_turns = hardware.get_state().position
        validate_max_extension_candidate(
            marked_turns, self.cable_state.home_turns, board_constants.MAX_EXTENSION_MIN_TRAVEL_TURNS
        )
        self.cable_state.set_max(marked_turns, marked_turns)
        self._end_max_calibration(hardware)

    def _apply_cancel_max_calibration(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self._action != "max_calibrating":
            return  # nothing to cancel -- safe no-op
        self._end_max_calibration(hardware)

    def _end_max_calibration(self, hardware: HardwareInterface) -> None:
        hardware.set_torque_target(0.0)
        hardware.set_mode(ControlMode.VELOCITY)
        hardware.set_velocity_target(0.0)
        self._action = "idle"
        self.cable_state.max_calibration_in_progress = False

    def _apply_start_spool_growth_calibration(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        """Experimental multi-point spool-growth calibration (train tab
        calibration overhaul item 4) -- identical hold-torque shape to
        _apply_start_max_calibration (same calib_hold_force_n, same reason:
        keeps the webbing taut so the encoder reading is trustworthy while
        the user reels out by hand and reads a tape measure at each point).
        Recording/removing/clearing points and the final save are handled
        directly against CableState by backend/app/exercise_routes.py, not
        as further mode actions -- only starting and ending this hold needs
        the motor."""
        validate_homed(self.cable_state.is_homed)
        self._require_layer_a_available("start spool-growth calibration")
        hardware.set_mode(ControlMode.TORQUE)
        hold_torque = force_to_torque(self.cable_state.calib_hold_force_n, r0=self.cable_state.r0)
        hardware.set_torque_target(-CABLE_SIGN * hold_torque)
        self._action = "spool_growth_calibrating"
        self.cable_state.spool_growth_calibration_in_progress = True

    def _apply_end_spool_growth_calibration(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        """Ends the hold started above -- used for both discarding
        (cancel_spool_growth_calibration) and after a successful save
        (save_growth_calibration); which one happened is entirely about
        whether CableState.spool_growth_points was written before this was
        called, not about anything this teardown itself does."""
        if self._action != "spool_growth_calibrating":
            return  # nothing to end -- safe no-op
        hardware.set_torque_target(0.0)
        hardware.set_mode(ControlMode.VELOCITY)
        hardware.set_velocity_target(0.0)
        self._action = "idle"
        self.cable_state.spool_growth_calibration_in_progress = False

    def _apply_move(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        validate_homed(self.cable_state.is_homed)
        if self._action not in ("idle", "moving"):
            raise RuntimeError(f"Cannot move while {self._action}")
        if self._action == "idle" and self._force_state != ForceState.ARMED:
            raise RuntimeError(
                f"Cannot move while force feedback is {self._force_state.value} -- disengage first"
            )

        target_length_m = value.get("target_length_m")
        if isinstance(target_length_m, bool) or not isinstance(target_length_m, (int, float)):
            raise TypeError(f"move requires numeric target_length_m, got {target_length_m!r}")
        if target_length_m < 0:
            raise ValueError(f"target_length_m must be non-negative, got {target_length_m!r}")

        move_velocity = value.get("move_velocity_turns_s", board_constants.TRAP_TRAJ_VEL_LIMIT)
        accel_decel = value.get("accel_decel_turns_s2", board_constants.TRAP_TRAJ_ACCEL_LIMIT)
        for name, v in (("move_velocity_turns_s", move_velocity), ("accel_decel_turns_s2", accel_decel)):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
                raise ValueError(f"{name} must be a positive number, got {v!r}")

        turns_delta = self.cable_state.spool_geometry.turns_delta_from_length(target_length_m)
        target_abs_turns = self.cable_state.home_turns + CABLE_SIGN * turns_delta
        clamped = (
            clamp_target_turns(target_abs_turns, self.cable_state.home_turns, self.cable_state.max_turns)
            if self.cable_state.has_max
            else clamp_to_home(target_abs_turns, self.cable_state.home_turns)
        )

        hardware.set_mode(ControlMode.POSITION)
        hardware.set_position_target(clamped, move_velocity=move_velocity, accel_decel=accel_decel)
        self._move_target_turns = clamped
        self._action = "moving"

    # ---- Layer A tick helpers ----

    def _tick_homing(self, hardware: HardwareInterface, sample: TelemetrySample, extra: Dict[str, Any]) -> None:
        result = self._homing_sm.update(sample.t, sample.current_iq, sample.position)
        hardware.set_velocity_target(result.velocity_command_turns_s)
        extra["homing_state"] = result.state.value

        if result.state == HomingState.HOMED:
            self.cable_state.latch_home(result.home_position_turns)
            hardware.set_current_limit(board_constants.MOTOR_CURRENT_LIM)
            self._action = "idle"
            self.cable_state.homing_in_progress = False
        elif result.state in (HomingState.FAULT_TRAVEL_EXCEEDED, HomingState.FAULT_TIMEOUT):
            hardware.set_current_limit(board_constants.MOTOR_CURRENT_LIM)
            self._action = "idle"
            self.cable_state.homing_in_progress = False
            self.cable_state.last_homing_fault = result.fault_reason
            extra["fault_reason"] = result.fault_reason

    def _tick_moving(self, sample: TelemetrySample, extra: Dict[str, Any]) -> None:
        # TODO(future): the runtime guard's warning tier could also actively
        # slow an in-flight move (re-issue a lower trap_traj velocity) as it
        # approaches the boundary, not just display a warning -- deferred,
        # needs live tuning of how aggressively to decelerate without
        # feeling like a fault.
        if self._move_target_turns is not None and abs(sample.position - self._move_target_turns) < _MOVE_DONE_TOLERANCE_TURNS:
            self._action = "idle"

    def _tick_max_calibrating(self, hardware: HardwareInterface) -> None:
        hold_torque = force_to_torque(self.cable_state.calib_hold_force_n, r0=self.cable_state.r0)
        hardware.set_torque_target(-CABLE_SIGN * hold_torque)

    # ---- Layer B (force feedback) action handlers ----

    def _enter_armed(self, hardware: HardwareInterface) -> None:
        hardware.set_mode(ControlMode.TORQUE)
        hardware.set_torque_target(0.0)
        self._force_state = ForceState.ARMED
        self._commanded_force_n = 0.0
        self._target_force_n = 0.0
        self._power_limiter_active = False

    def _apply_engage(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self._action != "idle":
            raise RuntimeError(f"Cannot engage while {self._action}")
        if self._force_state != ForceState.ARMED:
            raise RuntimeError(f"Cannot engage while {self._force_state.value}")
        validate_homed(self.cable_state.is_homed)

        hardware.set_mode(ControlMode.TORQUE)
        self._set_force_params(value)

        self._filtered_velocity_turns_s = None
        self._letgo = LetGoDetector(self.cable_state.letgo_velocity_turns_s, self.cable_state.letgo_debounce_samples)
        self._phase_detector.reset()
        self._hold_start_t = None
        self._force_state = ForceState.ENGAGED

    def _apply_update_params(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self._force_state not in _RESISTING_STATES:
            raise RuntimeError(f"Cannot update force parameters while {self._force_state.value}")
        self._set_force_params(value)

    def _set_force_params(self, value: Dict[str, Any]) -> None:
        mode = value.get("mode", self._force_mode)
        if mode not in _VALID_FORCE_MODES:
            raise ValueError(f"Unknown force mode: {mode!r} (expected one of {sorted(_VALID_FORCE_MODES)})")

        concentric_force_n = value.get("concentric_force_n")
        eccentric_force_n = value.get("eccentric_force_n")
        for label, v in (("concentric_force_n", concentric_force_n), ("eccentric_force_n", eccentric_force_n)):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise ValueError(f"{label} must be a non-negative number, got {v!r}")
            if v > board_constants.FORCE_MAX_N:
                raise ValueError(f"{label} {v!r} exceeds FORCE_MAX_N={board_constants.FORCE_MAX_N}")

        velocity_target = value.get("velocity_target_turns_s", self._isokinetic_velocity_target_turns_s)
        if mode == "isokinetic":
            if isinstance(velocity_target, bool) or not isinstance(velocity_target, (int, float)) or velocity_target <= 0:
                raise ValueError(f"velocity_target_turns_s must be a positive number, got {velocity_target!r}")

        range_start_turns, range_end_turns = self._resolve_range(
            value.get("start_length_m"), value.get("end_length_m")
        )

        self._force_mode = mode
        self._concentric_force_n = float(concentric_force_n)
        self._eccentric_force_n = float(eccentric_force_n)
        self._isokinetic_velocity_target_turns_s = float(velocity_target)
        self._range_start_turns = range_start_turns
        self._range_end_turns = range_end_turns

    def _resolve_range(self, start_length_m, end_length_m):
        home_turns = self.cable_state.home_turns
        max_turns = self.cable_state.max_turns  # may be None -- max extension is optional

        if start_length_m is None:
            start_turns = home_turns
        else:
            if isinstance(start_length_m, bool) or not isinstance(start_length_m, (int, float)) or start_length_m < 0:
                raise ValueError(f"start_length_m must be a non-negative number, got {start_length_m!r}")
            start_turns = home_turns + CABLE_SIGN * self.cable_state.spool_geometry.turns_delta_from_length(start_length_m)

        if end_length_m is None:
            if max_turns is None:
                raise ValueError(
                    "No max extension is calibrated -- end_length_m must be given explicitly to engage "
                    "force feedback without one."
                )
            end_turns = max_turns
        else:
            if isinstance(end_length_m, bool) or not isinstance(end_length_m, (int, float)) or end_length_m < 0:
                raise ValueError(f"end_length_m must be a non-negative number, got {end_length_m!r}")
            end_turns = home_turns + CABLE_SIGN * self.cable_state.spool_geometry.turns_delta_from_length(end_length_m)

        start_clamped, end_clamped = sorted((start_turns, end_turns), key=lambda t: t * CABLE_SIGN)

        if max_turns is not None:
            lo, hi = min(home_turns, max_turns), max(home_turns, max_turns)
            if not (lo - 1e-9 <= start_clamped <= hi + 1e-9) or not (lo - 1e-9 <= end_clamped <= hi + 1e-9):
                raise ValueError(
                    f"Force range must fall within the calibrated [home, max] travel -- "
                    f"got a range that falls outside it."
                )
        elif (start_clamped - home_turns) * CABLE_SIGN < -1e-9 or (end_clamped - home_turns) * CABLE_SIGN < -1e-9:
            raise ValueError("Force range must not extend past home in the retract direction.")

        if abs(end_clamped - start_clamped) < 1e-9:
            raise ValueError("Force range start and end must not be the same point.")
        return start_clamped, end_clamped

    def _apply_disengage(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self._force_state not in _RESISTING_STATES:
            return  # nothing to disengage -- safe no-op
        self._force_state = ForceState.ARMED
        self._hold_start_t = None
        # _commanded_force_n ramps to 0 via tick()'s ARMED target, not stepped.

    def _apply_resume(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self._force_state != ForceState.FAULT:
            raise RuntimeError("Not in FAULT -- nothing to resume")
        self._last_fault_reason = None
        hardware.set_mode(ControlMode.TORQUE)
        hardware.set_torque_target(0.0)
        self._force_state = ForceState.SETTLING
        self._settle_consecutive = 0
        self._commanded_force_n = 0.0
        self._target_force_n = 0.0
        self._power_limiter_active = False

    # ---- Layer B tick ----

    def _tick_force(
        self,
        hardware: HardwareInterface,
        sample: TelemetrySample,
        cable_velocity_turns_s: float,
        position_warning: bool,
        extra: Dict[str, Any],
    ) -> None:
        now = sample.t
        dt = 0.0 if self._last_force_tick_t is None else max(0.0, now - self._last_force_tick_t)
        self._last_force_tick_t = now

        if self._force_state == ForceState.SETTLING:
            self._tick_settling(cable_velocity_turns_s)
        elif self._force_state == ForceState.ENGAGED:
            self._tick_engaged(hardware, sample, cable_velocity_turns_s, position_warning, extra)
        elif self._force_state == ForceState.HOLDING:
            self._target_force_n = board_constants.FORCE_MIN_N
        elif self._force_state == ForceState.ARMED:
            self._target_force_n = 0.0
        # FAULT: _target_force_n left at whatever it was (irrelevant -- never
        # applied below; commanded force was already forced to 0 on entry).

        final_force = 0.0
        if self._force_state != ForceState.FAULT:
            rate = board_constants.FORCE_MAX_N / (
                self.cable_state.force_ramp_in_s
                if self._target_force_n >= self._commanded_force_n
                else self.cable_state.force_ramp_out_s
            )
            self._commanded_force_n = slew_toward(self._commanded_force_n, self._target_force_n, rate * dt)

        if self._force_state in _RESISTING_STATES:
            cable_velocity_m_s = speed_m_s_from_turns_s(cable_velocity_turns_s, self.cable_state.r0)
            limited_force, active = apply_power_limit(
                self._commanded_force_n,
                cable_velocity_m_s,
                board_constants.REGEN_POWER_BUDGET_W,
                board_constants.MOTOR_TORQUE_CONSTANT,
                board_constants.MOTOR_PHASE_RESISTANCE_OHM,
                self.cable_state.r0,
            )
            self._power_limiter_active = active
            self._last_regen_power_w = estimate_regen_power_w(
                limited_force, cable_velocity_m_s,
                board_constants.MOTOR_TORQUE_CONSTANT, board_constants.MOTOR_PHASE_RESISTANCE_OHM,
                self.cable_state.r0,
            )
            final_force = limited_force
            signed_torque = -CABLE_SIGN * force_to_torque(final_force, r0=self.cable_state.r0)
            hardware.set_torque_target(signed_torque)
        else:
            self._power_limiter_active = False
            hardware.set_torque_target(0.0)

        extra["force_state"] = self._force_state.value
        extra["commanded_force_n"] = final_force
        extra["regen_power_w"] = self._last_regen_power_w if self._force_state in _RESISTING_STATES else 0.0
        extra["power_limiter_active"] = self._power_limiter_active
        extra["fault_reason"] = self._last_fault_reason
        if self._range_start_turns is not None and self._range_end_turns is not None:
            home_turns = self.cable_state.home_turns
            extra["range_start_length_m"] = self.cable_state.spool_geometry.length_from_turns_delta(
                self._range_start_turns - home_turns
            )
            extra["range_end_length_m"] = self.cable_state.spool_geometry.length_from_turns_delta(
                self._range_end_turns - home_turns
            )

    def _tick_settling(self, cable_velocity_turns_s: float) -> None:
        threshold = self.cable_state.letgo_velocity_turns_s
        if abs(cable_velocity_turns_s) < threshold:
            self._settle_consecutive += 1
        else:
            self._settle_consecutive = 0
        if self._settle_consecutive >= int(self.cable_state.letgo_debounce_samples):
            self._force_state = ForceState.ARMED
            self._settle_consecutive = 0
        self._target_force_n = 0.0

    def _tick_engaged(
        self,
        hardware: HardwareInterface,
        sample: TelemetrySample,
        cable_velocity_turns_s: float,
        position_warning: bool,
        extra: Dict[str, Any],
    ) -> None:
        if self._letgo.update(sample.velocity):
            hardware.stop()
            self._force_state = ForceState.FAULT
            self._last_fault_reason = (
                "Let-go detected: sustained reel-in velocity beyond the configured threshold -- hard stop."
            )
            self._commanded_force_n = 0.0
            self._target_force_n = 0.0
            extra["fault_reason"] = self._last_fault_reason
            return

        phase = self._phase_detector.update(sample.velocity)
        extra["phase"] = phase.value

        if phase in (Phase.TOP_HOLD, Phase.BOTTOM_HOLD):
            if self._hold_start_t is None:
                self._hold_start_t = sample.t
            elif sample.t - self._hold_start_t >= self.cable_state.hold_duration_s:
                self._force_state = ForceState.HOLDING
                self._hold_start_t = None
                self._target_force_n = board_constants.FORCE_MIN_N
                return
        else:
            self._hold_start_t = None

        alpha = self.cable_state.isokinetic_velocity_filter_alpha
        self._filtered_velocity_turns_s = (
            cable_velocity_turns_s
            if self._filtered_velocity_turns_s is None
            else alpha * cable_velocity_turns_s + (1 - alpha) * self._filtered_velocity_turns_s
        )

        # Phase-aware target: concentric (pulling out) and eccentric
        # (controlled return) each get their own configured force (spec:
        # requested 24 July 2026 -- "separate configurable force for
        # eccentric", real cable-machine behaviour). Only genuine, actively-
        # moving ECCENTRIC uses the eccentric target; CONCENTRIC and BOTH
        # hold phases use concentric -- BOTTOM_HOLD is "at rest, about to
        # pull" (PhaseDetector's own starting phase, before any movement has
        # happened at all), not itself part of a return stroke, so
        # defaulting it to eccentric would apply the wrong force the moment
        # a session is engaged and nothing has moved yet. Eccentric's
        # governing velocity is sign-flipped so governed_force's ">target =>
        # resist harder" logic reads the same way against reel-in speed as
        # it does against pay-out speed for concentric.
        if phase == Phase.ECCENTRIC:
            base_force_n = self._eccentric_force_n
            governing_velocity = -self._filtered_velocity_turns_s
        else:  # CONCENTRIC, TOP_HOLD, or BOTTOM_HOLD
            base_force_n = self._concentric_force_n
            governing_velocity = self._filtered_velocity_turns_s

        if self._force_mode == "isokinetic":
            base_force = governed_force(
                velocity_turns_s=governing_velocity,
                velocity_target_turns_s=self._isokinetic_velocity_target_turns_s,
                force_base_n=base_force_n,
                force_max_n=board_constants.FORCE_MAX_N,
                governor_gain=self.cable_state.isokinetic_governor_gain,
            )
        else:
            base_force = min(base_force_n, board_constants.FORCE_MAX_N)

        taper = 1.0
        if self._range_start_turns is not None and self._range_end_turns is not None:
            home_turns = self.cable_state.home_turns
            geo = self.cable_state.spool_geometry
            length_to_current = geo.length_from_turns_delta(sample.position - home_turns)
            length_to_end = geo.length_from_turns_delta(self._range_end_turns - home_turns)
            distance_from_end_edge_m = length_to_end - length_to_current
            end_taper = taper_factor(distance_from_end_edge_m, self.cable_state.max_extension_force_taper_m)
            if math.isclose(self._range_start_turns, home_turns, abs_tol=1e-9):
                start_taper = 1.0
            else:
                length_to_start = geo.length_from_turns_delta(self._range_start_turns - home_turns)
                distance_from_start_edge_m = length_to_current - length_to_start
                start_taper = taper_factor(distance_from_start_edge_m, self.cable_state.max_extension_force_taper_m)
            taper = min(start_taper, end_taper)

        target = base_force * taper

        # Active braking (spec: warning tier added 24 July 2026) -- once the
        # measured position has left [home, max] beyond the warning
        # tolerance (but not yet the hard tolerance that stops the session
        # outright), ease resistance UP toward the physical limit instead of
        # the comfort taper's ease-DOWN, to help decelerate the user rather
        # than just cutting out. Torque here always pulls inward (toward
        # home) regardless of phase, so boosting it is directionally safe
        # for the common case (past max, still extending) and a mild,
        # harmless added tension in the less common one (past home).
        if position_warning and self.cable_state.has_max:
            excess = excess_beyond_range(sample.position, self.cable_state.home_turns, self.cable_state.max_turns)
            span = max(self.cable_state.position_guard_hard_turns - self.cable_state.position_guard_warning_turns, 1e-9)
            brake_frac = min(1.0, max(0.0, excess - self.cable_state.position_guard_warning_turns) / span)
            brake_force = board_constants.FORCE_MIN_N + brake_frac * (board_constants.FORCE_MAX_N - board_constants.FORCE_MIN_N)
            target = max(target, brake_force)

        self._target_force_n = target
