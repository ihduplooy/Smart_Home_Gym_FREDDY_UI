import math

from core.profiles.detectors import Phase, PhaseDetector, RepCounter

DT = 1.0 / 50.0  # 50 Hz tick, matching ControlSession.TELEMETRY_HZ


def _sinusoid_rep_sequence(n_reps: int, rep_period_s: float, amplitude: float, dt: float = DT):
    """Position/velocity samples for `n_reps` clean reps: position follows a
    smooth raised-cosine bump per rep (0 -> amplitude -> 0), velocity its
    analytic derivative. Rest between reps is a flat plateau at position 0
    so the detector settles into BOTTOM_HOLD between reps too.

    Plateau length matters here, not just for phase-cycle correctness: the
    rep counter (REP_EWMA_ALPHA=0.05, time constant 1/alpha=20 ticks=0.4s at
    50 Hz) only counts a rep once its own position EWMA decays back within
    REP_PROXIMITY_TURNS of true rest -- from the EWMA's peak-tracking value,
    that takes ~35 ticks (~0.7s, verified empirically while building the
    detector). 1.5s gives comfortable margin without depending on exact
    decay-rate arithmetic.
    """
    plateau_s = 1.5
    samples = []
    t = 0.0
    for _ in range(n_reps):
        # Plateau at rest before the rep.
        n_plateau = int(plateau_s / dt)
        for _ in range(n_plateau):
            samples.append((t, 0.0, 0.0))
            t += dt
        # One rep: position = amplitude/2 * (1 - cos(2*pi*t'/period)), a full
        # up-and-back cycle over `rep_period_s`.
        n_rep = int(rep_period_s / dt)
        for i in range(n_rep + 1):
            tp = i * dt
            omega = 2 * math.pi / rep_period_s
            position = amplitude / 2 * (1 - math.cos(omega * tp))
            velocity = amplitude / 2 * omega * math.sin(omega * tp)
            samples.append((t, position, velocity))
            t += dt
    # Trailing plateau so the last rep's EWMA has the same time to decay back
    # to baseline as every rep before it got (each rep's plateau precedes it,
    # so without this the final rep would be one plateau short).
    n_plateau = int(plateau_s / dt)
    for _ in range(n_plateau):
        samples.append((t, 0.0, 0.0))
        t += dt
    return samples


def _run_sequence(samples):
    detector = PhaseDetector()
    counter = RepCounter()
    phases = []
    rep_counts = []
    for _, position, velocity in samples:
        phase = detector.update(velocity)
        rep_count = counter.update(position, phase)
        phases.append(phase)
        rep_counts.append(rep_count)
    return phases, rep_counts


def test_three_clean_reps_produce_correct_phase_cycle_and_rep_count():
    samples = _sinusoid_rep_sequence(n_reps=3, rep_period_s=2.0, amplitude=2.0)
    phases, rep_counts = _run_sequence(samples)

    # Collapse consecutive duplicate phases into the order they occurred.
    order = [phases[0]]
    for p in phases[1:]:
        if p != order[-1]:
            order.append(p)

    # Expect a repeating CONCENTRIC -> TOP_HOLD -> ECCENTRIC -> BOTTOM_HOLD
    # cycle (starting phase is BOTTOM_HOLD before the first pull).
    expected_cycle = [Phase.CONCENTRIC, Phase.TOP_HOLD, Phase.ECCENTRIC, Phase.BOTTOM_HOLD]
    assert order[0] == Phase.BOTTOM_HOLD
    for i, phase in enumerate(order[1:]):
        assert phase == expected_cycle[i % 4]

    assert rep_counts[-1] == 3


def test_noise_at_threshold_does_not_flicker_phase():
    """Velocity dithering right around PHASE_VEL_THRESHOLD_TURNS_S, below the
    hysteresis-extended exit threshold, must never leave the current hold."""
    from config import board_constants

    threshold = board_constants.PHASE_VEL_THRESHOLD_TURNS_S
    detector = PhaseDetector()  # starts in BOTTOM_HOLD

    # Dither velocity between +0.9*threshold and -0.9*threshold: never clears
    # threshold + hysteresis, so must stay in BOTTOM_HOLD throughout.
    noisy_velocities = [0.9 * threshold, -0.9 * threshold] * 50
    phases = [detector.update(v) for v in noisy_velocities]

    assert all(p == Phase.BOTTOM_HOLD for p in phases)


def test_no_concentric_phase_means_no_rep_counted():
    """Position wandering back near its own EWMA without ever passing
    through CONCENTRIC must not count a rep (the phase gate)."""
    counter = RepCounter()
    # Phase.ECCENTRIC only, never CONCENTRIC -- position dips then returns.
    positions = [0.0, -0.05, -0.1, -0.05, 0.0] * 10
    rep_counts = [counter.update(p, Phase.ECCENTRIC) for p in positions]

    assert all(rc == 0 for rc in rep_counts)


def test_rep_counter_reset_clears_state():
    counter = RepCounter()
    counter.update(0.0, Phase.CONCENTRIC)
    counter.update(0.0, Phase.CONCENTRIC)
    counter.reset()
    assert counter.rep_count == 0


def test_phase_detector_reset_returns_to_bottom_hold():
    detector = PhaseDetector()
    detector.update(1.0)  # -> CONCENTRIC
    assert detector.phase == Phase.CONCENTRIC
    detector.reset()
    assert detector.phase == Phase.BOTTOM_HOLD
