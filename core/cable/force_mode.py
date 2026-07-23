"""ForceMode — Exercise tab Layer B, Session B1 (concentric force feedback)
ControlSession integration (exercise_tab_build_spec_layerB.md §3, §4, §8).

Separate from ExerciseMode (§8 architecture decision, logged in full in
docs/decisions.md): ExerciseMode is already sizeable, dedicated to Layer A's
brief, one-shot calibration actions, and switches ODrive control modes
within a session. ForceMode is structurally different -- fixed to torque
control for its entire lifecycle (spec §3, the load-bearing decision of this
whole layer), but runs a sustained, continuous, multi-component force
computation every tick (governor, let-go detector, power limiter, ramps).
Shares CableState with ExerciseMode via the same mode_factories hook; the
two are mutually-exclusive sibling modes on the one ControlSession, exactly
like Control/Profiles/Exercise already are.

State machine:

    (start, action="arm") -> ARMED  [zero torque]
    ARMED --"engage"--> ENGAGED_CONCENTRIC
    ENGAGED_CONCENTRIC --sustained hold phase for HOLD_DURATION_S--> HOLDING
    {ENGAGED_CONCENTRIC, HOLDING} --"disengage"--> ARMED  [ramped to 0]
    ENGAGED_CONCENTRIC --let-go detector fires--> FAULT  [hardware.stop(): immediate, not ramped]
    FAULT --"resume"--> ARMED  [force params preserved, home/max untouched]
    any state, Layer A's runtime guard trips -> raises inside tick() -> full ControlSession auto-stop

No separate IDLE state (matches ExerciseMode's own precedent -- ControlSession's
running/not-running already covers "not started"). FAULT is deliberately NOT
implemented via the raise-inside-tick() auto-stop path Layer A's runtime
guard uses: spec §4.6 frames "resume" as lighter than re-homing, returning
"the state machine" (not a fresh session) to ARMED -- so ControlSession stays
running through a FAULT, and only Layer A's runtime guard (a more severe,
position-is-wrong failure) triggers the full-session-stop mechanism.
"""

import logging
from enum import Enum
from typing import Any, Dict

from config import board_constants
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles.detectors import CABLE_SIGN, Phase, PhaseDetector
from core.profiles.units import force_to_torque, torque_to_force

from ..control.modes import BaseMode
from .geometry import length_from_turns_delta, speed_m_s_from_turns_s
from .governor import governed_force
from .letgo import LetGoDetector
from .limits import check_runtime_guard, validate_homed
from .power_limiter import apply_power_limit, estimate_regen_power_w
from .ramps import slew_toward, taper_factor
from .state import CableState

log = logging.getLogger(__name__)


class ForceState(Enum):
    ARMED = "armed"
    ENGAGED_CONCENTRIC = "engaged_concentric"
    HOLDING = "holding"
    FAULT = "fault"


_VALID_ACTIONS = frozenset({"arm", "engage", "disengage", "update_params", "resume"})
_VALID_FORCE_MODES = frozenset({"constant", "isokinetic"})

_RESISTING_STATES = (ForceState.ENGAGED_CONCENTRIC, ForceState.HOLDING)


