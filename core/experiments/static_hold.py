"""StaticWeightHoldExperiment — Testing tab Build Spec §2.2-§2.4.

RAMPING -> LIFTING -> HOLDING -> COMPLETE/ABORTED, torque-mode throughout
(per Ivan's instruction: base this on torque control, not velocity/position,
since torque is already proven for Control/Profiles/Train).

Sign convention (flag, not fixed — same "verify at the bench" treatment as
CABLE_SIGN/enable_torque_mode_vel_limit elsewhere in this project): torque is
commanded exactly as configured, with NO CABLE_SIGN flip applied — unlike
TrainMode's tension-resisting logic, this experiment's torque is a direct
user-facing value (the config literally says "starting torque command"), not
a force derived from cable tension. Whether a positive initial_torque_nm
actually lifts (vs. lowers) the attached weight is bench-rig dependent and
UNCONFIRMED until the first live run.

Spec §2.2/§2.3's COMPLETE-vs-ABORTED text is internally inconsistent: COMPLETE
is defined as "user-initiated stop or timeout elapses," but ABORTED's own
bullet lists max_duration_s among the safety limits that trigger ABORTED.
Resolved here in favor of COMPLETE's own, more specific definition: a
max_duration_s timeout ends the run as COMPLETE (a graceful, planned end),
while a max_torque_nm breach (an active fault, not a planned end) is what
triggers ABORTED. Flagged in docs/decisions.md rather than silently picking
one.
"""

from typing import Any, Dict, Optional

from core.cable.geometry import speed_m_s_from_turns_s
from core.cable.limits import validate_homed
from core.cable.state import CableState
from core.hardware.interface import TelemetrySample

from .base import Experiment, ExperimentConfig, ExperimentState, ExperimentStepResult


