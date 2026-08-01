"""core/cable/geometry.py tests (exercise_tab_build_spec_layerA.md §8)."""

import math

import pytest

from core.cable.geometry import (
    SpoolGeometry,
    angle_from_length,
    angle_from_length_piecewise,
    build_growth_segments,
    calibrate_k,
    describe_model,
    length_from_angle,
    length_from_angle_piecewise,
    length_from_turns_delta,
    radians_from_turns,
    speed_m_s_from_turns_s,
    turns_delta_from_length,
    turns_from_radians,
)

R0 = 0.05  # SPOOL_RADIUS_M


# ---- turns <-> radians, the one conversion site ----

def test_radians_from_turns_and_back():
    assert radians_from_turns(1.0) == pytest.approx(2 * math.pi)
    assert turns_from_radians(2 * math.pi) == pytest.approx(1.0)
    assert turns_from_radians(radians_from_turns(3.7)) == pytest.approx(3.7)


def test_speed_m_s_from_turns_s():
    assert speed_m_s_from_turns_s(1.0, R0) == pytest.approx(2 * math.pi * R0)
    assert speed_m_s_from_turns_s(0.0, R0) == 0.0
    assert speed_m_s_from_turns_s(-2.0, R0) == pytest.approx(-2 * 2 * math.pi * R0)


# ---- round-trip consistency (hard requirement, spec §3.3) ----

@pytest.mark.parametrize("k", [0.0, 0.0003, -0.0003, 0.0005, -0.0005])
@pytest.mark.parametrize("theta", [0.1, 1.0, 5.0, 20.0])
def test_round_trip_angle_length_angle(k, theta):
    # k values span SPOOL_CORRECTION_K_BOUNDS: the model stays invertible
    # (r_eff > 0) across this theta range for any k within that bound (see
    # board_constants.py's reasoning for the bound) -- this is the "working
    # range" the round-trip requirement is scoped to (spec §3.3), not every
    # mathematically conceivable (theta, k) pair.
    length = length_from_angle(theta, R0, k)
    theta_back = angle_from_length(length, R0, k)
    assert theta_back == pytest.approx(theta, rel=1e-9, abs=1e-9)


@pytest.mark.parametrize("k", [0.0, 0.0003, -0.0003, 0.0005, -0.0005])
def test_round_trip_turns_delta(k):
    for turns in (0.5, 2.0, 8.0):
        length = length_from_turns_delta(turns, R0, k)
        turns_back = turns_delta_from_length(length, R0, k)
        assert turns_back == pytest.approx(turns, rel=1e-9, abs=1e-9)


# ---- k = 0 must be fully supported (fixed-radius model) ----

def test_k_zero_reduces_to_fixed_radius():
    theta = 4.0
    assert length_from_angle(theta, R0, 0.0) == pytest.approx(R0 * theta)
    assert angle_from_length(R0 * theta, R0, 0.0) == pytest.approx(theta)


def test_k_nonzero_differs_from_fixed_radius():
    theta = 4.0
    fixed = length_from_angle(theta, R0, 0.0)
    grown = length_from_angle(theta, R0, k=0.005)
    assert grown > fixed  # positive k => growing effective radius => more length


# ---- behaviour at theta = 0 ----

def test_zero_angle_is_zero_length_for_any_k():
    for k in (0.0, 0.005, -0.005):
        assert length_from_angle(0.0, R0, k) == 0.0
        assert angle_from_length(0.0, R0, k) == pytest.approx(0.0)


# ---- negative theta treated as a magnitude ----

def test_negative_theta_treated_as_magnitude():
    assert length_from_angle(-3.0, R0, 0.002) == pytest.approx(length_from_angle(3.0, R0, 0.002))


# ---- angle_from_length guards ----

def test_angle_from_length_rejects_negative_length():
    with pytest.raises(ValueError):
        angle_from_length(-1.0, R0, 0.0)


def test_angle_from_length_rejects_no_real_solution():
    # A strongly negative k makes the discriminant go negative for a large
    # enough length -- the model's effective radius would have to hit zero
    # and then imaginary before reaching this length.
    with pytest.raises(ValueError):
        angle_from_length(1000.0, R0, k=-0.5)


# ---- calibrate_k: recovers a known k from one measurement ----

@pytest.mark.parametrize("true_k", [0.0, 0.001, 0.004, -0.003])
def test_calibrate_k_recovers_known_k(true_k):
    theta_m_turns = 3.0  # comfortably above any reasonable min-theta guard
    length_at_theta_m = length_from_turns_delta(theta_m_turns, R0, true_k)

    recovered_k = calibrate_k(theta_m_turns, length_at_theta_m, R0)
    assert recovered_k == pytest.approx(true_k, abs=1e-9)


