"""core/cable/torque_calibration_run.py tests."""

import pytest

from core.cable.torque_calibration_run import (
    DEFAULT_MIN_MOVING_VELOCITY_TURNS_S,
    RunSample,
    extract_calibration_points_from_run,
)

R_EFF = 0.04


def _s(cable_velocity_turns_s, raw_torque_nm, r_eff_m=R_EFF):
    return RunSample(cable_velocity_turns_s=cable_velocity_turns_s, raw_torque_nm=raw_torque_nm, r_eff_m=r_eff_m)


def _trapezoid(sign, peak_velocity, raw_torque_nm, ramp_len=3, cruise_len=5, r_eff_m=R_EFF):
    """A single rep leg: ramp up to peak velocity, cruise at peak, ramp back
    down -- the plateau extractor should only keep the cruise samples."""
    samples = []
    for i in range(1, ramp_len + 1):
        samples.append(_s(sign * peak_velocity * i / (ramp_len + 1), raw_torque_nm + 10.0, r_eff_m))  # transient torque
    for _ in range(cruise_len):
        samples.append(_s(sign * peak_velocity, raw_torque_nm, r_eff_m))
    for i in range(ramp_len, 0, -1):
        samples.append(_s(sign * peak_velocity * i / (ramp_len + 1), raw_torque_nm + 10.0, r_eff_m))
    return samples


def _turnaround(n=3):
    return [_s(0.0, 0.0) for _ in range(n)]


def test_no_moving_samples_yields_no_points():
    samples = [_s(0.0, 1.0) for _ in range(10)]
    results = extract_calibration_points_from_run(samples, known_weight_kg=5.0)
    assert results["up"] is None
    assert results["down"] is None


def test_single_up_leg_extracts_up_point_only():
    samples = _trapezoid(sign=-1, peak_velocity=1.0, raw_torque_nm=-0.95)
    results = extract_calibration_points_from_run(samples, known_weight_kg=5.0)
    assert results["down"] is None
    up = results["up"]
    assert up is not None
    assert up.direction == "up"
    assert up.rep_count == 1
    assert up.point.known_weight_kg == 5.0
    assert up.point.direction == "up"
    assert up.point.raw_torque_nm == pytest.approx(-0.95)  # transients excluded from the average
    assert up.point.r_eff_m == pytest.approx(R_EFF)


def test_single_down_leg_extracts_down_point_only():
    samples = _trapezoid(sign=1, peak_velocity=1.0, raw_torque_nm=-0.4)
    results = extract_calibration_points_from_run(samples, known_weight_kg=5.0)
    assert results["up"] is None
    down = results["down"]
    assert down is not None
    assert down.direction == "down"
    assert down.point.raw_torque_nm == pytest.approx(-0.4)


def test_multiple_reps_average_per_rep_not_per_sample():
    # A longer, noisier leg must not outweigh a short one -- each leg's own
    # mean contributes equally to the final average.
    leg_a = _trapezoid(sign=-1, peak_velocity=1.0, raw_torque_nm=-1.0, cruise_len=2)
    leg_b = _trapezoid(sign=-1, peak_velocity=1.0, raw_torque_nm=-2.0, cruise_len=20)
    samples = leg_a + _turnaround() + leg_b
    results = extract_calibration_points_from_run(samples, known_weight_kg=5.0)
    up = results["up"]
    assert up.rep_count == 2
    assert up.per_rep_raw_torque_nm == pytest.approx([-1.0, -2.0])
    assert up.point.raw_torque_nm == pytest.approx(-1.5)  # (−1.0 + −2.0) / 2, NOT sample-weighted


def test_up_and_down_legs_in_one_run_both_extracted():
    up_leg = _trapezoid(sign=-1, peak_velocity=1.0, raw_torque_nm=-0.9)
    down_leg = _trapezoid(sign=1, peak_velocity=1.0, raw_torque_nm=-0.5)
    samples = up_leg + _turnaround() + down_leg + _turnaround()
    results = extract_calibration_points_from_run(samples, known_weight_kg=10.0)
    assert results["up"].point.raw_torque_nm == pytest.approx(-0.9)
    assert results["down"].point.raw_torque_nm == pytest.approx(-0.5)
    assert results["up"].point.known_weight_kg == 10.0
    assert results["down"].point.known_weight_kg == 10.0


def test_velocity_below_moving_threshold_is_not_a_rep_leg():
    tiny = DEFAULT_MIN_MOVING_VELOCITY_TURNS_S / 2.0
    samples = [_s(tiny, 5.0) for _ in range(10)]
    results = extract_calibration_points_from_run(samples, known_weight_kg=5.0)
    assert results["up"] is None
    assert results["down"] is None


def test_plateau_excludes_ramp_transients():
    # A leg whose cruise readings differ sharply from the accel/decel
    # transients -- the extracted point must match the cruise value, not be
    # dragged toward the transient value.
    samples = _trapezoid(sign=-1, peak_velocity=2.0, raw_torque_nm=-1.5, ramp_len=4, cruise_len=3)
    results = extract_calibration_points_from_run(samples, known_weight_kg=5.0)
    assert results["up"].point.raw_torque_nm == pytest.approx(-1.5)