class StaticWeightHoldExperiment(Experiment):
    name = "static_hold"

    def __init__(self, cable_state: CableState):
        self.cable_state = cable_state
        self._state = ExperimentState.IDLE
        self._config: Optional[ExperimentConfig] = None
        self._home_turns: Optional[float] = None
        self._max_length_m: Optional[float] = None

        self._torque_at_movement_onset: Optional[float] = None
        self._base_holding_torque: Optional[float] = None
        self._elapsed_at_movement: Optional[float] = None
        self._elapsed_at_target: Optional[float] = None
        self._peak_torque_nm = 0.0
        self._last_position_m: Optional[float] = None
        self._last_velocity_m_s: Optional[float] = None
        self._last_position_error_m: Optional[float] = None
        self._abort_reason: Optional[str] = None
        self._complete_reason: Optional[str] = None

    # ---- Experiment contract ----

    def describe(self) -> Dict[str, Any]:
        cs = self.cable_state

        def _param(label, value, minimum=None, maximum=None):
            return {"label": label, "value": value, "default": value, "min": minimum, "max": maximum}

        return {
            "name": self.name,
            "label": "Static Weight Hold",
            "parameters": {
                "known_weight_kg": _param("Known weight (kg)", 0.0, minimum=0.0),
                "target_position_m": _param("Target position (m, from home)", 0.0, minimum=0.0),
                "initial_torque_nm": _param(
                    "Initial torque (Nm)", cs.test_initial_torque_nm, minimum=0.0, maximum=cs.test_max_torque_nm
                ),
                "torque_ramp_rate_nm_per_s": _param(
                    "Torque ramp rate (Nm/s)", cs.test_torque_ramp_rate_nm_per_s, minimum=0.0
                ),
                "movement_threshold_m_per_s": _param(
                    "Movement threshold (m/s)", cs.test_movement_threshold_m_per_s, minimum=0.0
                ),
                "hold_deadband_m": _param("Hold deadband (m)", cs.test_hold_deadband_m, minimum=0.0),
                "hold_gain": _param("Hold gain (Nm/m)", cs.test_hold_gain, minimum=0.0),
                "max_torque_nm": _param("Max torque (Nm)", cs.test_max_torque_nm, minimum=0.0),
                "max_duration_s": _param("Max duration (s)", cs.test_max_duration_s, minimum=0.0),
            },
        }

    def configure(self, config: ExperimentConfig) -> None:
        validate_homed(self.cable_state.is_homed)
        if not self.cable_state.has_max:
            raise RuntimeError(
                "Cable has no calibrated max extension -- complete max-extension "
                "calibration in the Train tab before configuring an experiment."
            )

        if config.torque_ramp_rate_nm_per_s <= 0:
            raise ValueError(f"torque_ramp_rate_nm_per_s must be positive, got {config.torque_ramp_rate_nm_per_s!r}")
        if config.movement_threshold_m_per_s <= 0:
            raise ValueError(f"movement_threshold_m_per_s must be positive, got {config.movement_threshold_m_per_s!r}")
        if config.hold_deadband_m <= 0:
            raise ValueError(f"hold_deadband_m must be positive, got {config.hold_deadband_m!r}")
        if config.hold_gain < 0:
            raise ValueError(f"hold_gain must be non-negative, got {config.hold_gain!r}")
        if config.max_torque_nm <= 0:
            raise ValueError(f"max_torque_nm must be positive, got {config.max_torque_nm!r}")
        if config.max_duration_s <= 0:
            raise ValueError(f"max_duration_s must be positive, got {config.max_duration_s!r}")
        if abs(config.initial_torque_nm) > config.max_torque_nm:
            raise ValueError(
                f"initial_torque_nm ({config.initial_torque_nm!r}) must not exceed "
                f"max_torque_nm ({config.max_torque_nm!r})."
            )

        home_turns = self.cable_state.home_turns
        max_length_m = self.cable_state.spool_geometry.length_from_turns_delta(
            self.cable_state.max_turns - home_turns
        )
        if not (0.0 <= config.target_position_m <= max_length_m):
            raise ValueError(
                f"target_position_m ({config.target_position_m!r}) is outside the "
                f"calibrated travel range [0, {max_length_m!r}] m from home."
            )

        self._config = config
        self._home_turns = home_turns
        self._max_length_m = max_length_m
        self._state = ExperimentState.CONFIGURED

    def start(self) -> None:
        if self._state != ExperimentState.CONFIGURED:
            raise RuntimeError(f"Cannot start from state {self._state.value!r} -- configure() first")
        self._state = ExperimentState.RAMPING

    def step(self, sample: TelemetrySample, elapsed_s: float) -> ExperimentStepResult:
        if self._state in (ExperimentState.COMPLETE, ExperimentState.ABORTED):
            return ExperimentStepResult(0.0, self._state, self._extra())

        config = self._config
        position_m = self.cable_state.spool_geometry.length_from_turns_delta(sample.position - self._home_turns)
        velocity_m_s = speed_m_s_from_turns_s(sample.velocity, self.cable_state.r0)
        self._last_position_m = position_m
        self._last_velocity_m_s = velocity_m_s

        if elapsed_s >= config.max_duration_s:
            self._complete_reason = "max_duration_s elapsed"
            self._state = ExperimentState.COMPLETE
            return ExperimentStepResult(0.0, self._state, self._extra())

        if self._state == ExperimentState.RAMPING:
            commanded = config.initial_torque_nm + config.torque_ramp_rate_nm_per_s * elapsed_s
            if abs(velocity_m_s) > config.movement_threshold_m_per_s:
                self._torque_at_movement_onset = commanded
                self._elapsed_at_movement = elapsed_s
                self._state = ExperimentState.LIFTING
        elif self._state == ExperimentState.LIFTING:
            commanded = self._torque_at_movement_onset
            if abs(position_m - config.target_position_m) <= config.hold_deadband_m:
                self._elapsed_at_target = elapsed_s
                self._base_holding_torque = commanded
                self._state = ExperimentState.HOLDING
        elif self._state == ExperimentState.HOLDING:
            # Deliberate v1 simplification (spec §2.4): proportional-only, no
            # integral/derivative term. The 0-floor clamp is spec-literal, not
            # an oversight -- an overshoot above target can only be corrected
            # by torque decaying toward zero, never by commanding negative
            # torque, which is a real limitation worth re-visiting once this
            # runs against a real weight.
            position_error = config.target_position_m - position_m
            self._last_position_error_m = position_error
            commanded = self._base_holding_torque + config.hold_gain * position_error
            commanded = max(0.0, min(config.max_torque_nm, commanded))
        else:
            commanded = 0.0

        self._peak_torque_nm = max(self._peak_torque_nm, abs(commanded))

        if abs(commanded) > config.max_torque_nm:
            self._abort_reason = (
                f"commanded torque {commanded:.4f} Nm exceeded max_torque_nm {config.max_torque_nm:.4f}"
            )
            self._state = ExperimentState.ABORTED
            return ExperimentStepResult(0.0, self._state, self._extra())

        return ExperimentStepResult(commanded, self._state, self._extra())

    def abort(self, reason: str) -> ExperimentStepResult:
        self._abort_reason = reason
        self._state = ExperimentState.ABORTED
        return ExperimentStepResult(0.0, self._state, self._extra())

    @property
    def state(self) -> ExperimentState:
        return self._state

    def summary(self) -> Dict[str, Any]:
        return {
            "state": self._state.value,
            "peak_torque_nm": self._peak_torque_nm,
            "time_to_first_movement_s": self._elapsed_at_movement,
            "time_to_target_s": self._elapsed_at_target,
            "final_position_error_m": self._last_position_error_m,
            "abort_reason": self._abort_reason,
            "complete_reason": self._complete_reason,
        }

    # ---- helpers ----

    def _extra(self) -> Dict[str, Any]:
        return {
            "position_m": self._last_position_m,
            "velocity_m_s": self._last_velocity_m_s,
            "target_position_m": self._config.target_position_m if self._config else None,
        }
