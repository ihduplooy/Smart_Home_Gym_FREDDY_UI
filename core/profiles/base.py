"""ResistanceProfile ABC — the contract every profile (real or stub) and the
OverloadWrapper composition must satisfy.

`describe()` is written to also serve as the source for the backend's
`GET /api/profiles` parameter schema (spec §7): each parameter entry carries
`label`/`value`/`default`/`min`/`max`, not just a current value, so the
backend can build schema-driven form inputs from a single call on a
default-constructed instance, never hardcoding parameter shape in the
frontend.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from .detectors import ProfileState


class ResistanceProfile(ABC):
    name: str = "unnamed"

    # True only for OverloadWrapper — lets the registry/backend route flag
    # "this entry composes over another profile" without needing a second,
    # separately-maintained list (spec §7's "whether it's a wrapper").
    IS_WRAPPER = False

    @abstractmethod
    def compute_torque(self, state: ProfileState) -> float:
        """The whole contract. Returns Nm."""
        ...

    @abstractmethod
    def describe(self) -> Dict[str, Any]:
        """Name + current parameters (schema: label/value/default/min/max
        per parameter), for the GUI and the /api/profiles route."""
        ...

    @property
    @abstractmethod
    def primary_parameter_label(self) -> str:
        """e.g. "base force (N)" — the live-retarget hook's display label."""
        ...

    @abstractmethod
    def get_primary_parameter(self) -> float:
        """Current value of the live-retargetable primary parameter."""
        ...

    @abstractmethod
    def set_primary_parameter(self, value: float) -> None:
        """Live-retarget hook (spec §3): adjusts the profile in place, never
        replaces the profile object mid-run."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Called on session start; clears any internal state (e.g. VBT's
        per-rep accumulator)."""
        ...
