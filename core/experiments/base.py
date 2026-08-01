"""Experiment ABC + shared types — Testing tab Build Spec §2.

Mirrors `core/profiles/base.py::ResistanceProfile`'s shape deliberately:
`Experiment` is hardware-free/pure (`step()` returns a torque command, it
never calls `hardware.set_torque_target()` itself) so the state machine is
unit-testable without a fake `HardwareInterface` at all. The actual hardware
write happens one layer up, in `core/experiments/mode.py::ExperimentMode`
(a `BaseMode`), the same split `ProfileMode`/`ResistanceProfile` already use.

This is NOT hardware.set_torque_target-writing like TrainMode's own tick() —
that shape was rejected here specifically so the RAMPING/LIFTING/HOLDING
transition logic (the part most worth testing precisely) doesn't need a
RecordingHardware fake just to exercise it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from core.hardware.interface import TelemetrySample


class ExperimentState(Enum):
    IDLE = "idle"
    CONFIGURED = "configured"
    RAMPING = "ramping"
    LIFTING = "lifting"
    HOLDING = "holding"
    COMPLETE = "complete"
    ABORTED = "aborted"


@dataclass
class ExperimentConfig:
    """Per-run config (Testing tab Build Spec §2.1). `known_weight_kg` is
    reference/logging only — not fed into the control law in v1. The seven
    tuning fields below `initial_torque_nm` default from CableState's
    persisted Testing-tab settings (config/board_constants.py's
    TEST_*_DEFAULT constants) when the frontend builds this — this dataclass
    itself just stores whatever the user confirmed for this one run."""

    known_weight_kg: float
    initial_position_m: float
    target_position_m: float
    initial_torque_nm: float
    torque_ramp_rate_nm_per_s: float
    movement_threshold_m_per_s: float
    hold_deadband_m: float
    hold_gain: float
    max_torque_nm: float
    max_duration_s: float


@dataclass
class ExperimentStepResult:
    torque_command_nm: float
    state: ExperimentState
    extra: Dict[str, Any] = field(default_factory=dict)


class Experiment(ABC):
    name: str = "unnamed"

    @abstractmethod
    def describe(self) -> Dict[str, Any]:
        """Name + config field schema (label/default/min/max per field), for
        the GUI's config form and the `/api/experiments` route — same role
        as ResistanceProfile.describe() plays for `/api/profiles`."""
        ...

    @abstractmethod
    def configure(self, config: ExperimentConfig) -> None:
        """Validate `config` against prerequisites and value ranges; raise
        RuntimeError/ValueError on failure. Does not touch hardware — moves
        the experiment IDLE -> CONFIGURED only."""
        ...

    @abstractmethod
    def start(self) -> None:
        """The explicit, human-confirmed transition CONFIGURED -> RAMPING.
        Called only after the frontend's separate energization-confirmation
        step (Testing tab Build Spec §5) — never implied by configure()."""
        ...

    @abstractmethod
    def step(self, sample: TelemetrySample, elapsed_s: float) -> ExperimentStepResult:
        """One control-loop tick. `elapsed_s` is seconds since start(). Pure:
        reads `sample`, returns the torque to command plus the (possibly
        advanced) state — never calls into a HardwareInterface itself."""
        ...

    @abstractmethod
    def abort(self, reason: str) -> ExperimentStepResult:
        """Force an immediate transition to ABORTED (safety-limit breach or
        an external fault) — returns a zero-torque ExperimentStepResult."""
        ...

    @property
    @abstractmethod
    def state(self) -> ExperimentState:
        ...

    @abstractmethod
    def summary(self) -> Dict[str, Any]:
        """Post-run summary (Testing tab Build Spec §4.8): peak torque, time
        to first movement, time to target, final position error, terminal
        state, abort reason if any."""
        ...
