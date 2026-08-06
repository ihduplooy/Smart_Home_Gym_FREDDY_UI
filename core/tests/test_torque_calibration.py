"""core/cable/torque_calibration.py tests."""

import pytest

from core.cable.torque_calibration import (
    GRAVITY_M_S2,
    TorqueCalibration,
    TorqueCalibrationPoint,
    fit_linear,
)

R_EFF = 0.04


def _point(known_weight_kg, raw_torque_nm, r_eff_m=R_EFF):
    return TorqueCalibrationPoint(known_weight_kg=known_weight_kg, raw_torque_nm=raw_torque_nm, r_eff_m=r_eff_m)


def test_expected_torque_nm_is_weight_times_gravity_times_r_eff():
    p = _point(known_weight_kg=5.0, raw_torque_nm=1.0, r_eff_m=0.04)
    assert p.expected_torque_nm == pytest.approx(5.0 * GRAVITY_M_S2 * 0.04)


def test_fit_linear_with_no_points_is_identity():
    scale, offset = fit_linear([])
    assert scale == 1.0
    assert offset == 0.0


def test_fit_linear_with_one_point_solves_scale_only():
    # expected = 5*9.81*0.04 = 1.962; raw measured lower (0.9) -> scale > 1
    p = _point(known_weight_kg=5.0, raw_torque_nm=0.9)
    scale, offset = fit_linear([p])
    assert offset == 0.0
    assert scale == pytest.approx(p.expected_torque_nm / 0.9)


def test_fit_linear_with_one_point_and_zero_raw_falls_back_to_identity():
    scale, offset = fit_linear([_point(known_weight_kg=5.0, raw_torque_nm=0.0)])
    assert (scale, offset) == (1.0, 0.0)


def test_fit_linear_recovers_exact_scale_and_offset_from_synthetic_points():
    # Construct raw readings from a KNOWN scale/offset, then confirm the fit
    # recovers them: expected = true_scale*raw + true_offset -- solve raw
    # from expected under that relationship for a few different weights.
    true_scale, true_offset = 1.1, 0.05
    points = []
    for weight_kg in (2.0, 5.0, 10.0):
        expected = weight_kg * GRAVITY_M_S2 * R_EFF
        raw = (expected - true_offset) / true_scale
        points.append(_point(known_weight_kg=weight_kg, raw_torque_nm=raw))

    scale, offset = fit_linear(points)
    assert scale == pytest.approx(true_scale, rel=1e-6)
    assert offset == pytest.approx(true_offset, abs=1e-6)


def test_fit_linear_with_identical_raw_values_falls_back_to_scale_only():
    # No spread in raw_torque_nm -- can't fit a slope, falls back to scaling
    # against the mean rather than dividing by zero.
    points = [_point(known_weight_kg=2.0, raw_torque_nm=1.0), _point(known_weight_kg=4.0, raw_torque_nm=1.0)]
    scale, offset = fit_linear(points)
    assert offset == 0.0
    mean_expected = (points[0].expected_torque_nm + points[1].expected_torque_nm) / 2.0
    assert scale == pytest.approx(mean_expected / 1.0)


def test_fit_linear_with_negative_raw_readings_still_yields_positive_scale():
    # Real-bench scenario (surfaced 5 Aug 2026): holding a known weight
    # against gravity on this rig reads a NEGATIVE raw_torque_nm at both
    # points, while expected_torque_nm is always positive (a weight can't be
    # negative). Fitting against the signed raw value used to produce a
    # negative scale that happened to reproduce these two points exactly but
    # was physically nonsensical for any raw reading of the opposite sign
    # (see module docstring). Fitting against |raw| instead must always
    # yield a positive scale for this same data.
    points = [
        _point(known_weight_kg=5.0, raw_torque_nm=-0.9456, r_eff_m=0.0361),
        _point(known_weight_kg=10.0, raw_torque_nm=-4.6892, r_eff_m=0.0376),
    ]
    scale, offset = fit_linear(points)
    assert scale > 0.0
    calib = TorqueCalibration(points)
    # Both points still round-trip through the fitted model (a line through
    # 2 points is exact) -- the corrected magnitude for each point's own raw
    # reading matches its expected torque, sign matching the original raw
    # reading's sign (negative, in this scenario).
    for p in points:
        assert calib.corrected_torque_nm(p.raw_torque_nm) == pytest.approx(-p.expected_torque_nm, rel=1e-3)


