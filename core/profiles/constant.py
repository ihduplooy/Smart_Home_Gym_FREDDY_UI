from typing import Any, Dict

from .base import ResistanceProfile
from .detectors import ProfileState
from .units import force_to_torque

DEFAULT_BASE_FORCE_N = 100.0
MIN_BASE_FORCE_N = 0.0
MAX_BASE_FORCE_N = 500.0


class ConstantProfile(ResistanceProfile):
    """The one stub that's actually trivially "real": constant cable force,
    converted straight to torque. Everything else here is the interface
    shape other stubs share."""

    name = "constant"

    def __init__(self, base_force_n: float = DEFAULT_BASE_FORCE_N):
        self.base_force_n = float(base_force_n)

    def compute_torque(self, state: ProfileState) -> float:
        return force_to_torque(self.base_force_n)

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
                    "min": MIN_BASE_FORCE_N,
                    "max": MAX_BASE_FORCE_N,
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
