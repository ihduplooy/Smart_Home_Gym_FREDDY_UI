"""core/cable/governor.py tests (exercise_tab_build_spec_layerB.md §12)."""

import pytest

from core.cable.governor import governed_force


def test_below_target_returns_base_force_only():
    f = governed_force(
        velocity_turns_s=0.5,
        velocity_target_turns_s=1.0,
        force_base_n=20.0,
        force_max_n=150.0,
        governor_gain=150.0,
    )
    assert f == 20.0


def test_at_exact_target_returns_base_force_only():
    f = governed_force(
        velocity_turns_s=1.0,
        velocity_target_turns_s=1.0,
        force_base_n=20.0,
        force_max_n=150.0,
        governor_gain=150.0,
    )
    assert f == 20.0


def test_above_target_force_rises_with_excess_velocity():
    f = governed_force(
        velocity_turns_s=1.2,
        velocity_target_turns_s=1.0,
        force_base_n=20.0,
        force_max_n=150.0,
        governor_gain=150.0,
    )
    assert f == pytest.approx(20.0 + 150.0 * 0.2)


def test_force_increases_monotonically_with_velocity_above_target():
    kwargs = dict(velocity_target_turns_s=1.0, force_base_n=20.0, force_max_n=150.0, governor_gain=150.0)
    f1 = governed_force(velocity_turns_s=1.1, **kwargs)
    f2 = governed_force(velocity_turns_s=1.3, **kwargs)
    f3 = governed_force(velocity_turns_s=1.5, **kwargs)
    assert f1 < f2 < f3


def test_clamped_at_force_max():
    f = governed_force(
        velocity_turns_s=5.0,  # way above target
        velocity_target_turns_s=1.0,
        force_base_n=20.0,
        force_max_n=150.0,
        governor_gain=150.0,
    )
    assert f == 150.0


def test_zero_force_base_is_pure_isokinetic():
    below = governed_force(
        velocity_turns_s=0.5, velocity_target_turns_s=1.0, force_base_n=0.0, force_max_n=150.0, governor_gain=150.0
    )
    assert below == 0.0
    above = governed_force(
        velocity_turns_s=1.1, velocity_target_turns_s=1.0, force_base_n=0.0, force_max_n=150.0, governor_gain=150.0
    )
    assert above == pytest.approx(150.0 * 0.1)


def test_smoothness_no_discontinuity_at_the_target_boundary():
    # The formula is continuous at v == v_target by construction (both
    # branches evaluate to force_base_n there) -- verify numerically on
    # either side of the boundary, not just in the middle of each branch.
    kwargs = dict(velocity_target_turns_s=1.0, force_base_n=20.0, force_max_n=150.0, governor_gain=150.0)
    just_below = governed_force(velocity_turns_s=0.999, **kwargs)
    at_target = governed_force(velocity_turns_s=1.000, **kwargs)
    just_above = governed_force(velocity_turns_s=1.001, **kwargs)
    assert just_below == pytest.approx(at_target, abs=1e-6)
    assert just_above == pytest.approx(at_target, abs=0.2)  # gain=150 -> ~0.15N step over 0.001 turns/s