class TestTorqueCalibration:
    def test_uncalibrated_is_identity(self):
        calib = TorqueCalibration()
        assert calib.corrected_torque_nm(0.5) == pytest.approx(0.5)
        assert calib.raw_torque_nm_for_corrected(0.5) == pytest.approx(0.5)

    def test_corrected_and_raw_are_inverses(self):
        calib = TorqueCalibration([_point(5.0, 0.9), _point(10.0, 1.7)])
        raw = 0.35
        corrected = calib.corrected_torque_nm(raw)
        assert calib.raw_torque_nm_for_corrected(corrected) == pytest.approx(raw)

    def test_raw_torque_nm_for_corrected_handles_zero_scale_without_raising(self):
        calib = TorqueCalibration()
        calib.scale = 0.0
        calib.offset = 1.0
        assert calib.raw_torque_nm_for_corrected(5.0) == 0.0

    def test_corrected_torque_nm_preserves_sign_of_raw(self):
        calib = TorqueCalibration([_point(5.0, 0.9), _point(10.0, 1.7)])
        positive = calib.corrected_torque_nm(0.9)
        negative = calib.corrected_torque_nm(-0.9)
        assert positive > 0.0
        assert negative == pytest.approx(-positive)

    def test_corrected_torque_nm_of_zero_is_zero_even_with_a_nonzero_offset(self):
        calib = TorqueCalibration([_point(5.0, 0.9), _point(10.0, 1.7)])
        assert calib.offset != 0.0  # sanity: this model actually has an offset to guard against
        assert calib.corrected_torque_nm(0.0) == 0.0

    def test_raw_torque_nm_for_corrected_preserves_sign(self):
        calib = TorqueCalibration([_point(5.0, 0.9), _point(10.0, 1.7)])
        positive = calib.raw_torque_nm_for_corrected(2.0)
        negative = calib.raw_torque_nm_for_corrected(-2.0)
        assert positive > 0.0
        assert negative == pytest.approx(-positive)

    def test_raw_torque_nm_for_corrected_floors_magnitude_at_zero_below_offset(self):
        # A corrected torque smaller in magnitude than the fitted offset has
        # no valid (non-negative) raw magnitude that produces it -- clamp to
        # 0 rather than returning a nonsensical negative raw command. Uses
        # the same bench-realistic points as
        # test_fit_linear_with_negative_raw_readings_still_yields_positive_scale
        # (offset fits positive there, ~1.28).
        calib = TorqueCalibration([
            _point(known_weight_kg=5.0, raw_torque_nm=-0.9456, r_eff_m=0.0361),
            _point(known_weight_kg=10.0, raw_torque_nm=-4.6892, r_eff_m=0.0376),
        ])
        assert calib.offset > 0.0  # sanity
        tiny = calib.offset / 2.0
        assert calib.raw_torque_nm_for_corrected(tiny) == 0.0
        assert calib.raw_torque_nm_for_corrected(-tiny) == 0.0

    def test_describe_includes_equation_scale_offset_and_points(self):
        calib = TorqueCalibration([_point(5.0, 0.9)])
        d = calib.describe()
        assert d["scale"] == pytest.approx(calib.scale)
        assert d["offset"] == pytest.approx(calib.offset)
        assert "corrected_torque_nm" in d["equation"]
        assert len(d["points"]) == 1
        assert d["points"][0]["known_weight_kg"] == 5.0
        assert d["points"][0]["raw_torque_nm"] == 0.9
        assert d["points"][0]["expected_torque_nm"] == pytest.approx(5.0 * GRAVITY_M_S2 * R_EFF)
