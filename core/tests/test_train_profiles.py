import pytest

from core.cable.train_profiles import TrainProfile, TrainSegment


def test_constant_segment_force():
    seg = TrainSegment(0.0, 1.0, "constant", {"force_n": 50.0})
    assert seg.force_at(0.0) == 50.0
    assert seg.force_at(0.5) == 50.0
    assert seg.force_at(1.0) == 50.0


def test_linear_segment_interpolates():
    seg = TrainSegment(0.0, 1.0, "linear", {"start_force_n": 0.0, "end_force_n": 100.0})
    assert seg.force_at(0.0) == pytest.approx(0.0)
    assert seg.force_at(0.5) == pytest.approx(50.0)
    assert seg.force_at(1.0) == pytest.approx(100.0)


def test_linear_segment_can_decrease():
    seg = TrainSegment(0.0, 2.0, "linear", {"start_force_n": 100.0, "end_force_n": 0.0})
    assert seg.force_at(0.0) == pytest.approx(100.0)
    assert seg.force_at(1.0) == pytest.approx(50.0)
    assert seg.force_at(2.0) == pytest.approx(0.0)


def test_bell_segment_zero_at_edges_peak_at_peak_pos():
    seg = TrainSegment(0.0, 1.0, "bell", {"peak_pos_m": 0.5, "peak_force_n": 80.0})
    assert seg.force_at(0.0) == pytest.approx(0.0, abs=1e-9)
    assert seg.force_at(1.0) == pytest.approx(0.0, abs=1e-9)
    assert seg.force_at(0.5) == pytest.approx(80.0)
    # Monotonically rising toward the peak from the start edge.
    assert seg.force_at(0.1) < seg.force_at(0.3) < seg.force_at(0.5)


def test_bell_segment_off_centre_peak():
    # Peak much closer to the start than the end -- independent half-widths
    # either side of peak_pos_m must both still reach 0 at their own edge.
    seg = TrainSegment(0.0, 10.0, "bell", {"peak_pos_m": 1.0, "peak_force_n": 50.0})
    assert seg.force_at(0.0) == pytest.approx(0.0, abs=1e-9)
    assert seg.force_at(1.0) == pytest.approx(50.0)
    assert seg.force_at(10.0) == pytest.approx(0.0, abs=1e-9)
    assert seg.force_at(5.5) < seg.force_at(1.0)


def test_bell_segment_asymmetric_edge_floors():
    # 3 -> 10 -> 4: edges no longer have to return to zero.
    seg = TrainSegment(0.0, 1.0, "bell", {"peak_pos_m": 0.5, "peak_force_n": 10.0, "start_force_n": 3.0, "end_force_n": 4.0})
    assert seg.force_at(0.0) == pytest.approx(3.0)
    assert seg.force_at(1.0) == pytest.approx(4.0)
    assert seg.force_at(0.5) == pytest.approx(10.0)
    assert seg.force_at(0.1) < seg.force_at(0.3) < seg.force_at(0.5)
    assert seg.force_at(0.9) < seg.force_at(0.7) < seg.force_at(0.5)


def test_bell_segment_edge_floors_reject_negative():
    with pytest.raises(ValueError):
        TrainSegment(0.0, 1.0, "bell", {"peak_pos_m": 0.5, "peak_force_n": 10.0, "start_force_n": -1.0})
    with pytest.raises(ValueError):
        TrainSegment(0.0, 1.0, "bell", {"peak_pos_m": 0.5, "peak_force_n": 10.0, "end_force_n": -1.0})


def test_bell_peak_must_be_strictly_inside_segment():
    with pytest.raises(ValueError):
        TrainSegment(0.0, 1.0, "bell", {"peak_pos_m": 0.0, "peak_force_n": 50.0})
    with pytest.raises(ValueError):
        TrainSegment(0.0, 1.0, "bell", {"peak_pos_m": 1.0, "peak_force_n": 50.0})
    with pytest.raises(ValueError):
        TrainSegment(0.0, 1.0, "bell", {"peak_pos_m": 1.5, "peak_force_n": 50.0})


def test_segment_rejects_unknown_shape():
    with pytest.raises(ValueError):
        TrainSegment(0.0, 1.0, "quadratic", {})


def test_segment_rejects_inverted_or_degenerate_range():
    with pytest.raises(ValueError):
        TrainSegment(1.0, 0.0, "constant", {"force_n": 10.0})
    with pytest.raises(ValueError):
        TrainSegment(1.0, 1.0, "constant", {"force_n": 10.0})


def test_segment_rejects_negative_position():
    with pytest.raises(ValueError):
        TrainSegment(-0.1, 1.0, "constant", {"force_n": 10.0})


