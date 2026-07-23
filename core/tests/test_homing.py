"""Synthetic-sequence tests for core/cable/homing.py, written before anything
is built on top of the state machine (exercise_tab_build_spec_layerA.md §8,
§9). Same rationale as core/tests/test_detectors.py: an "obviously correct"
detector design can still have non-obvious false-trigger modes that only
synthetic sequences surface.

Each test monkeypatches board_constants to small, fast, unambiguous values
(HomingStateMachine reads them at construction time) so only the one bound/
behaviour under test can possibly fire.
"""

import pytest

from config import board_constants
from core.cable.homing import HomingState, HomingStateMachine

DT = 1.0 / 50.0  # matches ControlSession.TELEMETRY_HZ


def _patch(monkeypatch, **kwargs):
    for name, value in kwargs.items():
        monkeypatch.setattr(board_constants, name, value)


def _fast_defaults(monkeypatch, **overrides):
    """Small-but-generous values so grace/debounce are fast to exercise and
    both bounds are generous enough not to fire by accident, unless a test
    explicitly overrides one to make it fire."""
    values = dict(
        HOMING_CURRENT_THRESHOLD_A=0.8,
        HOMING_CURRENT_LIMIT_A=3.0,
        HOMING_VELOCITY_TURNS_S=0.15,
        HOMING_DEBOUNCE_SAMPLES=3,
        HOMING_STARTUP_GRACE_S=0.1,  # 5 ticks at DT
        HOMING_MAX_TRAVEL_TURNS=10.0,
        HOMING_TIMEOUT_S=10.0,
    )
    values.update(overrides)
    _patch(monkeypatch, **values)


def _run(hsm, samples):
    """samples: list of (t, current_iq, position_turns). Returns the list of
    HomingUpdate results, one per sample, in order."""
    return [hsm.update(t, i, p) for (t, i, p) in samples]


# ---- construction must not move anything (spec §4 item 1) ----

def test_construction_alone_does_not_start_homing(monkeypatch):
    _fast_defaults(monkeypatch)
    hsm = HomingStateMachine()
    assert hsm.state == HomingState.IDLE


# ---- live overrides (velocity_turns_s / current_threshold_a) ----

def test_construction_with_no_overrides_uses_board_constants(monkeypatch):
    _fast_defaults(monkeypatch, HOMING_VELOCITY_TURNS_S=0.42, HOMING_CURRENT_THRESHOLD_A=1.7)
    hsm = HomingStateMachine()
    r = hsm.update(0.0, 0.0, 0.0)
    assert r.velocity_command_turns_s == -0.42


def test_construction_with_velocity_override(monkeypatch):
    _fast_defaults(monkeypatch, HOMING_VELOCITY_TURNS_S=0.15)
    hsm = HomingStateMachine(velocity_turns_s=0.9)
    r = hsm.update(0.0, 0.0, 0.0)
    assert r.velocity_command_turns_s == -0.9  # override wins, not the board default


def test_construction_with_current_threshold_override(monkeypatch):
    _fast_defaults(monkeypatch, HOMING_CURRENT_THRESHOLD_A=0.8, HOMING_DEBOUNCE_SAMPLES=1, HOMING_STARTUP_GRACE_S=0.0)
    hsm = HomingStateMachine(current_threshold_a=1.5)
    # 1.0A would have crossed the board default (0.8) but not the override (1.5).
    r = hsm.update(0.0, 1.0, 0.0)
    assert r.state != HomingState.HOMED
    r2 = hsm.update(DT, 2.0, 0.0)  # crosses the override
    assert r2.state == HomingState.HOMED


# ---- case 1: clean detection ----

def test_clean_detection_latches_home_at_correct_position(monkeypatch):
    _fast_defaults(monkeypatch)
    hsm = HomingStateMachine()

    t = 0.0
    position = 0.0
    velocity = -0.15  # reeling in

    # Grace period: 5 ticks, no load.
    for _ in range(5):
        r = hsm.update(t, 0.1, position)
        assert r.state == HomingState.STARTUP_GRACE
        t += DT
        position += velocity * DT

    # Detecting, no load yet.
    r = hsm.update(t, 0.1, position)
    assert r.state == HomingState.DETECTING
    t += DT
    position += velocity * DT

    # Cable goes taut: current crosses threshold and holds for the debounce
    # window (3 samples).
    latched_at = None
    for i in range(3):
        r = hsm.update(t, 1.2, position)
        if i < 2:
            assert r.state == HomingState.DETECTING
            assert r.home_position_turns is None
        t += DT
        latched_at = position
        position += velocity * DT

    assert r.state == HomingState.HOMED
    assert r.home_position_turns == pytest.approx(latched_at)
    assert r.velocity_command_turns_s == 0.0

    # Terminal: further updates stay HOMED and inert.
    r2 = hsm.update(t, 5.0, position + 100)
    assert r2.state == HomingState.HOMED
    assert r2.velocity_command_turns_s == 0.0


def test_reel_in_velocity_command_follows_cable_sign(monkeypatch):
    _fast_defaults(monkeypatch)
    hsm = HomingStateMachine()
    r = hsm.update(0.0, 0.0, 0.0)
    # CABLE_SIGN=1, reel-in is the negative direction.
    assert r.velocity_command_turns_s == -0.15


# ---- case 2: transient spike during the grace period must not latch ----

