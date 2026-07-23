"""ExerciseMode — Exercise tab Layer A's ControlSession integration
(exercise_tab_build_spec_layerA.md §2.2, §3, §4).

Runs inside ControlSession's existing 50 Hz loop, following the ProfileMode
precedent (core/control/modes.py) — no second thread, no second rate.

One respect this deviates from that precedent in, because ControlSession
itself doesn't support it yet: unlike Velocity/Torque/Profile, which stay in
one ODrive control mode for the whole session, Exercise switches between
velocity (homing), torque (max-extension hold), and position (length moves)
*within* one session, as the user issues different actions. ControlSession
only ever calls hardware.set_mode() once, at start() — so this mode calls
hardware.set_mode() itself, from apply_target()/tick(), whenever the action
changes.

Actions (the `value` passed to start()/set_target()) are small dicts:
{"action": "arm" | "home" | "abort_homing" | "start_max_calibration" |
"confirm_max" | "cancel_max_calibration" | "move", ...}. "arm" is the only
action the backend's /api/exercise/start route ever sends as the *initial*
start() target — motion only ever begins from a later, explicit set_target()
call (spec §4 item 1: no motion from session start).

calibrate_k and reset_position are deliberately NOT actions here — they
don't need the motor moving (spec §3.3, §3.5) and are handled directly
against CableState by backend/app/exercise_routes.py, bypassing
ControlSession entirely (reset in particular must work while idle, i.e.
while nothing is running at all).
"""

import logging
from typing import Any, Dict

from config import board_constants
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles.detectors import CABLE_SIGN
from core.profiles.units import force_to_torque

from ..control.modes import BaseMode
from .geometry import length_from_turns_delta, turns_delta_from_length
from .homing import HomingState, HomingStateMachine
from .limits import check_runtime_guard, clamp_target_turns, validate_homed, validate_max_extension_candidate
from .state import CableState

log = logging.getLogger(__name__)

_VALID_ACTIONS = frozenset({
    "arm",
    "home",
    "abort_homing",
    "start_max_calibration",
    "confirm_max",
    "cancel_max_calibration",
    "move",
})

# Position-mode move completion tolerance -- reuses the runtime guard
# tolerance rather than inventing a second small-position-epsilon constant;
# both express "close enough to not matter" at the same physical scale.
_MOVE_DONE_TOLERANCE_TURNS = board_constants.POSITION_GUARD_TOLERANCE_TURNS


class ExerciseMode(BaseMode):
    hardware_mode = ControlMode.VELOCITY  # initial hardware.set_mode() call; "arm" holds 0
    unit = "exercise"

    def __init__(self, cable_state: CableState):
        self.cable_state = cable_state
        self._homing_sm = None
        self._action = "idle"
        self._move_target_turns = None

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
        extra: Dict[str, Any] = {}

        if self._action == "homing" and self._homing_sm is not None:
            self._tick_homing(hardware, sample, extra)
        elif self._action == "moving":
            self._tick_moving(sample, extra)

        # Runtime guard (spec §3.4 mechanism 2, §4 item 6): meaningful only
        # once both home and max are established. Raising here is caught by
        # ControlSession's existing telemetry-loop try/except (the same path
        # a raising profile already goes through) -- auto-stops the session
        # and surfaces the reason in status()["error_message"], with no new
        # plumbing needed.
        if self.cable_state.is_homed and self.cable_state.has_max:
            violated = check_runtime_guard(
                sample.position,
                self.cable_state.home_turns,
                self.cable_state.max_turns,
                board_constants.POSITION_GUARD_TOLERANCE_TURNS,
            )
            if violated:
                raise RuntimeError(
                    f"Cable position ({sample.position:.4f} turns) left the "
                    f"permitted range [home={self.cable_state.home_turns:.4f}, "
                    f"max={self.cable_state.max_turns:.4f}] beyond tolerance "
                    f"({board_constants.POSITION_GUARD_TOLERANCE_TURNS:.4f}) -- "
                    f"safety stop."
                )

        extra["action"] = self._action
        extra["is_homed"] = self.cable_state.is_homed
        extra["has_max"] = self.cable_state.has_max
        extra["home_turns"] = self.cable_state.home_turns
        extra["max_turns"] = self.cable_state.max_turns
        extra["cable_length_m"] = (
            length_from_turns_delta(sample.position - self.cable_state.home_turns, self.cable_state.r0, self.cable_state.k)
            if self.cable_state.is_homed
            else None
        )
        return extra

    # ---- action handlers (apply_target dispatch) ----

    def _apply_arm(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        hardware.set_mode(ControlMode.VELOCITY)
        hardware.set_velocity_target(0.0)
        self._action = "idle"

    def _apply_home(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self._action == "homing":
            raise RuntimeError("Homing is already in progress")
        if self._action == "max_calibrating":
            raise RuntimeError("Cannot start homing while max-extension calibration is in progress")
        hardware.set_current_limit(board_constants.HOMING_CURRENT_LIMIT_A)
        hardware.set_mode(ControlMode.VELOCITY)
        hardware.set_velocity_target(0.0)
        self._homing_sm = HomingStateMachine()
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
        if self._action != "idle":
            raise RuntimeError(f"Cannot start max-extension calibration while {self._action}")
        hardware.set_mode(ControlMode.TORQUE)
        # Tension pulls toward home (reel-in direction) so the cable stays
        # taut against the user pulling it out -- the one force->torque
        # conversion site (spec §3.2), reusing core/profiles/units.py.
        hold_torque = force_to_torque(board_constants.CALIB_HOLD_FORCE_N)
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
        margin_turns = turns_delta_from_length(
            board_constants.MAX_EXTENSION_SAFETY_MARGIN_M, self.cable_state.r0, self.cable_state.k
        )
        enforced_turns = marked_turns - CABLE_SIGN * margin_turns
        self.cable_state.set_max(marked_turns, enforced_turns)
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

    def _apply_move(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        validate_homed(self.cable_state.is_homed)
        if not self.cable_state.has_max:
            raise RuntimeError("Max extension is not set -- cannot move until calibrated")
        if self._action not in ("idle", "moving"):
            raise RuntimeError(f"Cannot move while {self._action}")

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

        turns_delta = turns_delta_from_length(target_length_m, self.cable_state.r0, self.cable_state.k)
        target_abs_turns = self.cable_state.home_turns + CABLE_SIGN * turns_delta
        clamped = clamp_target_turns(target_abs_turns, self.cable_state.home_turns, self.cable_state.max_turns)

        hardware.set_mode(ControlMode.POSITION)
        hardware.set_position_target(clamped, move_velocity=move_velocity, accel_decel=accel_decel)
        self._move_target_turns = clamped
        self._action = "moving"

    # ---- tick helpers ----

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
        if self._move_target_turns is not None and abs(sample.position - self._move_target_turns) < _MOVE_DONE_TOLERANCE_TURNS:
            self._action = "idle"
