"""core/cable/torque_calibration.py tests."""

import pytest

from core.cable.torque_calibration import (
    GRAVITY_M_S2,
    STATIC_VELOCITY_DEADBAND_TURNS_S,
    TorqueCalibration,
    TorqueCalibrationPoint,
    fit_linear,
)

R_EFF = 0.04


def _point(known_weight_kg, raw_torque_nm, r_eff_m=R_EFF, direction="up"):
    return TorqueCalibrationPoint(
        known_weight_kg=known_weight_kg, raw_torque_nm=raw_torque_nm, r_eff_m=r_eff_m, direction=direction
    )


def test_expected_torque_nm_is_weight_times_gravity_times_r_eff():
    p = _point(known_weight_kg=5.0, raw_torque_nm=1.0, r_eff_m=0.04)
    assert p.expected_torque_nm == pytest.approx(5.0 * GRAVITY_M_S2 * 0.04)


def test_point_rejects_invalid_direction():
    with pytest.raises(ValueError):
        _point(known_weight_kg=5.0, raw_torque_nm=1.0, direction="sideways")


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
        _point(known_weight_kg=5.0, raw_torque_nm=-0.9456, r_eff_m=0.0361, direction="up"),
        _point(known_weight_kg=10.0, raw_torque_nm=-4.6892, r_eff_m=0.0376, direction="up"),
    ]
    scale, offset = fit_linear(points)
    assert scale > 0.0
    calib = TorqueCalibration(points)
    # Both points still round-trip through the fitted model (a line through
    # 2 points is exact) -- the corrected magnitude for each point's own raw
    # reading matches its expected torque, sign matching the original raw
    # reading's sign (negative, in this scenario). Use a clearly "up"
    # velocity so the up-direction line (the one these points belong to) is
    # the one selected.
    for p in points:
        assert calib.corrected_torque_nm(p.raw_torque_nm, cable_velocity_turns_s=-1.0) == pytest.approx(
            -p.expected_torque_nm, rel=1e-3
        )


