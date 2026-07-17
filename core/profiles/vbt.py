"""VBTProfile — auto-regulation structural stub.

# STUB(2A+): placeholder math — interface shape is the deliverable, per
master plan §9.2/§9.3. The point of this stub is the per-REP update cadence
(not per-tick): the mean concentric velocity of the previous *completed* rep
is compared against a target band and nudges an internal resistance scalar
by a fixed step. Set/workout-level logic (Tonal-Burnout-style) is explicitly
out of scope here (spec §10/§11).
"""

from typing import Any, Dict

from .base import ResistanceProfile
from .detectors import Phase, ProfileState
from .units import force_to_torque

DEFAULT_BASE_FORCE_N = 100.0
DEFAULT_V_LOW = 0.3
DEFAULT_V_HIGH = 0.6
DEFAULT_ADJUST_STEP = 0.05


class VBTProfile(ResistanceProfile):
    name = "vbt"

    def __init__(
        self,
        base_force_n: float = DEFAULT_BASE_FORCE_N,
        v_low: float = DEFAULT_V_LOW,
        v_high: float = DEFAULT_V_HIGH,
        adjust_step: float = DEFAULT_ADJUST_STEP,
    ):
        self.base_force_n = float(base_force_n)
        self.v_low = float(v_low)
        self.v_high = float(v_high)
        self.adjust_step = float(adjust_step)
        self._scalar = 1.0
        self._last_rep_count = 0
        self._concentric_v_sum = 0.0
        self._concentric_v_ticks = 0

    def compute_torque(self, state: ProfileState) -> float:
        if state.phase == Phase.CONCENTRIC:
            self._concentric_v_sum += abs(state.velocity)
            self._concentric_v_ticks += 1

        if state.rep_count != self._last_rep_count:
            self._finalize_completed_rep()
            self._last_rep_count = state.rep_count

        return force_to_torque(self.base_force_n * self._scalar)

    def _finalize_completed_rep(self) -> None:
        """Per-rep update: adjusts the scalar once, using the mean
        concentric velocity accumulated over the rep that just ended."""
        if self._concentric_v_ticks > 0:
            mean_v = self._concentric_v_sum / self._concentric_v_ticks
            if mean_v < self.v_low:
                self._scalar = max(0.0, self._scalar - self.adjust_step)
            elif mean_v > self.v_high:
                self._scalar += self.adjust_step
            # else: in band, hold scalar unchanged.
        self._concentric_v_sum = 0.0
        self._concentric_v_ticks = 0

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "is_wrapper": False,
            "primary_parameter": "base_force_n",
            "parameters": {
                "base_force_n": {
                    "label": "Base force (N)",
                    "value": self.base_force_n,
                    "default": DEFAULT_BASE_FORCE_N,
                    "min": 0.0,
                    "max": 500.0,
                },
                "v_low": {
                    "label": "Target velocity low (turns/s)",
                    "value": self.v_low,
                    "default": DEFAULT_V_LOW,
                    "min": 0.0,
                    "max": 5.0,
                },
                "v_high": {
                    "label": "Target velocity high (turns/s)",
                    "value": self.v_high,
                    "default": DEFAULT_V_HIGH,
                    "min": 0.0,
                    "max": 5.0,
                },
                "adjust_step": {
                    "label": "Adjust step (fraction)",
                    "value": self.adjust_step,
                    "default": DEFAULT_ADJUST_STEP,
                    "min": 0.0,
                    "max": 1.0,
                },
            },
        }

    @property
    def primary_parameter_label(self) -> str:
        return "base force (N)"

    def get_primary_parameter(self) -> float:
        return self.base_force_n

    def set_primary_parameter(self, value: float) -> None:
        self.base_force_n = float(value)

    def reset(self) -> None:
        self._scalar = 1.0
        self._last_rep_count = 0
        self._concentric_v_sum = 0.0
        self._concentric_v_ticks = 0