def test_calibrate_k_rejects_tiny_theta_m():
    with pytest.raises(ValueError):
        calibrate_k(
            theta_m_turns=0.001,  # ~0.006 rad
            measured_length_m=0.001,
            r0=R0,
            min_theta_m_rad=1.0,
        )


def test_calibrate_k_accepts_theta_m_above_the_guard():
    # Should not raise.
    k = calibrate_k(
        theta_m_turns=1.0,  # 2*pi rad, above a 1.0 rad guard
        measured_length_m=length_from_turns_delta(1.0, R0, 0.002),
        r0=R0,
        min_theta_m_rad=1.0,
    )
    assert k == pytest.approx(0.002, abs=1e-6)


def test_calibrate_k_rejects_out_of_range_result():
    # A wildly wrong measured length (e.g. a cm/m data-entry slip) produces
    # an implausible k that must be rejected, not silently stored.
    with pytest.raises(ValueError):
        calibrate_k(
            theta_m_turns=1.0,
            measured_length_m=50.0,  # absurd for this spool at 1 turn out
            r0=R0,
            k_bounds=(-0.01, 0.01),
        )


def test_calibrate_k_accepts_result_within_bounds():
    k = calibrate_k(
        theta_m_turns=2.0,
        measured_length_m=length_from_turns_delta(2.0, R0, 0.003),
        r0=R0,
        k_bounds=(-0.01, 0.01),
    )
    assert k == pytest.approx(0.003, abs=1e-6)


# ---- SpoolGeometry convenience wrapper ----

def test_spool_geometry_wrapper_matches_free_functions():
    geo = SpoolGeometry(r0=R0, k=0.002)
    turns = 5.0
    length = geo.length_from_turns_delta(turns)
    assert length == pytest.approx(length_from_turns_delta(turns, R0, 0.002))
    assert geo.turns_delta_from_length(length) == pytest.approx(turns, rel=1e-9)


def test_spool_geometry_defaults_to_fixed_radius_and_linear_labels():
    assert SpoolGeometry(r0=R0, k=0.0).active_model == "fixed_radius"
    assert SpoolGeometry(r0=R0, k=0.002).active_model == "linear"
    assert SpoolGeometry(r0=R0, k=0.0, growth_points=[(3.0, length_from_turns_delta(3.0, R0, 0.002))]).active_model == "piecewise"


# ---- piecewise growth model: build_growth_segments ----

def test_build_growth_segments_rejects_empty_points():
    with pytest.raises(ValueError):
        build_growth_segments(R0, [])


def test_build_growth_segments_rejects_non_increasing_theta():
    with pytest.raises(ValueError):
        build_growth_segments(R0, [(2.0, 0.1), (2.0, 0.2)])
    with pytest.raises(ValueError):
        build_growth_segments(R0, [(2.0, 0.1), (1.0, 0.2)])


def test_build_growth_segments_rejects_non_increasing_length():
    with pytest.raises(ValueError):
        build_growth_segments(R0, [(1.0, 0.1), (2.0, 0.1)])
    with pytest.raises(ValueError):
        build_growth_segments(R0, [(1.0, 0.2), (2.0, 0.1)])


def test_build_growth_segments_rejects_degenerate_radius():
    # A measured length far too short for the given theta forces the segment
    # slope so negative that r_eff collapses through the floor.
    with pytest.raises(ValueError):
        build_growth_segments(R0, [(50.0, 0.001)], min_r_eff_m=0.005)


def test_build_growth_segments_one_point_matches_calibrate_k():
    # The 1-point piecewise model must be mathematically identical to
    # calibrate_k's single-measurement model -- this is the whole premise of
    # generalizing it.
    true_k = 0.0021
    theta_m_turns = 4.0
    theta_m_rad = radians_from_turns(theta_m_turns)
    length_at_theta_m = length_from_turns_delta(theta_m_turns, R0, true_k)

    segments = build_growth_segments(R0, [(theta_m_rad, length_at_theta_m)])
    for theta in (0.5, 2.0, theta_m_rad, 10.0, 30.0):
        assert length_from_angle_piecewise(theta, segments) == pytest.approx(
            length_from_angle(theta, R0, true_k), rel=1e-9, abs=1e-9
        )


