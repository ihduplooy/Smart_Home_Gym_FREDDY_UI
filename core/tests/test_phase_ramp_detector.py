import pytest

from core.cable.phase_ramp_detector import (
    CONCENTRIC,
    ECCENTRIC,
    MIN_SUSTAINED_VELOCITY_M_S,
    RAMP_DURATION_S,
    REVERSAL_DISTANCE_M,
    SUSTAIN_WINDOW_S,
    VELOCITY_DEADBAND_M_S,
    PhaseRampDetector,
)


def _run(detector, samples):
    """samples: list of (position_m, velocity_m_s, t) -> list of states."""
    return [detector.update(p, v, t) for p, v, t in samples]


def _ticks_to_clear_debounce(strong_v, dt):
    """Enough ticks at `strong_v`/`dt` to clear BOTH SUSTAIN_WINDOW_S and
    REVERSAL_DISTANCE_M with margin -- distance is usually the binding
    constraint at a small `strong_v`, time at a large one, so take whichever
    needs more ticks rather than assuming either one dominates."""
    time_ticks = SUSTAIN_WINDOW_S / dt
    distance_ticks = REVERSAL_DISTANCE_M / (strong_v * dt)
    return int(max(time_ticks, distance_ticks)) + 10


# ---- initial state ----


def test_starts_concentric_with_no_ramp():
    d = PhaseRampDetector()
    state = d.update(0.0, 0.0, 0.0)
    assert state.phase == CONCENTRIC
    assert state.previous_phase == CONCENTRIC
    assert state.ramp_progress == pytest.approx(1.0)


# ---- clean rep: a real, sustained, far-enough reversal commits ----


def test_clean_rep_commits_a_flip():
    d = PhaseRampDetector()
    strong_v = MIN_SUSTAINED_VELOCITY_M_S + 0.05
    # Pull out (concentric) for a while, then sustain a strong reversal for
    # longer than SUSTAIN_WINDOW_S while covering more than
    # REVERSAL_DISTANCE_M -- an unambiguous, real rep transition.
    t = 0.0
    pos = 0.0
    d.update(pos, strong_v, t)
    dt = 0.02
    n_ticks = _ticks_to_clear_debounce(strong_v, dt)
    state = None
    for _ in range(n_ticks):
        t += dt
        pos -= strong_v * dt  # reeling in -> eccentric
        state = d.update(pos, -strong_v, t)
    assert state.phase == ECCENTRIC


def test_ramp_progress_blends_smoothly_then_settles():
    d = PhaseRampDetector()
    strong_v = MIN_SUSTAINED_VELOCITY_M_S + 0.05
    t = 0.0
    pos = 0.0
    dt = 0.02
    n_ticks = _ticks_to_clear_debounce(strong_v, dt)
    flip_t = None
    for _ in range(n_ticks):
        t += dt
        pos -= strong_v * dt
        state = d.update(pos, -strong_v, t)
        if state.phase == ECCENTRIC and flip_t is None:
            flip_t = t
            assert state.previous_phase == CONCENTRIC
            assert 0.0 <= state.ramp_progress < 1.0
    assert flip_t is not None

    # Keep moving the same (now-committed) direction -- ramp_progress climbs
    # to 1.0 over RAMP_DURATION_S and previous_phase converges to phase.
    while t < flip_t + RAMP_DURATION_S + 0.05:
        t += dt
        pos -= strong_v * dt
        state = d.update(pos, -strong_v, t)
    assert state.ramp_progress == pytest.approx(1.0)
    assert state.previous_phase == state.phase == ECCENTRIC


# ---- pause-and-continue must NOT trigger a false flip ----


def test_pause_and_continue_does_not_flip():
    """A brief stop mid-rep (velocity drops into the deadband, then the user
    resumes pulling the SAME direction) must not be mistaken for a reversal
    -- the doc's explicit dual-debounce motivation."""
    d = PhaseRampDetector()
    strong_v = MIN_SUSTAINED_VELOCITY_M_S + 0.05
    t = 0.0
    pos = 0.0
    dt = 0.02
    state = d.update(pos, strong_v, t)
    assert state.phase == CONCENTRIC

    # Pause: velocity drops to ~0 for a bit (well within the deadband).
    for _ in range(10):
        t += dt
        state = d.update(pos, 0.0, t)
        assert state.phase == CONCENTRIC

    # Resume in the SAME direction -- still concentric throughout.
    for _ in range(20):
        t += dt
        pos += strong_v * dt
        state = d.update(pos, strong_v, t)
        assert state.phase == CONCENTRIC


