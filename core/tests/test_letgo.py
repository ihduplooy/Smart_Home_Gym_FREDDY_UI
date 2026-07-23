"""core/cable/letgo.py tests (exercise_tab_build_spec_layerB.md §6 items 3/4,
§12). State-gating itself (must not fire outside concentric) is a
force_mode.py integration responsibility, tested at that level once
ForceMode exists (spec §4.4: "test that gating explicitly") -- this file
covers the detector's own debounce/reset behaviour in isolation."""

from config import board_constants
from core.cable.letgo import LetGoDetector


def _fast_defaults(monkeypatch, **overrides):
    values = dict(LETGO_VELOCITY_TURNS_S=0.1, LETGO_DEBOUNCE_SAMPLES=5)
    values.update(overrides)
    for name, value in values.items():
        monkeypatch.setattr(board_constants, name, value)


def test_construction_alone_does_not_fire(monkeypatch):
    _fast_defaults(monkeypatch)
    detector = LetGoDetector()
    assert detector.update(0.0) is False


def test_fires_on_sustained_reel_in(monkeypatch):
    _fast_defaults(monkeypatch)
    detector = LetGoDetector()
    fired = None
    for _ in range(5):
        fired = detector.update(-0.5)  # well past threshold, reel-in direction
    assert fired is True


def test_does_not_fire_before_debounce_window_elapses(monkeypatch):
    _fast_defaults(monkeypatch)
    detector = LetGoDetector()
    for _ in range(4):  # one short of the 5-sample debounce
        fired = detector.update(-0.5)
        assert fired is False


def test_does_not_fire_on_a_sub_debounce_transient(monkeypatch):
    _fast_defaults(monkeypatch)
    detector = LetGoDetector()
    for _ in range(4):
        assert detector.update(-0.5) is False
    # Drops back below threshold before the debounce window completes.
    assert detector.update(0.0) is False
    # Counter must have reset, not merely paused.
    for _ in range(3):
        assert detector.update(-0.5) is False


def test_does_not_fire_on_paying_out_velocity():
    detector = LetGoDetector()
    for _ in range(20):
        assert detector.update(0.5) is False  # concentric: paying out, expected


def test_does_not_fire_on_small_velocity_near_at_rest_threshold(monkeypatch):
    _fast_defaults(monkeypatch)
    detector = LetGoDetector()
    for _ in range(20):
        # Below LETGO_VELOCITY_TURNS_S even though technically reel-in
        # direction -- ordinary settling/noise, not a let-go signal.
        assert detector.update(-0.05) is False


def test_reset_clears_debounce_count(monkeypatch):
    _fast_defaults(monkeypatch)
    detector = LetGoDetector()
    for _ in range(4):
        detector.update(-0.5)
    detector.reset()
    for _ in range(4):
        assert detector.update(-0.5) is False
    assert detector.update(-0.5) is True  # 5th sample after reset


def test_fires_again_after_reset_and_a_second_sustained_reel_in(monkeypatch):
    _fast_defaults(monkeypatch)
    detector = LetGoDetector()
    for _ in range(5):
        fired = detector.update(-0.5)
    assert fired is True
    detector.reset()
    assert detector.update(0.0) is False
    for _ in range(5):
        fired = detector.update(-0.5)
    assert fired is True