def test_build_growth_segments_multi_point_exact_at_each_point():
    points = [(2.0, 0.075), (5.0, 0.20), (9.0, 0.40)]
    segments = build_growth_segments(R0, points)
    for theta, length in points:
        assert length_from_angle_piecewise(theta, segments) == pytest.approx(length, rel=1e-9, abs=1e-9)


def test_piecewise_round_trip_length_angle_length():
    points = [(2.0, 0.075), (5.0, 0.20), (9.0, 0.40)]
    segments = build_growth_segments(R0, points)
    for theta in (0.3, 1.5, 2.0, 3.7, 5.0, 7.0, 9.0, 15.0):
        length = length_from_angle_piecewise(theta, segments)
        theta_back = angle_from_length_piecewise(length, segments)
        assert theta_back == pytest.approx(theta, rel=1e-9, abs=1e-9)


def test_piecewise_extrapolates_beyond_last_point_with_last_slope():
    points = [(2.0, 0.075), (5.0, 0.20)]
    segments = build_growth_segments(R0, points)
    last_segment = segments[-1]
    assert last_segment.theta_end is None
    # A point well beyond the last calibration point should still land on
    # the straight-line continuation of the last segment's slope.
    theta = 5.0 + 3.0
    expected = 0.20 + last_segment.r_start * 3.0 + (last_segment.slope / 2.0) * 3.0 * 3.0
    assert length_from_angle_piecewise(theta, segments) == pytest.approx(expected, rel=1e-9)


def test_angle_from_length_piecewise_rejects_negative_length():
    segments = build_growth_segments(R0, [(2.0, 0.075)])
    with pytest.raises(ValueError):
        angle_from_length_piecewise(-1.0, segments)


# ---- SpoolGeometry with growth_points (turns, not radians) ----

def _two_segment_growth_points_turns(r0, t1_turns, slope1, t2_turns, slope2):
    """Build a physically-consistent (turns, length_m) pair for a two-segment
    model with known per-segment slopes, so tests assert against derived
    values instead of hand-picked/arbitrary magic numbers."""
    theta1 = radians_from_turns(t1_turns)
    theta2 = radians_from_turns(t2_turns)
    l1 = r0 * theta1 + (slope1 / 2.0) * theta1 * theta1
    r_end1 = r0 + slope1 * theta1
    d2 = theta2 - theta1
    l2 = l1 + r_end1 * d2 + (slope2 / 2.0) * d2 * d2
    return [(t1_turns, l1), (t2_turns, l2)]


def test_spool_geometry_growth_points_supersede_k():
    # k is tracked/displayed but not consulted once growth_points exist.
    points = _two_segment_growth_points_turns(R0, 0.3, 0.002, 0.8, 0.004)
    geo = SpoolGeometry(r0=R0, k=0.5, growth_points=points)
    assert geo.active_model == "piecewise"
    t1_turns, l1 = points[0]
    length_at_t1 = geo.length_from_turns_delta(t1_turns)
    assert length_at_t1 == pytest.approx(l1, rel=1e-9)
    # k=0.5 would have produced something wildly different -- confirms k was
    # NOT used.
    assert length_at_t1 != pytest.approx(length_from_turns_delta(t1_turns, R0, 0.5))


def test_spool_geometry_segments_summary_and_r_eff():
    t1_turns, t2_turns = 0.3, 0.8
    points = _two_segment_growth_points_turns(R0, t1_turns, 0.002, t2_turns, 0.004)
    geo = SpoolGeometry(r0=R0, k=0.0, growth_points=points)
    summary = geo.segments_summary()
    assert len(summary) == 3  # 2 bounded segments + 1 open-ended extrapolation
    assert summary[0]["theta_start_turns"] == pytest.approx(0.0)
    assert summary[0]["theta_end_turns"] == pytest.approx(t1_turns)
    assert summary[-1]["theta_end_turns"] is None
    assert geo.r_eff_at_turns_delta(0.0) == pytest.approx(R0)


def test_spool_geometry_describe_reports_linear_and_piecewise():
    linear = SpoolGeometry(r0=R0, k=0.001).describe()
    assert "segments" in linear and linear["segments"] == []
    assert f"{R0:.6f}" in linear["model"]

    points = _two_segment_growth_points_turns(R0, 0.3, 0.002, 0.8, 0.004)
    piecewise = SpoolGeometry(r0=R0, k=0.0, growth_points=points).describe()
    assert len(piecewise["segments"]) == 3
    assert "piecewise" in piecewise["model"]


def test_describe_model_matches_spool_geometry_describe():
    geo = SpoolGeometry(r0=R0, k=0.001)
    assert describe_model(R0, 0.001, []) == geo.describe()