def test_brief_reversal_that_never_sustains_does_not_flip():
    """A short opposite-direction blip (e.g. a bounce at the bottom of a
    rep) that never clears SUSTAIN_WINDOW_S must not commit a flip, even if
    it's individually fast enough to look like a real reversal in isolation."""
    d = PhaseRampDetector()
    strong_v = MIN_SUSTAINED_VELOCITY_M_S + 0.05
    t = 0.0
    pos = 0.0
    d.update(pos, strong_v, t)  # concentric

    # Opposite-direction blip, shorter than SUSTAIN_WINDOW_S.
    dt = 0.02
    blip_ticks = max(1, int((SUSTAIN_WINDOW_S / dt) / 2))
    for _ in range(blip_ticks):
        t += dt
        pos -= strong_v * dt
        state = d.update(pos, -strong_v, t)
    assert state.phase == CONCENTRIC  # not sustained long enough to commit

    # Back to the original direction -- still concentric, no false flip ever
    # landed.
    for _ in range(10):
        t += dt
        pos += strong_v * dt
        state = d.update(pos, strong_v, t)
    assert state.phase == CONCENTRIC


def test_sustained_but_insufficient_distance_does_not_flip():
    """Sustained long enough in time, but the cable barely moved (e.g. a
    fast wobble in place) -- distance debounce alone must block the flip."""
    d = PhaseRampDetector()
    strong_v = MIN_SUSTAINED_VELOCITY_M_S + 0.05
    t = 0.0
    pos = 0.0
    d.update(pos, strong_v, t)  # concentric

    dt = 0.001  # tiny steps -- plenty of sustained time, negligible distance
    n_ticks = int((SUSTAIN_WINDOW_S / dt) + 50)
    state = None
    for _ in range(n_ticks):
        t += dt
        pos -= strong_v * dt
        state = d.update(pos, -strong_v, t)
        if abs(pos) >= REVERSAL_DISTANCE_M:
            break  # stop before distance debounce would legitimately clear
    assert state.phase == CONCENTRIC


# ---- noise near a stall must not cause spurious transitions ----


def test_noise_near_stall_does_not_transition():
    """Small, sign-flickering velocity noise around zero (encoder jitter at
    a dead stop) must never register as a phase change."""
    d = PhaseRampDetector()
    t = 0.0
    dt = 0.02
    noise = [0.01, -0.015, 0.008, -0.012, 0.02, -0.005, 0.011, -0.019]
    for i in range(200):
        t += dt
        v = noise[i % len(noise)]
        assert abs(v) < VELOCITY_DEADBAND_M_S  # sanity: genuinely noise-level
        state = d.update(0.0, v, t)
        assert state.phase == CONCENTRIC
        assert state.ramp_progress == pytest.approx(1.0)


def test_velocity_just_above_deadband_but_below_sustained_threshold_does_not_flip():
    """A weak reversal (above the raw deadband but below
    MIN_SUSTAINED_VELOCITY_M_S) must not be treated as a real candidate
    direction at all."""
    d = PhaseRampDetector()
    weak_v = (VELOCITY_DEADBAND_M_S + MIN_SUSTAINED_VELOCITY_M_S) / 2
    assert VELOCITY_DEADBAND_M_S < weak_v < MIN_SUSTAINED_VELOCITY_M_S
    d.update(0.0, MIN_SUSTAINED_VELOCITY_M_S + 0.05, 0.0)  # concentric

    t = 0.0
    pos = 0.0
    dt = 0.02
    state = None
    for _ in range(50):
        t += dt
        pos -= weak_v * dt
        state = d.update(pos, -weak_v, t)
    assert state.phase == CONCENTRIC


# ---- reset ----


def test_reset_returns_to_initial_state():
    d = PhaseRampDetector()
    strong_v = MIN_SUSTAINED_VELOCITY_M_S + 0.05
    t = 0.0
    pos = 0.0
    dt = 0.02
    n_ticks = _ticks_to_clear_debounce(strong_v, dt)
    for _ in range(n_ticks):
        t += dt
        pos -= strong_v * dt
        d.update(pos, -strong_v, t)
    assert d.update(pos, -strong_v, t).phase == ECCENTRIC  # sanity: really flipped

    d.reset()
    state = d.update(0.0, 0.0, 0.0)
    assert state.phase == CONCENTRIC
    assert state.previous_phase == CONCENTRIC
    assert state.ramp_progress == pytest.approx(1.0)
