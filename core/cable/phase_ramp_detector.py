"""phase_ramp_detector.py -- Concentric/eccentric phase detection for the
resistance-modes sub-phase 4 ("constant + inertia + band" doc's follow-up).
Pure, hardware-free, standalone (train_tab_build_spec convention, same as
core/cable/train_profiles.py: no config/board_constants import, no
CableState) -- a small function-shaped state machine, deliberately NOT a
subclass or variant of core/profiles/detectors.py's own `PhaseDetector`.

That existing detector (used by ExerciseMode/Force Feedback) is a simpler
single-threshold velocity-hysteresis machine with four phases (CONCENTRIC/
TOP_HOLD/ECCENTRIC/BOTTOM_HOLD) and no notion of a smooth force transition --
exactly right for its own job (phase-gated rep counting), but this feature
needs two things it doesn't have: a *dual* debounce (both a minimum sustained
velocity AND a minimum distance traveled in the new direction, specifically
to reject "a brief pause-and-continue being mistaken for a direction
change" -- sub-phase 4 doc §3), and a smooth 0.0-1.0 ramp/blend progress
value once a flip commits, so commanded force glides between the concentric
and eccentric values instead of jumping. Building a second, dedicated
detector keeps that existing one, and everything that already depends on its
exact behavior (rep counting, isokinetic governing), completely unchanged.

Sign convention matches core/profiles/detectors.py's own documented one:
positive velocity = cable paying out = concentric. Callers pass already
CABLE_SIGN-corrected, metres-based cable_velocity_m_s/cable_length_m (what
TrainMode already computes every tick), not raw encoder turns.
"""

from dataclasses import dataclass

CONCENTRIC = "concentric"
ECCENTRIC = "eccentric"
_OPPOSITE = {CONCENTRIC: ECCENTRIC, ECCENTRIC: CONCENTRIC}

# Tunable constants -- module-level defaults only. Live use (TrainMode) reads
# CableState's copies instead (inertia_kg_max/phase_* settings, set via
# set_phase_settings() -- GYM's Settings sub-tab, resistance-modes sub-phase
# 4 follow-up), passed into update() below as keyword overrides each tick;
# these five stay as the fallback for standalone/test use and as what a fresh
# CableState seeds itself from (config/board_constants.py's own
# PHASE_*_DEFAULT constants mirror these exact values -- keep both in sync by
# hand if either changes).
#
# Data-grounded, not guessed: simulated against a real ~124s train-constant
# session (logs/telemetry_20260917_143634_train-constant_real.csv, genuine
# hardware pulls, not sim) -- this exact dual-debounce design produced 35
# transitions, cleanly alternating concentric/eccentric with zero
# same-direction double-flips, median ~1.2s apart (consistent with real rep
# tempo, including a couple of multi-second rest gaps between sets). A naive
# single-threshold sign check against the same data produced 494 "reversals"
# at a median 0.12s apart -- almost all encoder-noise flicker -- which is
# exactly the failure mode this dual debounce exists to reject.
# RAMP_DURATION_S is the one constant that can't be validated from a log
# (it's a *feel* parameter, not a detection-accuracy one) -- bench-test at
# slow and fast rep tempo per the doc's own acceptance criteria before
# trusting this default; it's exactly the kind of value the GYM Settings
# sub-tab exists to let a real bench session adjust without a code change.
VELOCITY_DEADBAND_M_S = 0.05
MIN_SUSTAINED_VELOCITY_M_S = 0.08
SUSTAIN_WINDOW_S = 0.15
REVERSAL_DISTANCE_M = 0.03
RAMP_DURATION_S = 0.15


@dataclass(frozen=True)
class PhaseRampState:
    """`phase` is the current (post-commit) direction; `previous_phase` is
    whichever phase is being ramped away from -- equal to `phase` once
    `ramp_progress` reaches 1.0. A caller blends force as:
    `lerp(force[previous_phase], force[phase], ramp_progress)` -- this
    module only ever deals in phase labels/progress, never force units
    itself (kept unit-agnostic on purpose; TrainMode owns the N-valued
    blend)."""

    phase: str
    previous_phase: str
    ramp_progress: float


