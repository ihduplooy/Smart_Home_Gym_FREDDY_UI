"""ExperimentMode — the Testing tab's ControlSession-facing adapter (Testing
tab Build Spec §2.3/§5). Lives in core/experiments/ (not core/control/modes.py)
following TrainMode's own precedent (core/cable/train_mode.py) for "a BaseMode
subclass that belongs to a sibling core/ package, injected with the shared
CableState" -- core/experiments/ importing core/control/core/cable is a
core-to-core dependency, not a core->backend one, so this doesn't violate the
package's "must not import backend/" rule.

Two-phase action dispatch, mirroring TrainMode's `_apply_<action>` convention
and ExerciseMode's existing "arm with zero motion, then a later explicit
action for real motion" convention (`exercise_start`):
  - "configure": builds the Experiment from the registry, validates the
    config, holds torque at 0. No energization yet -- this is what makes the
    motor-energization gate (spec §5) structural rather than a UI-only
    promise: the motor genuinely cannot move between Configure and Confirm.
  - "confirm_start": the one explicit, human-confirmed action that begins
    RAMPING. Called only by the frontend's separate "Confirm & Energize
    Motor" button, never implied by "configure".

tick() calls hardware.stop() directly, in the same tick, the instant the
experiment's own step() reports COMPLETE or ABORTED -- an immediate safe
shutdown, not deferred to a later frontend-triggered Stop call (spec §5:
"any breach forces immediate ABORTED + safe shutdown"). Hardware/encoder
errors mid-run are NOT special-cased here: ControlSession._telemetry_loop's
existing generic get_errors() -> auto-stop path (used identically by every
other mode) already provides "transition to safe shutdown, don't try to
recover" -- see docs/decisions.md for the one caveat this leaves (the CSV's
last experiment_state row before such a stop reflects whatever phase was
active, not a literal "aborted" label; the session-level errored/
error_message fields are what surface that case, same as every other mode).
"""

from typing import Any, Dict

from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample

from ..control.modes import BaseMode
from .base import ExperimentConfig, ExperimentState
from .registry import EXPERIMENT_REGISTRY
from .telemetry import estimated_power_w

_VALID_ACTIONS = frozenset({"configure", "confirm_start"})

_CONFIG_FIELDS = (
    "known_weight_kg",
    "initial_position_m",
    "target_position_m",
    "initial_torque_nm",
    "torque_ramp_rate_nm_per_s",
    "movement_threshold_m_per_s",
    "hold_deadband_m",
    "hold_gain",
    "max_torque_nm",
    "max_duration_s",
)


def _build_config(data: Dict[str, Any]) -> ExperimentConfig:
    if not isinstance(data, dict):
        raise TypeError(f"'config' must be a dict, got {data!r}")
    values = {}
    for key in _CONFIG_FIELDS:
        if key not in data:
            raise ValueError(f"Experiment config missing required field '{key}'")
        v = data[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise TypeError(f"Experiment config field '{key}' must be numeric, got {v!r}")
        values[key] = float(v)
    return ExperimentConfig(**values)


class ExperimentMode(BaseMode):
    hardware_mode = ControlMode.TORQUE
    unit = "experiment"

    def __init__(self, cable_state):
        self.cable_state = cable_state
        self.experiment = None
        self._experiment_name = None
        self._t0 = None

    # ---- BaseMode contract ----

    def validate_target(self, value) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError(f"Experiment target must be a dict, got {value!r}")
        action = value.get("action")
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Unknown experiment action: {action!r} (expected one of {sorted(_VALID_ACTIONS)})")

        if action == "configure":
            experiment_name = value.get("experiment")
            factory = EXPERIMENT_REGISTRY.get(experiment_name)
            if factory is None:
                raise ValueError(
                    f"Unknown experiment: {experiment_name!r} (expected one of {list(EXPERIMENT_REGISTRY)})"
                )
            config = _build_config(value.get("config") or {})
            return {"action": action, "experiment": experiment_name, "config": config}

        return {"action": action}

    def apply_target(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        action = value["action"]
        getattr(self, f"_apply_{action}")(hardware, value)

    def status_target(self, validated_value: Dict[str, Any]):
        if validated_value["action"] == "configure":
            return {"experiment": validated_value["experiment"], "action": "configure"}
        return {"action": "confirm_start"}

    def csv_log_name(self, mode: str) -> str:
        name = self.experiment.name if self.experiment is not None else "unknown"
        return f"{mode}-{name}"

    # ---- action handlers ----

    def _apply_configure(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        factory = EXPERIMENT_REGISTRY[value["experiment"]]
        experiment = factory(self.cable_state)
        experiment.configure(value["config"])
        self.experiment = experiment
        self._experiment_name = value["experiment"]
        hardware.set_torque_target(0.0)

    def _apply_confirm_start(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        if self.experiment is None:
            raise RuntimeError("No experiment configured -- configure() first")
        self.experiment.start()

    # ---- tick ----

    def tick(self, hardware: HardwareInterface, sample: TelemetrySample) -> Dict[str, Any]:
        if self.experiment is None:
            return {}

        state = self.experiment.state
        if state in (ExperimentState.IDLE, ExperimentState.CONFIGURED):
            hardware.set_torque_target(0.0)
            return {"experiment_state": state.value}

        if state in (ExperimentState.COMPLETE, ExperimentState.ABORTED):
            # Run already ended on a previous tick, before the frontend's
            # next poll got a chance to call Stop -- hold safe.
            hardware.set_torque_target(0.0)
            return {"experiment_state": state.value, **self.experiment.summary()}

        if self._t0 is None:
            self._t0 = sample.t

        result = self.experiment.step(sample, sample.t - self._t0)
        hardware.set_torque_target(result.torque_command_nm)

        if result.state in (ExperimentState.COMPLETE, ExperimentState.ABORTED):
            hardware.stop()  # immediate safe shutdown, same tick as the breach/timeout

        return {
            "experiment_state": result.state.value,
            "commanded_torque_nm": result.torque_command_nm,
            "bus_voltage_v": sample.bus_voltage_v,
            "estimated_power_w": estimated_power_w(sample),
            **result.extra,
        }