def test_transient_spike_during_grace_period_does_not_latch(monkeypatch):
    _fast_defaults(monkeypatch)
    hsm = HomingStateMachine()

    t = 0.0
    position = 0.0
    # A spike lasting the full debounce window, but entirely inside the
    # 5-tick grace window — must never be evaluated, must never latch.
    for i in range(5):
        r = hsm.update(t, 5.0, position)  # way over threshold
        assert r.state == HomingState.STARTUP_GRACE
        assert r.home_position_turns is None
        t += DT
        position -= 0.01

    # Grace ends; load drops back to nothing. Must not have carried any
    # debounce count across the boundary.
    r = hsm.update(t, 0.1, position)
    assert r.state == HomingState.DETECTING
    assert r.home_position_turns is None


# ---- case 3: transient spike after grace, shorter than the debounce window ----

def test_transient_spike_shorter_than_debounce_window_does_not_latch(monkeypatch):
    _fast_defaults(monkeypatch, HOMING_DEBOUNCE_SAMPLES=5)
    hsm = HomingStateMachine()

    t = 0.0
    position = 0.0
    for _ in range(5):  # clear grace
        hsm.update(t, 0.1, position)
        t += DT
        position -= 0.15 * DT

    # Spike for 4 consecutive samples (one short of the 5-sample debounce),
    # then drop back below threshold.
    for _ in range(4):
        r = hsm.update(t, 1.2, position)
        assert r.state == HomingState.DETECTING
        assert r.home_position_turns is None
        t += DT
        position -= 0.15 * DT

    r = hsm.update(t, 0.1, position)  # drops back below threshold
    assert r.state == HomingState.DETECTING
    assert r.home_position_turns is None
    t += DT

    # Counter must have reset to zero, not merely paused: three more
    # over-threshold samples (fewer than the 5-sample debounce) still must
    # not latch.
    for _ in range(3):
        r = hsm.update(t, 1.2, position)
        assert r.state == HomingState.DETECTING
        assert r.home_position_turns is None
        t += DT


# ---- case 4: threshold never reached -> travel-bound fault ----

def test_threshold_never_reached_travel_bound_faults(monkeypatch):
    _fast_defaults(monkeypatch, HOMING_MAX_TRAVEL_TURNS=0.5, HOMING_TIMEOUT_S=1000.0)
    hsm = HomingStateMachine()

    t = 0.0
    position = 0.0
    velocity = -0.15
    result = None
    for _ in range(2000):
        result = hsm.update(t, 0.1, position)  # never crosses threshold
        t += DT
        position += velocity * DT
        if result.state in (HomingState.FAULT_TRAVEL_EXCEEDED, HomingState.HOMED):
            break

    assert result.state == HomingState.FAULT_TRAVEL_EXCEEDED
    assert result.velocity_command_turns_s == 0.0
    assert result.fault_reason
    assert hsm.state == HomingState.FAULT_TRAVEL_EXCEEDED

    # Terminal: stays faulted.
    r2 = hsm.update(t, 5.0, position)
    assert r2.state == HomingState.FAULT_TRAVEL_EXCEEDED
    assert r2.velocity_command_turns_s == 0.0


# ---- case 5: threshold never reached -> time-bound fault ----

def test_threshold_never_reached_timeout_faults(monkeypatch):
    _fast_defaults(monkeypatch, HOMING_TIMEOUT_S=0.2, HOMING_MAX_TRAVEL_TURNS=1000.0)
    hsm = HomingStateMachine()

    t = 0.0
    position = 0.0  # position barely moves -- travel bound must not fire
    result = None
    for _ in range(50):
        result = hsm.update(t, 0.1, position)  # never crosses threshold
        t += DT
        position -= 1e-6
        if result.state in (HomingState.FAULT_TIMEOUT, HomingState.HOMED):
            break

    assert result.state == HomingState.FAULT_TIMEOUT
    assert result.velocity_command_turns_s == 0.0
    assert result.fault_reason
    assert hsm.state == HomingState.FAULT_TIMEOUT


# ---- case 6: abort mid-sequence ----

def test_abort_mid_sequence_terminates_immediately(monkeypatch):
    _fast_defaults(monkeypatch)
    hsm = HomingStateMachine()

    t = 0.0
    position = 0.0
    for _ in range(3):  # partway through grace
        hsm.update(t, 0.1, position)
        t += DT
        position -= 0.15 * DT

    r = hsm.abort()
    assert r.state == HomingState.ABORTED
    assert r.velocity_command_turns_s == 0.0
    assert hsm.state == HomingState.ABORTED

    # Terminal: further updates (even a threshold-crossing sample) never
    # resurrect it into HOMED.
    r2 = hsm.update(t, 5.0, position)
    assert r2.state == HomingState.ABORTED
    assert r2.velocity_command_turns_s == 0.0
    assert r2.home_position_turns is None


def test_abort_before_any_update_is_a_safe_no_op_terminal(monkeypatch):
    _fast_defaults(monkeypatch)
    hsm = HomingStateMachine()
    r = hsm.abort()
    assert r.state == HomingState.ABORTED
    r2 = hsm.update(0.0, 5.0, 0.0)
    assert r2.state == HomingState.ABORTED


def test_abort_after_homed_is_a_no_op(monkeypatch):
    _fast_defaults(monkeypatch, HOMING_DEBOUNCE_SAMPLES=1, HOMING_STARTUP_GRACE_S=0.0)
    hsm = HomingStateMachine()
    r = hsm.update(0.0, 5.0, 0.0)  # grace already elapsed (0.0s), latches immediately
    assert r.state == HomingState.HOMED
    r2 = hsm.abort()
    assert r2.state == HomingState.HOMED  # abort cannot un-home
