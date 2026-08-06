"""core/cable/state.py tests -- persistence split (spec §6): home/max TURNS
are in-memory only, k persists across a fresh CableState() (simulating a
backend restart). The physical max-extension LENGTH is the one exception
(train tab calibration overhaul item 3): it persists across both reset() and
re-homing, and latch_home() reapplies it against the new home reference
automatically."""

import pytest

from config import board_constants
from core.cable.geometry import radians_from_turns
from core.cable.state import CableState


def _tmp_sidecar(tmp_path):
    return tmp_path / "spool_calibration.json"


def test_fresh_state_is_unhomed_and_has_default_k(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state.is_homed is False
    assert state.has_max is False
    assert state.k == board_constants.SPOOL_CORRECTION_K_DEFAULT


def test_latch_home_sets_is_homed(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state.latch_home(12.5)
    assert state.is_homed is True
    assert state.home_turns == 12.5


def test_latching_a_new_home_reapplies_persisted_max_extension(tmp_path):
    """Item 3: re-homing invalidates the old (now stale) TURNS reference, but
    the physical max-extension LENGTH survives and is immediately reapplied
    against the new home -- no recalibration needed on every re-home."""
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state.latch_home(0.0)
    state.set_max(marked_turns=10.0, enforced_turns=9.0)
    length_m = state.max_extension_length_m
    assert state.has_max is True

    state.latch_home(1.0)  # re-homed -- old TURNS reference is stale
    assert state.has_max is True
    assert state.max_extension_length_m == pytest.approx(length_m)
    # Same physical length from the new home, so the enforced turns shift by
    # exactly the home offset (fixed-radius model: 9.0 turns from the old
    # home == 9.0 turns from the new one, offset by the +1.0 turn shift).
    assert state.max_turns == pytest.approx(10.0)
    assert state.marked_max_turns == pytest.approx(10.0)


def test_latching_a_new_home_without_prior_max_stays_unset(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state.latch_home(0.0)
    assert state.has_max is False
    state.latch_home(1.0)
    assert state.has_max is False


def test_reset_clears_home_and_max_but_not_k(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state.set_k(0.0003)
    state.latch_home(0.0)
    state.set_max(marked_turns=10.0, enforced_turns=9.0)

    state.reset()

    assert state.is_homed is False
    assert state.has_max is False
    assert state.k == 0.0003  # untouched -- physical spool property


def test_max_extension_length_survives_reset_and_reapplies_on_rehome(tmp_path):
    """Item 3's core guarantee: reset() alone leaves max un-set (no home to
    reapply it against), but the next successful Home brings it straight
    back -- no recalibration prompt."""
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state.latch_home(0.0)
    state.set_max(marked_turns=10.0, enforced_turns=9.0)
    length_m = state.max_extension_length_m

    state.reset()
    assert state.has_max is False
    assert state.max_extension_length_m == pytest.approx(length_m)  # survives reset

    state.latch_home(2.0)  # simulates the next Home after reset
    assert state.has_max is True
    assert state.max_extension_length_m == pytest.approx(length_m)


def test_max_extension_length_persists_across_a_fresh_instance(tmp_path):
    """Simulates a backend restart: unlike home/max turns, the physical
    max-extension length is meant to survive it."""
    sidecar = _tmp_sidecar(tmp_path)
    state1 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state1.latch_home(0.0)
    state1.set_max(marked_turns=10.0, enforced_turns=9.0)

    state2 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state2.is_homed is False
    assert state2.has_max is False  # no home yet in the fresh instance
    assert state2.max_extension_length_m == pytest.approx(state1.max_extension_length_m)

    state2.latch_home(0.0)  # first Home after the simulated restart
    assert state2.has_max is True


# ---- persistence split: k survives a fresh instance, home/max never do ----

def test_k_persists_across_a_fresh_instance_simulating_backend_restart(tmp_path):
    sidecar = _tmp_sidecar(tmp_path)

    state1 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state1.set_k(0.00042)
    state1.latch_home(5.0)
    state1.set_max(marked_turns=15.0, enforced_turns=14.0)

    # A fresh instance against the same sidecar path simulates a backend
    # restart: k must survive, home/max must NOT (spec §6 hard requirement).
    state2 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state2.k == 0.00042
    assert state2.is_homed is False
    assert state2.has_max is False


def test_missing_sidecar_file_falls_back_to_default_k(tmp_path):
    sidecar = tmp_path / "does_not_exist.json"
    state = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state.k == board_constants.SPOOL_CORRECTION_K_DEFAULT


def test_corrupt_sidecar_file_falls_back_to_default_k(tmp_path):
    sidecar = _tmp_sidecar(tmp_path)
    sidecar.write_text("not valid json{{{")
    state = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state.k == board_constants.SPOOL_CORRECTION_K_DEFAULT


# ---- live-adjustable spool radius (r0) and homing settings ----

def test_fresh_state_has_default_r0_and_homing_settings(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state.r0 == board_constants.SPOOL_RADIUS_M
    assert state.homing_current_threshold_a == board_constants.HOMING_CURRENT_THRESHOLD_A
    assert state.homing_velocity_turns_s == board_constants.HOMING_VELOCITY_TURNS_S
    assert state.homing_current_limit_a == board_constants.HOMING_CURRENT_LIMIT_A


def test_set_r0_persists_across_a_fresh_instance(tmp_path):
    sidecar = _tmp_sidecar(tmp_path)
    state1 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state1.set_r0(0.04)
    state2 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state2.r0 == 0.04


def test_set_r0_rejects_nonpositive(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    with pytest.raises(ValueError):
        state.set_r0(0.0)
    with pytest.raises(ValueError):
        state.set_r0(-0.01)


def test_set_homing_settings_persists_across_a_fresh_instance(tmp_path):
    sidecar = _tmp_sidecar(tmp_path)
    state1 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state1.set_homing_settings(current_threshold_a=2.0, velocity_turns_s=0.5, current_limit_a=7.5)
    state2 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state2.homing_current_threshold_a == 2.0
    assert state2.homing_velocity_turns_s == 0.5
    assert state2.homing_current_limit_a == 7.5


# ---- experimental multi-point spool-growth calibration ----

def _tmp_growth_sidecar(tmp_path):
    return tmp_path / "spool_growth_calibration.json"


def _tmp_torque_sidecar(tmp_path):
    return tmp_path / "torque_calibration.json"


def _state(tmp_path):
    return CableState(
        sidecar_path=_tmp_sidecar(tmp_path),
        growth_sidecar_path=_tmp_growth_sidecar(tmp_path),
        torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path),
    )


def _valid_growth_points(r0, t1_turns=2.0, t2_turns=5.0, slope1=0.0002, slope2=0.0003):
    """A physically-consistent (turns, length_m) pair for a given r0 -- small
    positive per-segment slopes, so the fitted model stays comfortably
    non-degenerate. Derived rather than hand-picked (see the equivalent
    helper in test_geometry.py) to avoid brittle/wrong magic numbers."""
    theta1 = radians_from_turns(t1_turns)
    theta2 = radians_from_turns(t2_turns)
    l1 = r0 * theta1 + (slope1 / 2.0) * theta1 * theta1
    r_end1 = r0 + slope1 * theta1
    d2 = theta2 - theta1
    l2 = l1 + r_end1 * d2 + (slope2 / 2.0) * d2 * d2
    return [(t1_turns, l1), (t2_turns, l2)]


def test_fresh_state_has_no_growth_points_and_fixed_radius_geometry(tmp_path):
    state = _state(tmp_path)
    assert state.spool_growth_points == []
    assert state.pending_growth_points == []
    assert state.spool_growth_calibration_in_progress is False
    assert state.spool_geometry.active_model == "fixed_radius"


def test_set_growth_points_persists_across_a_fresh_instance(tmp_path):
    state1 = _state(tmp_path)
    points = _valid_growth_points(state1.r0)
    state1.set_growth_points(points)

    state2 = _state(tmp_path)
    assert state2.spool_growth_points == points
    assert state2.spool_geometry.active_model == "piecewise"


def test_set_growth_points_rebuilds_spool_geometry_immediately(tmp_path):
    state = _state(tmp_path)
    assert state.spool_geometry.active_model == "fixed_radius"
    state.set_growth_points(_valid_growth_points(state.r0)[:1])
    assert state.spool_geometry.active_model == "piecewise"
    state.set_growth_points([])
    assert state.spool_geometry.active_model == "fixed_radius"


def test_set_growth_points_rejects_invalid_points_without_partial_commit(tmp_path):
    state = _state(tmp_path)
    with pytest.raises(ValueError):
        # Sorted by turns this is (2.0, 0.20) then (5.0, 0.10) -- length
        # decreases as turns increase, physically impossible.
        state.set_growth_points([(5.0, 0.10), (2.0, 0.20)])
    # A bad set must never partially overwrite a good/empty one.
    assert state.spool_growth_points == []
    assert state.spool_geometry.active_model == "fixed_radius"


def test_set_r0_and_set_k_rebuild_spool_geometry(tmp_path):
    state = _state(tmp_path)
    state.set_k(0.001)
    assert state.spool_geometry.k == 0.001
    state.set_r0(0.04)
    assert state.spool_geometry.r0 == 0.04


def test_reset_does_not_touch_growth_points(tmp_path):
    state = _state(tmp_path)
    points = _valid_growth_points(state.r0)[:1]
    state.set_growth_points(points)
    state.latch_home(0.0)
    state.set_max(marked_turns=10.0, enforced_turns=9.0)

    state.reset()

    assert state.spool_growth_points == points
    assert state.is_homed is False


def test_pending_growth_point_add_remove_clear(tmp_path):
    state = _state(tmp_path)
    state.add_pending_growth_point(2.0, 0.15)
    state.add_pending_growth_point(5.0, 0.40)
    assert state.pending_growth_points == [(2.0, 0.15), (5.0, 0.40)]

    state.remove_pending_growth_point(0)
    assert state.pending_growth_points == [(5.0, 0.40)]

    state.clear_pending_growth_points()
    assert state.pending_growth_points == []


def test_remove_pending_growth_point_rejects_out_of_range_index(tmp_path):
    state = _state(tmp_path)
    with pytest.raises(ValueError):
        state.remove_pending_growth_point(0)


# ---- manual max-extension entry ----

def test_set_max_extension_manual_requires_homed(tmp_path):
    state = _state(tmp_path)
    with pytest.raises(RuntimeError):
        state.set_max_extension_manual(1.5)


def test_set_max_extension_manual_matches_physical_flow_convention(tmp_path):
    state = _state(tmp_path)
    state.latch_home(0.0)
    state.set_max_extension_manual(1.5)

    assert state.has_max is True
    # No-margin convention: marked == enforced, same as confirm_max.
    assert state.max_turns == pytest.approx(state.marked_max_turns)
    # Round-trips back through the same (fixed-radius, by default) model.
    assert state.spool_geometry.length_from_turns_delta(state.max_turns - state.home_turns) == pytest.approx(1.5)


def test_set_max_extension_manual_rejects_too_close_to_home(tmp_path):
    state = _state(tmp_path)
    state.latch_home(0.0)
    with pytest.raises(ValueError):
        state.set_max_extension_manual(0.0001)


def test_set_max_extension_manual_uses_growth_points_when_present(tmp_path):
    state = _state(tmp_path)
    points = _valid_growth_points(state.r0)
    state.set_growth_points(points)
    state.latch_home(0.0)
    _, l2 = points[1]
    state.set_max_extension_manual(l2)
    assert state.max_turns == pytest.approx(points[1][0])


# ---- k bound check against the actual calibrated travel range ----

def test_check_k_against_travel_range_noop_without_homed_max(tmp_path):
    state = _state(tmp_path)
    state.check_k_against_travel_range(0.5)  # must not raise -- nothing to check yet


def test_check_k_against_travel_range_rejects_k_that_collapses_radius(tmp_path):
    state = _state(tmp_path)
    state.latch_home(0.0)
    state.set_max(marked_turns=20.0, enforced_turns=20.0)  # 20 turns from home
    # A strongly negative k over 20 turns collapses r_eff well below the floor.
    with pytest.raises(ValueError):
        state.check_k_against_travel_range(-0.005)


def test_check_k_against_travel_range_accepts_safe_k(tmp_path):
    state = _state(tmp_path)
    state.latch_home(0.0)
    state.set_max(marked_turns=20.0, enforced_turns=20.0)
    state.check_k_against_travel_range(0.0005)  # must not raise


def test_set_homing_settings_updates_only_given_fields(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    original_velocity = state.homing_velocity_turns_s
    original_limit = state.homing_current_limit_a
    state.set_homing_settings(current_threshold_a=1.5)
    assert state.homing_current_threshold_a == 1.5
    assert state.homing_velocity_turns_s == original_velocity
    assert state.homing_current_limit_a == original_limit


def test_set_homing_settings_rejects_nonpositive_values(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    with pytest.raises(ValueError):
        state.set_homing_settings(current_threshold_a=0.0)
    with pytest.raises(ValueError):
        state.set_homing_settings(velocity_turns_s=-0.1)


def test_set_homing_settings_rejects_limit_at_or_below_threshold(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    with pytest.raises(ValueError):
        state.set_homing_settings(current_threshold_a=3.0, current_limit_a=3.0)
    with pytest.raises(ValueError):
        state.set_homing_settings(current_threshold_a=3.0, current_limit_a=2.0)


def test_set_homing_settings_rejects_limit_above_operating_limit(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    with pytest.raises(ValueError):
        state.set_homing_settings(current_limit_a=board_constants.MOTOR_CURRENT_LIM + 1.0)


def test_set_homing_settings_rejected_call_does_not_partially_apply(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    original_threshold = state.homing_current_threshold_a
    with pytest.raises(ValueError):
        state.set_homing_settings(current_threshold_a=5.0, current_limit_a=1.0)  # limit < threshold
    assert state.homing_current_threshold_a == original_threshold  # unchanged, not half-applied


# ---- live-adjustable max-extension calibration hold force ----

def test_fresh_state_has_default_calib_hold_force(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state.calib_hold_force_n == board_constants.CALIB_HOLD_FORCE_N


def test_set_calib_hold_force_persists_across_a_fresh_instance(tmp_path):
    sidecar = _tmp_sidecar(tmp_path)
    state1 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state1.set_calib_hold_force(4.5)
    state2 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state2.calib_hold_force_n == 4.5


def test_set_calib_hold_force_rejects_nonpositive(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    with pytest.raises(ValueError):
        state.set_calib_hold_force(0.0)
    with pytest.raises(ValueError):
        state.set_calib_hold_force(-1.0)


# ---- live-adjustable force/safety "feel" settings ----

def test_fresh_state_has_default_force_settings(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state.letgo_velocity_turns_s == board_constants.LETGO_VELOCITY_TURNS_S
    assert state.letgo_debounce_samples == board_constants.LETGO_DEBOUNCE_SAMPLES
    assert state.hold_duration_s == board_constants.HOLD_DURATION_S
    assert state.force_ramp_in_s == board_constants.FORCE_RAMP_IN_S
    assert state.force_ramp_out_s == board_constants.FORCE_RAMP_OUT_S
    assert state.isokinetic_governor_gain == board_constants.ISOKINETIC_GOVERNOR_GAIN
    assert state.isokinetic_velocity_filter_alpha == board_constants.ISOKINETIC_VELOCITY_FILTER_ALPHA
    assert state.max_extension_force_taper_m == board_constants.MAX_EXTENSION_FORCE_TAPER_M
    assert state.position_guard_warning_turns == board_constants.POSITION_GUARD_WARNING_TURNS
    assert state.position_guard_hard_turns == board_constants.POSITION_GUARD_TOLERANCE_TURNS


def test_set_force_settings_persists_across_a_fresh_instance(tmp_path):
    sidecar = _tmp_sidecar(tmp_path)
    state1 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    state1.set_force_settings(letgo_velocity_turns_s=0.3, hold_duration_s=1.0)
    state2 = CableState(sidecar_path=sidecar, growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    assert state2.letgo_velocity_turns_s == 0.3
    assert state2.hold_duration_s == 1.0


def test_set_force_settings_updates_only_given_fields(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    original_ramp_out = state.force_ramp_out_s
    state.set_force_settings(force_ramp_in_s=0.25)
    assert state.force_ramp_in_s == 0.25
    assert state.force_ramp_out_s == original_ramp_out


def test_set_force_settings_rejects_nonpositive_values(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    with pytest.raises(ValueError):
        state.set_force_settings(letgo_velocity_turns_s=0.0)
    with pytest.raises(ValueError):
        state.set_force_settings(force_ramp_in_s=-0.1)
    with pytest.raises(ValueError):
        state.set_force_settings(position_guard_warning_turns=0.0)


def test_set_force_settings_rejects_hard_tolerance_below_warning(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    with pytest.raises(ValueError):
        state.set_force_settings(position_guard_warning_turns=0.1, position_guard_hard_turns=0.05)


def test_set_force_settings_rejects_out_of_range_filter_alpha(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    with pytest.raises(ValueError):
        state.set_force_settings(isokinetic_velocity_filter_alpha=0.0)
    with pytest.raises(ValueError):
        state.set_force_settings(isokinetic_velocity_filter_alpha=1.5)


def test_set_force_settings_rejected_call_does_not_partially_apply(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path), growth_sidecar_path=_tmp_growth_sidecar(tmp_path), torque_calibration_sidecar_path=_tmp_torque_sidecar(tmp_path))
    original = state.letgo_velocity_turns_s
    with pytest.raises(ValueError):
        state.set_force_settings(letgo_velocity_turns_s=0.5, force_ramp_in_s=-1.0)
    assert state.letgo_velocity_turns_s == original
