"""core/cable/power_limiter.py tests (exercise_tab_build_spec_layerB.md §12).

Uses the real, measured constants (SPOOL_RADIUS_M=0.035, MOTOR_TORQUE_CONSTANT
=0.492 (bench-measured, open item #13 resolved), MOTOR_PHASE_RESISTANCE_OHM
=0.38) so these tests double as a standing check on the §5.2 break-even
analysis.
"""

import pytest

from core.cable.power_limiter import apply_power_limit, estimate_regen_power_w

KT = 0.492
R_PHASE = 0.38
R_SPOOL = 0.035


def test_estimate_matches_hand_computed_breakeven_velocity():
    # v_breakeven = 1.5 * F * r^2 * R / Kt^2 -- the estimate should be ~0 there.
    f = 100.0
    v_breakeven = 1.5 * f * R_SPOOL**2 * R_PHASE / KT**2
    p = estimate_regen_power_w(f, v_breakeven, KT, R_PHASE, R_SPOOL)
    assert p == pytest.approx(0.0, abs=1e-6)


def test_estimate_is_negative_below_breakeven_velocity():
    f = 100.0
    v_breakeven = 1.5 * f * R_SPOOL**2 * R_PHASE / KT**2
    p = estimate_regen_power_w(f, v_breakeven * 0.5, KT, R_PHASE, R_SPOOL)
    assert p < 0  # net consumption, not regen


def test_estimate_is_positive_above_breakeven_velocity():
    f = 100.0
    v_breakeven = 1.5 * f * R_SPOOL**2 * R_PHASE / KT**2
    p = estimate_regen_power_w(f, v_breakeven * 2.0, KT, R_PHASE, R_SPOOL)
    assert p > 0


def test_estimate_zero_at_zero_velocity_is_all_copper_loss_negative():
    p = estimate_regen_power_w(100.0, 0.0, KT, R_PHASE, R_SPOOL)
    assert p < 0
    iq = 100.0 * R_SPOOL / KT
    expected_copper = 1.5 * iq * iq * R_PHASE
    assert p == pytest.approx(-expected_copper)


# ---- apply_power_limit ----

def test_no_limiting_when_under_budget():
    limited, active = apply_power_limit(50.0, 0.3, budget_w=30.0, torque_constant=KT, r_phase_ohm=R_PHASE, spool_radius_m=R_SPOOL)
    assert active is False
    assert limited == 50.0


def test_limiting_activates_when_over_budget():
    # High force + high velocity -> well over a 30W budget.
    limited, active = apply_power_limit(150.0, 1.0, budget_w=30.0, torque_constant=KT, r_phase_ohm=R_PHASE, spool_radius_m=R_SPOOL)
    assert active is True
    assert limited < 150.0


def test_limited_force_actually_respects_the_budget():
    limited, active = apply_power_limit(150.0, 1.0, budget_w=30.0, torque_constant=KT, r_phase_ohm=R_PHASE, spool_radius_m=R_SPOOL)
    assert active is True
    p_at_limit = estimate_regen_power_w(limited, 1.0, KT, R_PHASE, R_SPOOL)
    assert p_at_limit <= 30.0 + 1e-6


def test_limited_force_is_less_than_requested():
    limited, active = apply_power_limit(150.0, 1.0, budget_w=30.0, torque_constant=KT, r_phase_ohm=R_PHASE, spool_radius_m=R_SPOOL)
    assert limited < 150.0
    assert limited > 0.0


def test_releases_when_velocity_drops_back_down():
    # Same force, but at a low velocity where copper loss dominates --
    # limiter should not activate.
    limited, active = apply_power_limit(150.0, 0.05, budget_w=30.0, torque_constant=KT, r_phase_ohm=R_PHASE, spool_radius_m=R_SPOOL)
    assert active is False
    assert limited == 150.0


def test_no_limiting_at_zero_or_negative_velocity():
    limited, active = apply_power_limit(150.0, 0.0, budget_w=30.0, torque_constant=KT, r_phase_ohm=R_PHASE, spool_radius_m=R_SPOOL)
    assert active is False
    assert limited == 150.0
    limited, active = apply_power_limit(150.0, -0.2, budget_w=30.0, torque_constant=KT, r_phase_ohm=R_PHASE, spool_radius_m=R_SPOOL)
    assert active is False
    assert limited == 150.0


def test_no_limiting_at_zero_or_negative_force():
    limited, active = apply_power_limit(0.0, 1.0, budget_w=30.0, torque_constant=KT, r_phase_ohm=R_PHASE, spool_radius_m=R_SPOOL)
    assert active is False
    assert limited == 0.0


def test_generous_budget_never_limits_even_at_high_force_and_velocity():
    limited, active = apply_power_limit(150.0, 1.0, budget_w=1_000_000.0, torque_constant=KT, r_phase_ohm=R_PHASE, spool_radius_m=R_SPOOL)
    assert active is False
    assert limited == 150.0