def test_segment_rejects_negative_force():
    with pytest.raises(ValueError):
        TrainSegment(0.0, 1.0, "constant", {"force_n": -5.0})
    with pytest.raises(ValueError):
        TrainSegment(0.0, 1.0, "linear", {"start_force_n": -1.0, "end_force_n": 10.0})
    with pytest.raises(ValueError):
        TrainSegment(0.0, 1.0, "bell", {"peak_pos_m": 0.5, "peak_force_n": -1.0})


def test_segment_rejects_missing_param():
    with pytest.raises(ValueError):
        TrainSegment(0.0, 1.0, "constant", {})


def test_segment_rejects_non_numeric_param():
    with pytest.raises(TypeError):
        TrainSegment(0.0, 1.0, "constant", {"force_n": "fifty"})


def test_profile_force_at_selects_segment():
    profile = TrainProfile(
        name="test",
        segments=[
            TrainSegment(0.0, 1.0, "constant", {"force_n": 10.0}),
            TrainSegment(1.0, 2.0, "constant", {"force_n": 20.0}),
        ],
    )
    assert profile.force_at(0.5) == 10.0
    assert profile.force_at(1.5) == 20.0
    # Shared boundary (both segments' `contains()` includes it) resolves
    # deterministically to whichever segment is checked first: segments are
    # sorted ascending by start_pos_m, so the lower segment wins.
    assert profile.force_at(1.0) == 10.0


def test_profile_force_outside_every_segment_is_zero():
    profile = TrainProfile(name="test", segments=[TrainSegment(1.0, 2.0, "constant", {"force_n": 10.0})])
    assert profile.force_at(0.0) == 0.0
    assert profile.force_at(5.0) == 0.0


def test_profile_with_no_segments_is_always_zero():
    profile = TrainProfile(name="empty", segments=[])
    assert profile.force_at(0.0) == 0.0
    assert profile.force_at(100.0) == 0.0


def test_profile_rejects_overlapping_segments():
    with pytest.raises(ValueError):
        TrainProfile(
            segments=[
                TrainSegment(0.0, 1.5, "constant", {"force_n": 10.0}),
                TrainSegment(1.0, 2.0, "constant", {"force_n": 20.0}),
            ]
        )


def test_profile_sorts_segments_by_start():
    profile = TrainProfile(
        segments=[
            TrainSegment(1.0, 2.0, "constant", {"force_n": 20.0}),
            TrainSegment(0.0, 1.0, "constant", {"force_n": 10.0}),
        ]
    )
    assert [s.start_pos_m for s in profile.segments] == [0.0, 1.0]


def test_profile_preview_covers_range():
    profile = TrainProfile(segments=[TrainSegment(0.0, 1.0, "linear", {"start_force_n": 0.0, "end_force_n": 100.0})])
    points = profile.preview((0.0, 1.0), n_points=5)
    assert len(points) == 5
    assert points[0] == pytest.approx((0.0, 0.0))
    assert points[-1] == pytest.approx((1.0, 100.0))
    # Strictly increasing under a rising linear segment.
    values = [v for _, v in points]
    assert values == sorted(values)


def test_profile_preview_and_force_at_are_the_same_evaluator():
    """Spec §4: the preview graph and the live overlay must read from the
    same evaluator -- assert preview()'s points equal independent force_at()
    calls at the same positions, not just that both "look reasonable"."""
    profile = TrainProfile(
        segments=[
            TrainSegment(0.0, 0.5, "constant", {"force_n": 30.0}),
            TrainSegment(0.5, 1.5, "bell", {"peak_pos_m": 1.0, "peak_force_n": 90.0}),
        ]
    )
    points = profile.preview((0.0, 1.5), n_points=31)
    for position_m, force_n in points:
        assert force_n == pytest.approx(profile.force_at(position_m))


def test_to_dict_from_dict_round_trip():
    profile = TrainProfile(
        name="round-trip",
        segments=[
            TrainSegment(0.0, 1.0, "constant", {"force_n": 10.0}),
            TrainSegment(1.0, 2.0, "linear", {"start_force_n": 10.0, "end_force_n": 40.0}),
            TrainSegment(2.0, 3.0, "bell", {"peak_pos_m": 2.5, "peak_force_n": 60.0}),
        ],
    )
    restored = TrainProfile.from_dict(profile.to_dict())
    assert restored.name == profile.name
    for position_m in (0.2, 0.9, 1.5, 2.5, 2.9):
        assert restored.force_at(position_m) == pytest.approx(profile.force_at(position_m))


def test_from_dict_rejects_non_dict():
    with pytest.raises(TypeError):
        TrainProfile.from_dict([1, 2, 3])
