"""Let-go detector — Exercise tab Layer B, Session B1
(exercise_tab_build_spec_layerB.md §4.4, §6 items 3/4).

Pure logic, same shape as core/cable/homing.py's debounce: if the user
releases the handle mid-concentric, the resisting torque has nothing
opposing it and accelerates the spool in the reel-in direction. Detection is
sustained reel-in velocity for N consecutive samples — debounced the same
way homing's threshold-crossing is, so a single noisy sample can't trigger
what the spec calls for as a hard stop (zero torque, brake, FAULT, manual
resume required — not a controlled reel-in).

This detector is deliberately dumb about *when* it should be active — that
is a state-gating responsibility of the caller (force_mode.py), not this
class (spec §4.4: "must be active in concentric only... gate it on state,
and test that gating explicitly"). Calling .reset() when leaving concentric
is how the caller prevents a stale debounce count from carrying into a
later re-engagement.
"""

from config import board_constants
from core.profiles.detectors import CABLE_SIGN


class LetGoDetector:
    def __init__(self):
        self._consecutive = 0
        self._threshold = board_constants.LETGO_VELOCITY_TURNS_S
        self._debounce_samples = board_constants.LETGO_DEBOUNCE_SAMPLES

    def reset(self) -> None:
        self._consecutive = 0

    def update(self, cable_velocity_turns_s: float) -> bool:
        """Returns True once sustained reel-in has been observed for the
        debounce window -- callers should treat True as "fire now" (the
        hard-stop response), not as an ongoing state to poll indefinitely;
        call reset() after handling it (or after leaving concentric)."""
        signed = CABLE_SIGN * cable_velocity_turns_s
        if signed < -self._threshold:
            self._consecutive += 1
        else:
            self._consecutive = 0
        return self._consecutive >= self._debounce_samples