class ForceMode(BaseMode):
    hardware_mode = ControlMode.TORQUE  # fixed for the whole session (spec §3)
    unit = "force"

    def __init__(self, cable_state: CableState):
        self.cable_state = cable_state
        self.state = ForceState.ARMED

        self._phase_detector = PhaseDetector()
        self._letgo = LetGoDetector()

        self._force_mode = "constant"
        # force_n_param serves double duty: the flat target in constant mode,
        # F_base in isokinetic mode (spec §4.3 -- "F_base may be zero ... or
        # non-zero"). One field, not two, because they're the same
        # user-facing "how much resistance" input regardless of mode.
        self._force_n_param = board_constants.FORCE_MIN_N
        self._isokinetic_velocity_target_turns_s = board_constants.ISOKINETIC_VELOCITY_TARGET_TURNS_S

        self._filtered_velocity_turns_s = None
        self._commanded_force_n = 0.0
        self._target_force_n = 0.0
        self._hold_start_t = None
        self._last_tick_t = None
        self._last_fault_reason = None
        self._power_limiter_active = False
        self._last_regen_power_w = 0.0

    # ---- BaseMode contract ----

    def validate_target(self, value) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError(f"Force target must be a dict, got {value!r}")
        action = value.get("action")
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Unknown force action: {action!r} (expected one of {sorted(_VALID_ACTIONS)})")
        return value

    def apply_target(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        action = value["action"]
        handler = getattr(self, f"_apply_{action}")
        handler(hardware, value)

    def tick(self, hardware: HardwareInterface, sample: TelemetrySample) -> Dict[str, Any]:
        now = sample.t
        dt = 0.0 if self._last_tick_t is None else max(0.0, now - self._last_tick_t)
        self._last_tick_t = now

        extra: Dict[str, Any] = {"fault_reason": self._last_fault_reason}
        cable_velocity_turns_s = CABLE_SIGN * sample.velocity  # + = paying out

        if self.state == ForceState.ENGAGED_CONCENTRIC:
            self._tick_engaged(hardware, sample, cable_velocity_turns_s, extra)
        elif self.state == ForceState.HOLDING:
            self._target_force_n = board_constants.FORCE_MIN_N
        elif self.state == ForceState.ARMED:
            self._target_force_n = 0.0
        # FAULT: _target_force_n left at whatever it was (irrelevant -- never
        # applied below; commanded force was already forced to 0 on entry).

        final_force = 0.0
        if self.state != ForceState.FAULT:
            rate = board_constants.FORCE_MAX_N / (
                board_constants.FORCE_RAMP_IN_S
                if self._target_force_n >= self._commanded_force_n
                else board_constants.FORCE_RAMP_OUT_S
            )
            self._commanded_force_n = slew_toward(self._commanded_force_n, self._target_force_n, rate * dt)

        if self.state in _RESISTING_STATES:
            cable_velocity_m_s = speed_m_s_from_turns_s(cable_velocity_turns_s, board_constants.SPOOL_RADIUS_M)
            limited_force, active = apply_power_limit(
                self._commanded_force_n,
                cable_velocity_m_s,
                board_constants.REGEN_POWER_BUDGET_W,
                board_constants.MOTOR_TORQUE_CONSTANT,
                board_constants.MOTOR_PHASE_RESISTANCE_OHM,
                board_constants.SPOOL_RADIUS_M,
            )
            self._power_limiter_active = active
            self._last_regen_power_w = estimate_regen_power_w(
                limited_force, cable_velocity_m_s,
                board_constants.MOTOR_TORQUE_CONSTANT, board_constants.MOTOR_PHASE_RESISTANCE_OHM,
                board_constants.SPOOL_RADIUS_M,
            )
            final_force = limited_force
            signed_torque = -CABLE_SIGN * force_to_torque(final_force)
            hardware.set_torque_target(signed_torque)
        elif self.state == ForceState.ARMED:
            self._power_limiter_active = False
            hardware.set_torque_target(0.0)
        elif self.state == ForceState.FAULT:
            self._power_limiter_active = False
            hardware.set_torque_target(0.0)

        # Layer A's runtime guard (spec §4.5: "Layer B must not bypass them") --
        # unconditional, regardless of ForceMode's own state. Raising here is
        # caught by ControlSession's existing telemetry-loop try/except, the
        # same auto-stop path Layer A's ExerciseMode already uses.
        if self.cable_state.is_homed and self.cable_state.has_max:
            violated = check_runtime_guard(
                sample.position, self.cable_state.home_turns, self.cable_state.max_turns,
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

        extra["force_state"] = self.state.value
        extra["commanded_force_n"] = final_force
        extra["estimated_force_n"] = torque_to_force(sample.torque_est)
        extra["cable_velocity_m_s"] = speed_m_s_from_turns_s(cable_velocity_turns_s, board_constants.SPOOL_RADIUS_M)
        extra["regen_power_w"] = self._last_regen_power_w if self.state in _RESISTING_STATES else 0.0
        extra["power_limiter_active"] = self._power_limiter_active
        extra["fault_reason"] = self._last_fault_reason
        return extra

    # ---- action handlers ----

    def _enter_armed(self, hardware: HardwareInterface) -> None:
        hardware.set_mode(ControlMode.TORQUE)
        hardware.set_torque_target(0.0)
        self.state = ForceState.ARMED
        self._commanded_force_n = 0.0
        self._target_force_n = 0.0
        self._power_limiter_active = False

    def _apply_arm(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        self._enter_armed(hardware)

    def _apply_engage(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self.state != ForceState.ARMED:
            raise RuntimeError(f"Cannot engage while {self.state.value}")
        validate_homed(self.cable_state.is_homed)
        if not self.cable_state.has_max:
            raise RuntimeError("Max extension is not set -- cannot engage force resistance until calibrated")

        self._set_force_params(value)

        self._filtered_velocity_turns_s = None
        self._letgo.reset()
        self._phase_detector.reset()
        self._hold_start_t = None
        self.state = ForceState.ENGAGED_CONCENTRIC

    def _apply_update_params(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self.state not in _RESISTING_STATES:
            raise RuntimeError(f"Cannot update force parameters while {self.state.value}")
        self._set_force_params(value)

    def _set_force_params(self, value: Dict[str, Any]) -> None:
        mode = value.get("mode", self._force_mode)
        if mode not in _VALID_FORCE_MODES:
            raise ValueError(f"Unknown force mode: {mode!r} (expected one of {sorted(_VALID_FORCE_MODES)})")

        force_n = value.get("force_n")
        if isinstance(force_n, bool) or not isinstance(force_n, (int, float)) or force_n < 0:
            raise ValueError(f"force_n must be a non-negative number, got {force_n!r}")
        if force_n > board_constants.FORCE_MAX_N:
            raise ValueError(f"force_n {force_n!r} exceeds FORCE_MAX_N={board_constants.FORCE_MAX_N}")

        velocity_target = value.get("velocity_target_turns_s", self._isokinetic_velocity_target_turns_s)
        if mode == "isokinetic":
            if isinstance(velocity_target, bool) or not isinstance(velocity_target, (int, float)) or velocity_target <= 0:
                raise ValueError(f"velocity_target_turns_s must be a positive number, got {velocity_target!r}")

        self._force_mode = mode
        self._force_n_param = float(force_n)
        self._isokinetic_velocity_target_turns_s = float(velocity_target)

    def _apply_disengage(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self.state not in _RESISTING_STATES:
            return  # nothing to disengage -- safe no-op
        self.state = ForceState.ARMED
        self._letgo.reset()
        self._hold_start_t = None
        # _commanded_force_n ramps to 0 via tick()'s ARMED target, not stepped.

    def _apply_resume(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self.state != ForceState.FAULT:
            raise RuntimeError("Not in FAULT -- nothing to resume")
        self._last_fault_reason = None
        self._enter_armed(hardware)

    # ---- tick helpers ----

    def _tick_engaged(
        self, hardware: HardwareInterface, sample: TelemetrySample, cable_velocity_turns_s: float, extra: Dict[str, Any]
    ) -> None:
        if self._letgo.update(sample.velocity):
            hardware.stop()
            self.state = ForceState.FAULT
            self._last_fault_reason = (
                "Let-go detected: sustained reel-in velocity during concentric resistance -- hard stop."
            )
            self._commanded_force_n = 0.0
            self._target_force_n = 0.0
            extra["fault_reason"] = self._last_fault_reason
            return

        phase = self._phase_detector.update(sample.velocity)
        if phase in (Phase.TOP_HOLD, Phase.BOTTOM_HOLD):
            if self._hold_start_t is None:
                self._hold_start_t = sample.t
            elif sample.t - self._hold_start_t >= board_constants.HOLD_DURATION_S:
                self.state = ForceState.HOLDING
                self._hold_start_t = None
                self._target_force_n = board_constants.FORCE_MIN_N
                return
        else:
            self._hold_start_t = None

        alpha = board_constants.ISOKINETIC_VELOCITY_FILTER_ALPHA
        self._filtered_velocity_turns_s = (
            cable_velocity_turns_s
            if self._filtered_velocity_turns_s is None
            else alpha * cable_velocity_turns_s + (1 - alpha) * self._filtered_velocity_turns_s
        )

        if self._force_mode == "isokinetic":
            base_force = governed_force(
                velocity_turns_s=self._filtered_velocity_turns_s,
                velocity_target_turns_s=self._isokinetic_velocity_target_turns_s,
                force_base_n=self._force_n_param,
                force_max_n=board_constants.FORCE_MAX_N,
                governor_gain=board_constants.ISOKINETIC_GOVERNOR_GAIN,
            )
        else:
            base_force = min(self._force_n_param, board_constants.FORCE_MAX_N)

        taper = 1.0
        if self.cable_state.has_max:
            turns_to_max = self.cable_state.max_turns - self.cable_state.home_turns
            turns_to_current = sample.position - self.cable_state.home_turns
            length_to_max = length_from_turns_delta(turns_to_max, self.cable_state.r0, self.cable_state.k)
            length_to_current = length_from_turns_delta(turns_to_current, self.cable_state.r0, self.cable_state.k)
            distance_to_limit_m = length_to_max - length_to_current
            taper = taper_factor(distance_to_limit_m, board_constants.MAX_EXTENSION_FORCE_TAPER_M)

        self._target_force_n = base_force * taper