class TestTorqueCalibration:
    def test_uncalibrated_is_identity(self):
        calib = TorqueCalibration()
        assert calib.corrected_torque_nm(0.5, cable_velocity_turns_s=-1.0) == pytest.approx(0.5)
        assert calib.corrected_torque_nm(0.5, cable_velocity_turns_s=1.0) == pytest.approx(0.5)
        assert calib.corrected_torque_nm(0.5, cable_velocity_turns_s=0.0) == pytest.approx(0.5)
        assert calib.raw_torque_nm_for_corrected(0.5) == pytest.approx(0.5)

    def test_points_are_split_by_direction(self):
        up = _point(5.0, 0.9, direction="up")
        down = _point(5.0, 1.4, direction="down")
        calib = TorqueCalibration([up, down])
        assert calib.points_by_direction["up"] == [up]
        assert calib.points_by_direction["down"] == [down]
        # Single-point-per-direction fit -- exact round trip for each
        # direction's own raw reading through its own line.
        assert calib.corrected_torque_nm(0.9, cable_velocity_turns_s=-1.0) == pytest.approx(up.expected_torque_nm)
        assert calib.corrected_torque_nm(1.4, cable_velocity_turns_s=1.0) == pytest.approx(down.expected_torque_nm)

    def test_only_one_direction_calibrated_other_direction_stays_identity(self):
        calib = TorqueCalibration([_point(5.0, 0.9, direction="up")])
        assert calib.corrected_torque_nm(2.0, cable_velocity_turns_s=1.0) == pytest.approx(2.0)  # down: identity
        assert calib.corrected_torque_nm(0.9, cable_velocity_turns_s=-1.0) == pytest.approx(  # up: fitted
            _point(5.0, 0.9, direction="up").expected_torque_nm
        )

    def test_near_zero_velocity_uses_blended_scale_and_zero_offset(self):
        up = _point(5.0, -0.9456, r_eff_m=0.0361, direction="up")
        down = _point(10.0, 4.6892, r_eff_m=0.0376, direction="down")
        calib = TorqueCalibration([up, down])
        assert calib.offset["up"] == 0.0  # sanity: single-point fits have no offset
        assert calib.offset["down"] == 0.0
        blended_scale = (calib.scale["up"] + calib.scale["down"]) / 2.0
        assert calib.corrected_torque_nm(2.0, cable_velocity_turns_s=0.0) == pytest.approx(2.0 * blended_scale)
        # Anything inside the deadband behaves the same as exactly zero.
        assert calib.corrected_torque_nm(
            2.0, cable_velocity_turns_s=STATIC_VELOCITY_DEADBAND_TURNS_S / 2.0
        ) == pytest.approx(2.0 * blended_scale)

    def test_static_blend_drops_offset_even_when_directions_have_one(self):
        # Two points per direction so each direction's fit gets a real
        # (nonzero) offset, not just a scale -- confirms the static blend
        # forces offset to 0 rather than also averaging the offsets.
        calib = TorqueCalibration([
            _point(5.0, 0.9, direction="up"),
            _point(10.0, 1.7, direction="up"),
            _point(5.0, 1.3, direction="down"),
            _point(10.0, 2.4, direction="down"),
        ])
        assert calib.offset["up"] != 0.0
        assert calib.offset["down"] != 0.0
        blended_scale = (calib.scale["up"] + calib.scale["down"]) / 2.0
        assert calib.corrected_torque_nm(2.0, cable_velocity_turns_s=0.0) == pytest.approx(2.0 * blended_scale)

    def test_corrected_and_raw_are_inverses_per_direction(self):
        calib = TorqueCalibration([
            _point(5.0, 0.9, direction="up"),
            _point(10.0, 1.7, direction="up"),
            _point(5.0, 1.3, direction="down"),
            _point(10.0, 2.4, direction="down"),
        ])
        for velocity in (-1.0, 1.0, 0.0):
            raw = 0.35
            corrected = calib.corrected_torque_nm(raw, cable_velocity_turns_s=velocity)
            assert calib.raw_torque_nm_for_corrected(corrected, cable_velocity_turns_s=velocity) == pytest.approx(raw)

    def test_raw_torque_nm_for_corrected_handles_zero_scale_without_raising(self):
        calib = TorqueCalibration()
        calib.scale["up"] = 0.0
        calib.offset["up"] = 1.0
        assert calib.raw_torque_nm_for_corrected(5.0, cable_velocity_turns_s=-1.0) == 0.0

    def test_corrected_torque_nm_preserves_sign_of_raw(self):
        calib = TorqueCalibration([_point(5.0, 0.9, direction="up"), _point(10.0, 1.7, direction="up")])
        positive = calib.corrected_torque_nm(0.9, cable_velocity_turns_s=-1.0)
        negative = calib.corrected_torque_nm(-0.9, cable_velocity_turns_s=-1.0)
        assert positive > 0.0
        assert negative == pytest.approx(-positive)

    def test_corrected_torque_nm_of_zero_is_zero_even_with_a_nonzero_offset(self):
        calib = TorqueCalibration([_point(5.0, 0.9, direction="up"), _point(10.0, 1.7, direction="up")])
        assert calib.offset["up"] != 0.0  # sanity: this model actually has an offset to guard against
        assert calib.corrected_torque_nm(0.0, cable_velocity_turns_s=-1.0) == 0.0

    def test_raw_torque_nm_for_corrected_preserves_sign(self):
        calib = TorqueCalibration([_point(5.0, 0.9, direction="up"), _point(10.0, 1.7, direction="up")])
        positive = calib.raw_torque_nm_for_corrected(2.0, cable_velocity_turns_s=-1.0)
        negative = calib.raw_torque_nm_for_corrected(-2.0, cable_velocity_turns_s=-1.0)
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
            _point(known_weight_kg=5.0, raw_torque_nm=-0.9456, r_eff_m=0.0361, direction="up"),
            _point(known_weight_kg=10.0, raw_torque_nm=-4.6892, r_eff_m=0.0376, direction="up"),
        ])
        assert calib.offset["up"] > 0.0  # sanity
        tiny = calib.offset["up"] / 2.0
        assert calib.raw_torque_nm_for_corrected(tiny, cable_velocity_turns_s=-1.0) == 0.0
        assert calib.raw_torque_nm_for_corrected(-tiny, cable_velocity_turns_s=-1.0) == 0.0

    def test_describe_includes_both_directions_and_static_blend(self):
        calib = TorqueCalibration([_point(5.0, 0.9, direction="up"), _point(5.0, 1.3, direction="down")])
        d = calib.describe()
        assert set(d["directions"]) == {"up", "down"}
        for direction in ("up", "down"):
            entry = d["directions"][direction]
            assert entry["scale"] == pytest.approx(calib.scale[direction])
            assert entry["offset"] == pytest.approx(calib.offset[direction])
            assert "corrected_torque_nm" in entry["equation"]
            assert len(entry["points"]) == 1
        assert d["directions"]["up"]["points"][0]["known_weight_kg"] == 5.0
        assert d["static_blend"]["offset"] == 0.0
        assert d["static_blend"]["scale"] == pytest.approx((calib.scale["up"] + calib.scale["down"]) / 2.0)

    def test_describe_top_level_mirrors_static_blend_for_direction_agnostic_callers(self):
        calib = TorqueCalibration([_point(5.0, 0.9, direction="up"), _point(5.0, 1.3, direction="down")])
        d = calib.describe()
        assert d["scale"] == pytest.approx(d["static_blend"]["scale"])
        assert d["offset"] == 0.0
        assert len(d["points"]) == 2  # both directions pooled
