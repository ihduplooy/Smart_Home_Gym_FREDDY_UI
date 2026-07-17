"""OverloadWrapper — composes over any ResistanceProfile (it is itself one),
multiplying the wrapped profile's torque by `ratio` while the current phase
equals `target_phase`. Defaults to eccentric overload; Tonal's Smart Flex
applies the same mechanism concentrically (planning-session refinement, 16
July), hence the constructor also supports `target_phase=Phase.CONCENTRIC`.

# STUB(2A+): placeholder math — interface shape is the deliverable, per
master plan §9.2/§9.3. The wrapped profile carries its own stub math; this
class only adds the multiply-in-phase behaviour on top.
"""

from typing import Any, Dict, Optional

from config import board_constants

from .base import ResistanceProfile
from .detectors import Phase, ProfileState


class OverloadWrapper(ResistanceProfile):
    name = "overload"
    IS_WRAPPER = True

    def __init__(
        self,
        wrapped: Optional[ResistanceProfile] = None,
        ratio: Optional[float] = None,
        target_phase: Phase = Phase.ECCENTRIC,
    ):
        if wrapped is None:
            # Zero-arg constructibility (needed for registry/schema
            # introspection, spec §7) defaults to wrapping a ConstantProfile.
            # Local import: avoids a real circular import (constant.py
            # doesn't import overload.py), just keeps module-load order
            # flexible regardless of which of the two is imported first.
            from .constant import ConstantProfile

            wrapped = ConstantProfile()
        self.wrapped = wrapped
        self.ratio = ratio if ratio is not None else board_constants.ECCENTRIC_OVERLOAD_RATIO_DEFAULT
        self.target_phase = target_phase

    def compute_torque(self, state: ProfileState) -> float:
        base_torque = self.wrapped.compute_torque(state)
        if state.phase == self.target_phase:
            return base_torque * self.ratio
        return base_torque  # holds and the non-target moving phase: untouched

    def describe(self) -> Dict[str, Any]:
        wrapped_desc = self.wrapped.describe()
        parameters = dict(wrapped_desc["parameters"])
        parameters["ratio"] = {
            "label": "Overload ratio",
            "value": self.ratio,
            "default": board_constants.ECCENTRIC_OVERLOAD_RATIO_DEFAULT,
            "min": 1.0,
            "max": 2.0,
        }
        return {
            "name": self.name,
            "is_wrapper": True,
            "wraps": wrapped_desc["name"],
            "primary_parameter": wrapped_desc["primary_parameter"],
            "parameters": parameters,
            "target_phase": self.target_phase.value,
        }

    @property
    def primary_parameter_label(self) -> str:
        return self.wrapped.primary_parameter_label

    def get_primary_parameter(self) -> float:
        return self.wrapped.get_primary_parameter()

    def set_primary_parameter(self, value: float) -> None:
        # Passes through to the wrapped profile (spec §5.3) -- ratio and
        # target_phase are NOT live-retargetable via this hook.
        self.wrapped.set_primary_parameter(value)

    def reset(self) -> None:
        self.wrapped.reset()
