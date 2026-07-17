"""BellCurveProfile — position-dependent stiffness K(x) shape.

# STUB(2A+): placeholder math — interface shape is the deliverable, per
master plan §9.2/§9.3. `curve_factor` is a raised-cosine bump, injectable at
construction so Phase 2A+ can swap in measured strength-curve data (the Son
et al. joint-angle/torque table in the charter) without touching the rest of
the profile.
"""

import math
from typing import Any, Callable, Dict, Optional

from .base import ResistanceProfile
from .detectors import ProfileState
from .units import force_to_torque

DEFAULT_BASE_FORCE_N = 100.0
DEFAULT_X_START = 0.0
DEFAULT_X_END = 1.0
DEFAULT_PEAK_MULTIPLIER = 1.5


class BellCurveProfile(ResistanceProfile):
    name = "bell_curve"

    def __init__(
        self,
        base_force_n: float = DEFAULT_BASE_FORCE_N,
        x_start: float = DEFAULT_X_START,
        x_end: float = DEFAULT_X_END,
        peak_multiplier: float = DEFAULT_PEAK_MULTIPLIER,
        curve_factor: Optional[Callable[[float], float]] = None,
    ):
        self.base_force_n = float(base_force_n)
        self.x_start = float(x_start)
        self.x_end = float(x_end)
        self.peak_multiplier = float(peak_multiplier)
        # Injectable/replaceable callable (spec §5.3) -- default is a smooth
        # placeholder bump; 2A+ replaces this with measured curve data.
        self.curve_factor: Callable[[float], float] = curve_factor or self._default_curve_factor

    def _default_curve_factor(self, position: float) -> float:
        """Raised-cosine bump: 1.0 (no change) at/outside [x_start, x_end],
        rising smoothly to `peak_multiplier` at the midpoint."""
        if position <= self.x_start or position >= self.x_end or self.x_end <= self.x_start:
            return 1.0
        span = self.x_end - self.x_start
        normalized = (position - self.x_start) / span  # 0..1
        bump = 0.5 * (1 - math.cos(2 * math.pi * normalized))  # 0 at edges, 1 at center
        return 1.0 + (self.peak_multiplier - 1.0) * bump

    def compute_torque(self, state: ProfileState) -> float:
        factor = self.curve_factor(state.position)
        return force_to_torque(self.base_force_n * factor)

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
                "x_start": {
                    "label": "Curve start position (turns)",
                    "value": self.x_start,
                    "default": DEFAULT_X_START,
                    "min": -10.0,
                    "max": 10.0,
                },
                "x_end": {
                    "label": "Curve end position (turns)",
                    "value": self.x_end,
                    "default": DEFAULT_X_END,
                    "min": -10.0,
                    "max": 10.0,
                },
                "peak_multiplier": {
                    "label": "Peak multiplier",
                    "value": self.peak_multiplier,
                    "default": DEFAULT_PEAK_MULTIPLIER,
                    "min": 1.0,
                    "max": 3.0,
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
        pass
