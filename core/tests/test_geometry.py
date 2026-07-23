"""core/cable/geometry.py tests (exercise_tab_build_spec_layerA.md §8)."""

import math

import pytest

from core.cable.geometry import (
    SpoolGeometry,
    angle_from_length,
    calibrate_k,
    length_from_angle,
    length_from_turns_delta,
    radians_from_turns,
    turns_delta_from_length,
    turns_from_radians,
)

R0 = 0.05  # SPOOL_RADIUS_M


# ---- turns <-> radians, the one conversion site ----

def test_radians_from_turns_and_back():
    assert radians_from_turns(1.0) == pytest.approx(2 * math.pi)
    assert turns_from_radians(2 * math.pi) == pytest.approx(1.0)
    assert turns_from_radians(radians_from_turns(3.7)) == pytest.approx(3.7)


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
