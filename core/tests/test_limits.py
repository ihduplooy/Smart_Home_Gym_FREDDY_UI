"""core/cable/limits.py tests (exercise_tab_build_spec_layerA.md §8)."""

import pytest

from core.cable.limits import (
    check_runtime_guard,
    clamp_target_turns,
    validate_homed,
    validate_max_extension_candidate,
)


# ---- target clamping at both ends ----

def test_clamp_within_range_is_unchanged():
    assert clamp_target_turns(5.0, home_turns=0.0, max_turns=10.0) == 5.0


def test_clamp_below_home_clamps_to_home():
    assert clamp_target_turns(-3.0, home_turns=0.0, max_turns=10.0) == 0.0


def test_clamp_above_max_clamps_to_max():
    assert clamp_target_turns(15.0, home_turns=0.0, max_turns=10.0) == 10.0


def test_clamp_is_order_independent_on_home_max_args():
    # Same physical bounds, args passed in either order.
    assert clamp_target_turns(15.0, home_turns=10.0, max_turns=0.0) == 10.0
    assert clamp_target_turns(-3.0, home_turns=10.0, max_turns=0.0) == 0.0


def test_clamp_at_exact_boundaries_is_unchanged():
    assert clamp_target_turns(0.0, home_turns=0.0, max_turns=10.0) == 0.0
    assert clamp_target_turns(10.0, home_turns=0.0, max_turns=10.0) == 10.0


# ---- runtime guard on measured position ----

def test_runtime_guard_within_range_no_violation():
    assert check_runtime_guard(5.0, home_turns=0.0, max_turns=10.0, tolerance_turns=0.05) is False


def test_runtime_guard_within_tolerance_past_bound_no_violation():
    assert check_runtime_guard(10.03, home_turns=0.0, max_turns=10.0, tolerance_turns=0.05) is False
    assert check_runtime_guard(-0.03, home_turns=0.0, max_turns=10.0, tolerance_turns=0.05) is False


def test_runtime_guard_beyond_tolerance_past_max_is_violation():
    assert check_runtime_guard(10.2, home_turns=0.0, max_turns=10.0, tolerance_turns=0.05) is True


def test_runtime_guard_beyond_tolerance_past_home_is_violation():
    assert check_runtime_guard(-0.2, home_turns=0.0, max_turns=10.0, tolerance_turns=0.05) is True


def test_runtime_guard_at_exact_tolerance_boundary_no_violation():
    assert check_runtime_guard(10.05, home_turns=0.0, max_turns=10.0, tolerance_turns=0.05) is False


# ---- un-homed rejection ----

def test_validate_homed_raises_when_not_homed():
    with pytest.raises(RuntimeError):
        validate_homed(False)


def test_validate_homed_passes_when_homed():
    validate_homed(True)  # must not raise


# ---- max-extension candidate sanity check ----

def test_max_extension_candidate_accepts_sufficient_travel():
    validate_max_extension_candidate(5.0, home_turns=0.0, min_travel_turns=0.5)  # must not raise


def test_max_extension_candidate_rejects_at_home():
    with pytest.raises(ValueError):
        validate_max_extension_candidate(0.0, home_turns=0.0, min_travel_turns=0.5)


def test_max_extension_candidate_rejects_below_home():
    with pytest.raises(ValueError):
        validate_max_extension_candidate(-2.0, home_turns=0.0, min_travel_turns=0.5)


def test_max_extension_candidate_rejects_implausibly_close_to_home():
    with pytest.raises(ValueError):
        validate_max_extension_candidate(0.1, home_turns=0.0, min_travel_turns=0.5)
