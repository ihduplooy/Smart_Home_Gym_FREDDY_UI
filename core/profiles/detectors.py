"""Phase detection and rep counting for the resistance-profile layer.

Sign convention (decided once here, used everywhere in core/profiles/):
**positive cable velocity = cable paying out = concentric (lifting).** The
sim's positive-torque-produces-positive-velocity behaviour maps onto this
directly. `CABLE_SIGN` is the one-line flip point if Phase 2A's real cable
rigging turns out to invert this (e.g. velocity sign flips depending on which
side of a pulley the encoder reads) — multiply raw velocity by `CABLE_SIGN`
before any phase logic, nowhere else.

Both `PhaseDetector` and `RepCounter` are pure functions of successive
samples plus their own small internal state — no wall-clock dependency —
which is what makes them unit-testable with synthetic sequences (spec §8.1)
independent of the sim's real-time behaviour.
"""

from dataclasses import dataclass
from enum import Enum

from config import board_constants
from core.hardware.interface import TelemetrySample

CABLE_SIGN = 1


class Phase(Enum):
    CONCENTRIC = "concentric"
    TOP_HOLD = "top_hold"
    ECCENTRIC = "eccentric"
    BOTTOM_HOLD = "bottom_hold"


@dataclass
class ProfileState:
    t: float
    position: float
    velocity: float
    phase: Phase
    rep_count: int
    sample: TelemetrySample


class PhaseDetector:
    """Velocity-sign phase detector with hysteresis on exit from a hold.

    Starts in BOTTOM_HOLD (a rep is assumed to begin at rest, cable
    retracted, before the first concentric pull). While moving
    (CONCENTRIC/ECCENTRIC), |v| dropping below `PHASE_VEL_THRESHOLD_TURNS_S`
    enters the hold matching that moving phase (after concentric ->
    TOP_HOLD, after eccentric -> BOTTOM_HOLD). Leaving a hold, or reversing
    direction outright, requires clearing
    `PHASE_VEL_THRESHOLD_TURNS_S + PHASE_HYSTERESIS_TURNS_S` so noise sitting
    right at the threshold can't flicker the phase back and forth.
    """

    def __init__(self):
        self._phase = Phase.BOTTOM_HOLD

    def reset(self) -> None:
        self._phase = Phase.BOTTOM_HOLD

    @property
    def phase(self) -> Phase:
        return self._phase

    def update(self, velocity: float) -> Phase:
        v = CABLE_SIGN * velocity
        threshold = board_constants.PHASE_VEL_THRESHOLD_TURNS_S
        exit_threshold = threshold + board_constants.PHASE_HYSTERESIS_TURNS_S

        if self._phase in (Phase.CONCENTRIC, Phase.ECCENTRIC):
            if abs(v) < threshold:
                self._phase = Phase.TOP_HOLD if self._phase == Phase.CONCENTRIC else Phase.BOTTOM_HOLD
            elif self._phase == Phase.CONCENTRIC and v < -exit_threshold:
                self._phase = Phase.ECCENTRIC
            elif self._phase == Phase.ECCENTRIC and v > exit_threshold:
                self._phase = Phase.CONCENTRIC
            # else: keep the current moving phase's label (still moving the
            # same direction, or not yet past the reversal hysteresis).
        else:  # currently in a hold
            if v > exit_threshold:
                self._phase = Phase.CONCENTRIC
            elif v < -exit_threshold:
                self._phase = Phase.ECCENTRIC
            # else: stay in the current hold.

        return self._phase


class RepCounter:
    """Counts a rep when position *returns* within `REP_PROXIMITY_TURNS` of
    its own EWMA while sitting in BOTTOM_HOLD, having (a) passed through a
    CONCENTRIC phase and (b) moved at least `REP_PROXIMITY_TURNS` away from
    that EWMA, since the last count.

    (a) is the phase gate from spec §5.1: it stops jitter-at-rest from being
    counted as reps. (b) is needed alongside it: right at the start of a
    concentric phase, position and its own slow EWMA are still numerically
    close together (both sitting near the previous rep's baseline) for
    several ticks before they diverge, which would otherwise fire spurious
    counts before the rep has gone anywhere.

    Gating the final check on BOTTOM_HOLD specifically (rather than "any
    tick where distance < proximity") is a necessary addition beyond the
    literal spec text: an EWMA lagging a smooth position curve is briefly
    close to that curve near *any* local extremum, including the top of the
    rep, not just the bottom -- confirmed empirically via
    core/tests/test_detectors.py while building this. Requiring BOTTOM_HOLD
    also means "close to its own EWMA" is doing real work rather than being
    redundant with the phase check: BOTTOM_HOLD alone can fire on a mid-range
    pause after any eccentric movement, so the position/EWMA proximity check
    confirms that pause is actually near the rep's established baseline.
    """

    def __init__(self):
        self._ewma = None
        self._rep_count = 0
        self._seen_concentric_since_last_count = False
        self._left_proximity_since_last_count = False

    def reset(self) -> None:
        self._ewma = None
        self._rep_count = 0
        self._seen_concentric_since_last_count = False
        self._left_proximity_since_last_count = False

    @property
    def rep_count(self) -> int:
        return self._rep_count

    def update(self, position: float, phase: Phase) -> int:
        alpha = board_constants.REP_EWMA_ALPHA
        self._ewma = position if self._ewma is None else alpha * position + (1 - alpha) * self._ewma

        if phase == Phase.CONCENTRIC:
            self._seen_concentric_since_last_count = True

        proximity = board_constants.REP_PROXIMITY_TURNS
        distance = abs(position - self._ewma)
        if distance >= proximity:
            self._left_proximity_since_last_count = True

        if (
            phase == Phase.BOTTOM_HOLD
            and self._seen_concentric_since_last_count
            and self._left_proximity_since_last_count
            and distance < proximity
        ):
            self._rep_count += 1
            self._seen_concentric_since_last_count = False
            self._left_proximity_since_last_count = False

        return self._rep_count