class PhaseRampDetector:
    """update(position_m, velocity_m_s, t) each tick -> PhaseRampState.

    Starts committed to CONCENTRIC (a rep is assumed to begin at rest before
    the first concentric pull, same starting assumption core/profiles/
    detectors.py's PhaseDetector makes for BOTTOM_HOLD) with no ramp in
    progress. A flip only commits once the opposite direction's velocity has
    both (a) stayed above MIN_SUSTAINED_VELOCITY_M_S for SUSTAIN_WINDOW_S
    continuously, and (b) covered REVERSAL_DISTANCE_M of net travel in that
    direction since it first looked like a candidate -- either condition
    resetting (a pause, a return to the original direction, or even
    lingering in the deadband) throws away ALL candidate progress, not just
    pausing it, which is what makes a pause-and-continue safe (see
    test_phase_ramp_detector.py)."""

    def __init__(self):
        self._phase = CONCENTRIC
        self._previous_phase = CONCENTRIC
        self._ramp_start_t = None
        self._candidate_phase = None
        self._candidate_start_t = None
        self._candidate_start_position_m = None

    def reset(self) -> None:
        self.__init__()

    def update(
        self,
        position_m: float,
        velocity_m_s: float,
        t: float,
        *,
        velocity_deadband_m_s: float = VELOCITY_DEADBAND_M_S,
        min_sustained_velocity_m_s: float = MIN_SUSTAINED_VELOCITY_M_S,
        sustain_window_s: float = SUSTAIN_WINDOW_S,
        reversal_distance_m: float = REVERSAL_DISTANCE_M,
        ramp_duration_s: float = RAMP_DURATION_S,
    ) -> PhaseRampState:
        """The five keyword-only constants all default to this module's own
        (log-validated) values, so standalone/test use needs no changes --
        `PhaseRampDetector().update(pos, vel, t)` keeps working exactly as
        before. TrainMode instead passes CableState's live-adjustable copies
        of these every tick (resistance-modes sub-phase 4's "configure in a
        GYM Settings sub-tab" follow-up) rather than baking them into this
        instance at construction time, so a settings change takes effect on
        the very next tick of an already-running session."""
        if velocity_m_s > velocity_deadband_m_s:
            raw_dir = CONCENTRIC
        elif velocity_m_s < -velocity_deadband_m_s:
            raw_dir = ECCENTRIC
        else:
            raw_dir = None

        if raw_dir is None or raw_dir == self._phase or abs(velocity_m_s) < min_sustained_velocity_m_s:
            # Not moving, moving the already-committed direction, or too
            # slow to count as a real candidate -- any in-progress reversal
            # candidate is fully discarded (not paused) here, which is the
            # actual pause-and-continue rejection.
            self._candidate_phase = None
        elif self._candidate_phase != raw_dir:
            # First tick this candidate direction has looked sustained.
            self._candidate_phase = raw_dir
            self._candidate_start_t = t
            self._candidate_start_position_m = position_m
        else:
            sustained_s = t - self._candidate_start_t
            traveled_m = abs(position_m - self._candidate_start_position_m)
            if sustained_s >= sustain_window_s and traveled_m >= reversal_distance_m:
                self._previous_phase = self._phase
                self._phase = raw_dir
                self._ramp_start_t = t
                self._candidate_phase = None

        if self._ramp_start_t is None:
            ramp_progress = 1.0
        else:
            ramp_progress = min(1.0, (t - self._ramp_start_t) / ramp_duration_s) if ramp_duration_s > 0 else 1.0

        return PhaseRampState(
            phase=self._phase,
            previous_phase=self._phase if ramp_progress >= 1.0 else self._previous_phase,
            ramp_progress=ramp_progress,
        )
