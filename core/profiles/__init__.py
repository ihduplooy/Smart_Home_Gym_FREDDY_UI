from .base import ResistanceProfile
from .bell_curve import BellCurveProfile
from .constant import ConstantProfile
from .detectors import Phase, PhaseDetector, ProfileState, RepCounter
from .overload import OverloadWrapper
from .vbt import VBTProfile

# Name -> factory (spec §5.3). The backend's /api/profiles route builds its
# entire profile list from this — names are never hardcoded in the frontend.
# `overload` is registered like the other three but is itself a wrapper
# (ResistanceProfile.IS_WRAPPER=True) requiring a base-profile choice; the
# backend composes it server-side over whichever base profile the user picks
# rather than treating it as a fifth standalone profile.
PROFILE_REGISTRY = {
    "constant": ConstantProfile,
    "bell_curve": BellCurveProfile,
    "vbt": VBTProfile,
    "overload": OverloadWrapper,
}

__all__ = [
    "ResistanceProfile",
    "ConstantProfile",
    "BellCurveProfile",
    "VBTProfile",
    "OverloadWrapper",
    "PROFILE_REGISTRY",
    "Phase",
    "PhaseDetector",
    "RepCounter",
    "ProfileState",
]
