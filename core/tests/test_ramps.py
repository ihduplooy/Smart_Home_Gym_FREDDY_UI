"""core/cable/ramps.py tests (exercise_tab_build_spec_layerB.md §12)."""

import pytest

from core.cable.ramps import slew_toward, taper_factor


# ---- slew_toward ----

def test_slew_toward_reaches_target_in_one_step_when_within_max_step():
    assert slew_toward(0.0, 5.0, 10.0) == 5.0


def test_slew_toward_clamps_to_max_step_when_target_far_above():
    assert slew_toward(0.0, 100.0, 10.0) == 10.0


def test_slew_toward_clamps_to_max_step_when_target_far_below():
    assert slew_toward(0.0, -100.0, 10.0) == -10.0


def test_slew_toward_repeated_calls_converge_on_target():
    current = 0.0
    target = 50.0
    max_step = 5.0
    for _ in range(20):
        current = slew_toward(current, target, max_step)
    assert current == pytest.approx(target)


def test_slew_toward_at_exact_max_step_lands_on_target():
    assert slew_toward(0.0, 10.0, 10.0) == 10.0


def test_slew_toward_already_at_target_is_a_no_op():
    assert slew_toward(5.0, 5.0, 10.0) == 5.0


def test_slew_toward_rejects_negative_max_step():
    with pytest.raises(ValueError):
        slew_toward(0.0, 1.0, -1.0)


# ---- taper_factor ----

def test_taper_factor_is_one_far_from_limit():
    assert taper_factor(1.0, 0.15) == 1.0


def test_taper_factor_is_one_at_exact_taper_boundary():
    assert taper_factor(0.15, 0.15) == 1.0


def test_taper_factor_is_zero_at_the_limit():
    assert taper_factor(0.0, 0.15) == 0.0


def test_taper_factor_is_zero_past_the_limit():
    assert taper_factor(-0.05, 0.15) == 0.0


def test_taper_factor_is_linear_partway_through_the_taper_zone():
    assert taper_factor(0.075, 0.15) == pytest.approx(0.5)


def test_taper_factor_rejects_nonpositive_taper_distance():
    with pytest.raises(ValueError):
        taper_factor(0.05, 0.0)
    with pytest.raises(ValueError):
        taper_factor(0.05, -0.1)
