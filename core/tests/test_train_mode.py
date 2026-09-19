"""core/cable/train_mode.py tests. Same RecordingHardware-fake style as
core/tests/test_exercise_mode.py -- faster and more precise than
round-tripping through ControlSession's thread.
"""

from typing import List

import pytest

from config import board_constants
from core.cable import geometry
from core.cable.phase_ramp_detector import CONCENTRIC, ECCENTRIC
from core.cable.state import CableState
from core.cable.train_mode import TrainMode
from core.cable.train_profiles import TrainProfile, TrainSegment
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles.detectors import CABLE_SIGN
from core.profiles.units import force_to_torque


class RecordingHardware(HardwareInterface):
    def __init__(self):
        self.connected = False
        self.calls: List[tuple] = []
        self.mode = None
        self.velocity_target = None
        self.torque_target = None
        self.current_limit = None
        self.stop_calls = 0
        self.sample = TelemetrySample(t=0.0, position=0.0, velocity=0.0, current_iq=0.0, torque_est=0.0)

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    @property
    def is_connected(self):
        return self.connected

    def get_state(self):
        self.calls.append(("get_state",))
        return self.sample

    def set_mode(self, mode):
        self.calls.append(("set_mode", mode))
        self.mode = mode

    def set_velocity_target(self, turns_per_s):
        self.calls.append(("set_velocity_target", turns_per_s))
        self.velocity_target = turns_per_s

    def set_torque_target(self, nm):
        self.calls.append(("set_torque_target", nm))
        self.torque_target = nm

    def set_position_target(self, turns, move_velocity, accel_decel, torque_limit=None):
        self.calls.append(("set_position_target", turns, move_velocity, accel_decel, torque_limit))

    def set_current_limit(self, amps):
        self.calls.append(("set_current_limit", amps))
        self.current_limit = amps

    def stop(self):
        self.calls.append(("stop",))
        self.stop_calls += 1
        self.velocity_target = 0.0
        self.torque_target = 0.0

    def get_errors(self):
        return []


def _sample(t, position, velocity=0.0, current_iq=0.0, torque_est=0.0):
    return TelemetrySample(t=t, position=position, velocity=velocity, current_iq=current_iq, torque_est=torque_est)


def _mode(tmp_path):
    return TrainMode(CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json"))


def _homed_mode(tmp_path, home=0.0, max_turns=None):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json")
    cable_state.latch_home(home)
    if max_turns is not None:
        cable_state.set_max(marked_turns=max_turns, enforced_turns=max_turns)
    return TrainMode(cable_state)


def _run(mode, hw, profile=None, phase_forces=None):
    target = {"action": "run"}
    if profile is not None:
        target["profile"] = profile
    if phase_forces is not None:
        target["phase_forces"] = phase_forces
    mode.apply_target(hw, mode.validate_target(target))


# ---- validate_target ----


def test_validate_target_rejects_non_dict():
    m = TrainMode(CableState.__new__(CableState))  # cable_state unused here
    with pytest.raises(TypeError):
        m.validate_target(5.0)


def test_validate_target_rejects_unknown_action(tmp_path):
    m = _mode(tmp_path)
    with pytest.raises(ValueError):
        m.validate_target({"action": "engage"})


def test_validate_target_rejects_removed_move_action(tmp_path):
    """Manual jogging was removed from TrainMode 25 July 2026 in favour of
    the Control tab's own Position mode -- "move"/"stop_move" must no
    longer validate, not silently become dead-but-reachable actions."""
    m = _mode(tmp_path)
    with pytest.raises(ValueError):
        m.validate_target({"action": "move", "target_length_m": 0.2})
    with pytest.raises(ValueError):
        m.validate_target({"action": "stop_move"})


def test_validate_target_run_defaults_to_empty_profile(tmp_path):
    m = _mode(tmp_path)
    validated = m.validate_target({"action": "run"})
    assert isinstance(validated["profile"], TrainProfile)
    assert validated["profile"].segments == []


def test_validate_target_run_coerces_dict_profile(tmp_path):
    m = _mode(tmp_path)
    validated = m.validate_target(
        {"action": "run", "profile": {"name": "p", "segments": [{"start_pos_m": 0.0, "end_pos_m": 1.0, "shape": "constant", "params": {"force_n": 20.0}}]}}
    )
    assert isinstance(validated["profile"], TrainProfile)
    assert validated["profile"].name == "p"


# ---- run / set_profile ----


def test_run_requires_homed(tmp_path):
    m = _mode(tmp_path)
    hw = RecordingHardware()
    with pytest.raises(RuntimeError):
        _run(m, hw)


def test_run_sets_torque_mode_and_zero_initial_torque(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    _run(m, hw)
    assert hw.mode == ControlMode.TORQUE
    assert hw.torque_target == 0.0


def test_set_profile_swaps_profile_without_hardware_call(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    _run(m, hw)
    calls_before = len(hw.calls)

    profile = TrainProfile(segments=[TrainSegment(0.0, 1.0, "constant", {"force_n": 50.0})])
    m.apply_target(hw, m.validate_target({"action": "set_profile", "profile": profile}))

    assert m.profile is profile
    assert len(hw.calls) == calls_before  # no immediate hardware write


# ---- tick: profile evaluation ----


def test_tick_commands_zero_torque_with_empty_profile(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    _run(m, hw)
    hw.sample = _sample(t=1 / 50, position=0.1)
    extra = m.tick(hw, hw.sample)
    assert hw.torque_target == 0.0
    assert extra["target_force_n"] == 0.0


def test_tick_commands_torque_matching_profile_force(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 1.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile)

    hw.sample = _sample(t=1 / 50, position=0.2)  # 0.2 turns of cable paid out
    extra = m.tick(hw, hw.sample)

    cable_length_m = extra["cable_length_m"]
    expected_force = profile.force_at(cable_length_m)
    expected_torque = force_to_torque(expected_force, r0=m.cable_state.r0)
    assert extra["target_force_n"] == pytest.approx(expected_force)
    assert hw.torque_target == pytest.approx(-CABLE_SIGN * expected_torque)


def test_tick_commands_torque_at_effective_radius_not_bare_r0(tmp_path):
    """Item 3a: torque must use the position's effective spool radius
    (r_eff, growing/shrinking per the calibrated k), not the static r0 --
    otherwise force delivered to the user drifts as cable pays in/out even
    though cable_length_m already correctly tracks r_eff. A nonzero k makes
    r_eff diverge from r0 away from home, so this would have failed against
    the pre-fix `r0=self.cable_state.r0` call."""
    m = _homed_mode(tmp_path)
    m.cable_state.set_k(0.002)  # within SPOOL_CORRECTION_K_BOUNDS
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 5.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile)

    turns_delta = 3.0  # comfortably away from home so r_eff != r0
    hw.sample = _sample(t=1 / 50, position=turns_delta)
    extra = m.tick(hw, hw.sample)

    r_eff = m.cable_state.spool_geometry.r_eff_at_turns_delta(turns_delta)
    assert r_eff != pytest.approx(m.cable_state.r0)  # sanity: k actually moved r_eff
    expected_torque = force_to_torque(extra["target_force_n"], r0=r_eff)
    wrong_torque_at_bare_r0 = force_to_torque(extra["target_force_n"], r0=m.cable_state.r0)
    assert hw.torque_target == pytest.approx(-CABLE_SIGN * expected_torque)
    assert hw.torque_target != pytest.approx(-CABLE_SIGN * wrong_torque_at_bare_r0)


def test_tick_commands_torque_through_torque_calibration_correction(tmp_path):
    """Items 6/7: once a torque calibration is recorded, the raw Nm value
    actually sent to hardware must be the INVERSE-corrected one -- so the
    real, physical torque delivered matches the calibrated real-world
    relationship, not the raw motor-constant estimate."""
    m = _homed_mode(tmp_path)
    r_eff = m.cable_state.r_eff_at_position(0.0)
    m.cable_state.add_torque_calibration_point(
        known_weight_kg=5.0, raw_torque_nm=0.9, r_eff_m=r_eff, direction="up"
    )
    assert m.cable_state.torque_calibration.scale["up"] != pytest.approx(1.0)  # sanity: a real correction exists

    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 1.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile)

    # velocity<0 (CABLE_SIGN=1) -> cable_velocity_turns_s<0 -> "up" line, the
    # one just calibrated above.
    hw.sample = _sample(t=1 / 50, position=0.2, velocity=-0.5)
    extra = m.tick(hw, hw.sample)

    real_torque_nm = force_to_torque(extra["target_force_n"], r0=m.cable_state.r0)
    cable_velocity_turns_s = CABLE_SIGN * hw.sample.velocity
    raw_torque_nm = m.cable_state.raw_torque_nm_for_corrected(real_torque_nm, cable_velocity_turns_s)
    assert raw_torque_nm != pytest.approx(real_torque_nm)  # sanity: correction actually changes something
    assert hw.torque_target == pytest.approx(-CABLE_SIGN * raw_torque_nm)
    # extra still reports the REAL torque, not the raw command -- that's
    # what's meaningful to a human reading it back.
    assert extra["commanded_torque_nm"] == pytest.approx(real_torque_nm)


def test_tick_torque_conversion_is_noop_at_default_k(tmp_path):
    """Regression guard: with the default, un-calibrated k=0 (no growth
    points), r_eff_at_turns_delta() must reduce to plain r0 everywhere, so
    the item-3a fix changes nothing for a rig that hasn't been
    spool-calibrated."""
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 5.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile)

    hw.sample = _sample(t=1 / 50, position=3.0)
    extra = m.tick(hw, hw.sample)

    expected_torque = force_to_torque(extra["target_force_n"], r0=m.cable_state.r0)
    assert hw.torque_target == pytest.approx(-CABLE_SIGN * expected_torque)


def test_tick_clamps_effective_radius_to_min_floor_beyond_calibrated_envelope(tmp_path):
    """A piecewise growth model's final segment extrapolates its fitted
    slope indefinitely past the last calibration point, with no floor check
    of its own (core/cable/geometry.py::build_growth_segments only floors
    segments up to the last measured point). Travel far enough past that
    point -- reachable with a guard toggle disabled, or simply no max
    calibrated yet -- with a negative slope (the thicker-strap scenario:
    effective radius SHRINKS as more cable pays out) and r_eff would go
    through zero and negative. tick() must clamp it at
    SPOOL_MIN_EFFECTIVE_RADIUS_M rather than feed a non-physical radius into
    the torque conversion."""
    m = _homed_mode(tmp_path, home=0.0, max_turns=None)
    m.cable_state.set_r0(0.06)

    # One calibration point giving a shrinking effective radius (0.06 -> 0.05
    # over 2 turns) -- a negative slope, same direction as the user's real
    # thicker-strap measurements (~0.06m at home, ~0.04m at max extension).
    theta_end_turns = 2.0
    theta_end_rad = geometry.radians_from_turns(theta_end_turns)
    r_end = 0.05
    slope = (r_end - m.cable_state.r0) / theta_end_rad
    length_end = geometry.length_from_angle(theta_end_rad, m.cable_state.r0, slope)
    m.cable_state.set_growth_points([(theta_end_turns, length_end)])

    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 1000.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile)

    far_turns = 50.0  # well past the one calibration point at 2 turns
    raw_r_eff = m.cable_state.spool_geometry.r_eff_at_turns_delta(far_turns)
    assert raw_r_eff < board_constants.SPOOL_MIN_EFFECTIVE_RADIUS_M  # sanity: the unclamped model really does go non-physical here

    hw.sample = _sample(t=1 / 50, position=far_turns)
    extra = m.tick(hw, hw.sample)

    expected_torque = force_to_torque(extra["target_force_n"], r0=board_constants.SPOOL_MIN_EFFECTIVE_RADIUS_M)
    assert hw.torque_target == pytest.approx(-CABLE_SIGN * expected_torque)


def test_tick_clamps_force_to_force_max_n(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    huge_force = board_constants.FORCE_MAX_N * 10
    profile = TrainProfile(segments=[TrainSegment(0.0, 1.0, "constant", {"force_n": huge_force})])
    _run(m, hw, profile)

    hw.sample = _sample(t=1 / 50, position=0.1)
    extra = m.tick(hw, hw.sample)

    assert extra["target_force_n"] == pytest.approx(board_constants.FORCE_MAX_N)


def test_tick_resistance_symmetric_both_directions(tmp_path):
    """Spec §4: 'wherever the cable is, that's the torque, same in both
    directions' -- no eccentric/concentric asymmetry. Approaching a position
    from either side of it must command the identical torque."""
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 1.0, "linear", {"start_force_n": 10.0, "end_force_n": 90.0})])
    _run(m, hw, profile)

    hw.sample = _sample(t=1 / 50, position=0.5, velocity=+1.0)  # paying out
    m.tick(hw, hw.sample)
    torque_paying_out = hw.torque_target

    hw.sample = _sample(t=2 / 50, position=0.5, velocity=-1.0)  # reeling in
    m.tick(hw, hw.sample)
    torque_reeling_in = hw.torque_target

    assert torque_paying_out == pytest.approx(torque_reeling_in)


# ---- constant + inertia (resistance-modes sub-phase 3) ----


def test_inertia_kg_zero_reproduces_current_constant_behavior(tmp_path):
    """Acceptance criteria: inertia_kg=0 (the default) must be
    byte-identical to plain constant-mode behavior, even across ticks with
    changing velocity (so a nonzero acceleration estimate exists but has
    nothing to multiply)."""
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 5.0, "constant", {"force_n": 40.0, "inertia_kg": 0.0})])
    _run(m, hw, profile)

    hw.sample = _sample(t=1 / 50, position=0.2, velocity=0.5)
    extra = m.tick(hw, hw.sample)
    assert extra["target_force_n"] == pytest.approx(40.0)

    hw.sample = _sample(t=2 / 50, position=0.3, velocity=2.0)  # velocity jumped -> real acceleration
    extra = m.tick(hw, hw.sample)
    assert extra["target_force_n"] == pytest.approx(40.0)

    expected_torque = force_to_torque(40.0, r0=m.cable_state.r0)
    assert hw.torque_target == pytest.approx(-CABLE_SIGN * expected_torque)


def test_inertia_kg_adds_force_proportional_to_acceleration(tmp_path):
    """A step change in velocity between two ticks should show up as a
    nonzero inertia contribution on top of the base constant force, once the
    filter has a previous sample to difference against (first tick after
    "run" only seeds the filter -- see _filtered_acceleration_m_s2)."""
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 5.0, "constant", {"force_n": 40.0, "inertia_kg": 2.0})])
    _run(m, hw, profile)

    # First tick only seeds the velocity filter -- no prior sample to
    # difference against yet, so no inertia contribution.
    hw.sample = _sample(t=0.0, position=0.1, velocity=0.0)
    extra = m.tick(hw, hw.sample)
    assert extra["target_force_n"] == pytest.approx(40.0)

    # Second tick: velocity jumped, so the filtered value moves and a_filtered
    # is nonzero -- the accelerating direction (paying out faster) should ADD
    # to the base force, same sign as a real added mass resisting the speed-up.
    hw.sample = _sample(t=1 / 50, position=0.15, velocity=5.0)
    extra = m.tick(hw, hw.sample)
    assert extra["target_force_n"] > 40.0


def test_inertia_force_still_clamped_to_force_max_n(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    huge_force = board_constants.FORCE_MAX_N * 10
    profile = TrainProfile(segments=[TrainSegment(0.0, 5.0, "constant", {"force_n": huge_force, "inertia_kg": m.cable_state.inertia_kg_max})])
    _run(m, hw, profile)

    hw.sample = _sample(t=0.0, position=0.1, velocity=0.0)
    m.tick(hw, hw.sample)
    hw.sample = _sample(t=1 / 50, position=0.5, velocity=10.0)
    extra = m.tick(hw, hw.sample)

    assert extra["target_force_n"] == pytest.approx(board_constants.FORCE_MAX_N)


def test_inertia_only_applies_within_its_own_segment(tmp_path):
    """inertia_kg lives on one segment's params -- a neighbouring segment
    without it must not inherit an inertia contribution just because the
    filter has a nonzero acceleration estimate warmed up from the previous
    segment."""
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(
        segments=[
            TrainSegment(0.0, 1.0, "constant", {"force_n": 40.0, "inertia_kg": 5.0}),
            TrainSegment(1.0, 2.0, "constant", {"force_n": 40.0}),  # inertia_kg defaults to 0
        ]
    )
    _run(m, hw, profile)

    hw.sample = _sample(t=0.0, position=0.5, velocity=0.0)
    m.tick(hw, hw.sample)
    # position in turns; cable_length_m = turns * 2*pi*r0 (default r0=0.035m)
    # -- 6.0 turns lands at ~1.32m, inside the second (no-inertia) segment.
    hw.sample = _sample(t=1 / 50, position=6.0, velocity=10.0)
    extra = m.tick(hw, hw.sample)

    assert extra["cable_length_m"] > 1.0  # sanity: actually in the second segment
    assert extra["target_force_n"] == pytest.approx(40.0)


def test_inertia_filter_resets_on_run(tmp_path):
    """A fresh "run" must reset the inertia filter state -- a stale filtered
    velocity/timestamp from a previous session shouldn't be differenced
    against this session's first real sample."""
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 5.0, "constant", {"force_n": 40.0, "inertia_kg": 2.0})])
    _run(m, hw, profile)

    hw.sample = _sample(t=0.0, position=0.1, velocity=0.0)
    m.tick(hw, hw.sample)
    hw.sample = _sample(t=1 / 50, position=0.5, velocity=10.0)
    m.tick(hw, hw.sample)  # filter is now warmed up mid-session

    _run(m, hw, profile)  # re-run resets filter state
    assert m._filtered_velocity_m_s is None
    assert m._last_inertia_tick_t is None

    hw.sample = _sample(t=100.0, position=0.1, velocity=0.0)
    extra = m.tick(hw, hw.sample)  # first tick after reset only seeds the filter
    assert extra["target_force_n"] == pytest.approx(40.0)


def test_tick_outside_every_segment_is_zero_torque(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(2.0, 3.0, "constant", {"force_n": 50.0})])
    _run(m, hw, profile)

    hw.sample = _sample(t=1 / 50, position=0.1)  # well short of the segment
    m.tick(hw, hw.sample)
    assert hw.torque_target == 0.0


# ---- max-extension guard ----


def test_guard_enforced_raises_past_max(tmp_path):
    m = _homed_mode(tmp_path, home=0.0, max_turns=1.0)
    m.cable_state.train_max_extension_enforced = True
    hw = RecordingHardware()
    _run(m, hw)

    past_max = 1.0 + m.cable_state.position_guard_hard_turns + 0.01
    hw.sample = _sample(t=1 / 50, position=past_max)
    with pytest.raises(RuntimeError):
        m.tick(hw, hw.sample)


def test_guard_disabled_does_not_raise_past_max(tmp_path):
    m = _homed_mode(tmp_path, home=0.0, max_turns=1.0)
    m.cable_state.train_max_extension_enforced = False
    hw = RecordingHardware()
    _run(m, hw)

    past_max = 1.0 + m.cable_state.position_guard_hard_turns + 0.01
    hw.sample = _sample(t=1 / 50, position=past_max)
    m.tick(hw, hw.sample)  # must not raise


def test_guard_does_not_apply_without_max_set(tmp_path):
    m = _homed_mode(tmp_path, home=0.0, max_turns=None)
    m.cable_state.train_max_extension_enforced = True
    hw = RecordingHardware()
    _run(m, hw)

    hw.sample = _sample(t=1 / 50, position=1000.0)
    m.tick(hw, hw.sample)  # no max calibrated -- nothing to violate


# ---- home-side guard (split from max-extension 25 July 2026) ----


def test_home_guard_enforced_raises_past_home(tmp_path):
    m = _homed_mode(tmp_path, home=0.0, max_turns=1.0)
    m.cable_state.train_home_guard_enforced = True
    hw = RecordingHardware()
    _run(m, hw)

    past_home = 0.0 - m.cable_state.position_guard_hard_turns - 0.01
    hw.sample = _sample(t=1 / 50, position=past_home)
    with pytest.raises(RuntimeError):
        m.tick(hw, hw.sample)


def test_home_guard_disabled_does_not_raise_past_home(tmp_path):
    m = _homed_mode(tmp_path, home=0.0, max_turns=1.0)
    m.cable_state.train_home_guard_enforced = False
    hw = RecordingHardware()
    _run(m, hw)

    past_home = 0.0 - m.cable_state.position_guard_hard_turns - 0.01
    hw.sample = _sample(t=1 / 50, position=past_home)
    m.tick(hw, hw.sample)  # must not raise


def test_home_guard_disabled_still_raises_past_max(tmp_path):
    """The two toggles are independent: disabling the home side must not
    silently disable the max side too."""
    m = _homed_mode(tmp_path, home=0.0, max_turns=1.0)
    m.cable_state.train_home_guard_enforced = False
    m.cable_state.train_max_extension_enforced = True
    hw = RecordingHardware()
    _run(m, hw)

    past_max = 1.0 + m.cable_state.position_guard_hard_turns + 0.01
    hw.sample = _sample(t=1 / 50, position=past_max)
    with pytest.raises(RuntimeError):
        m.tick(hw, hw.sample)


def test_max_guard_disabled_still_raises_past_home(tmp_path):
    """Same independence check the other way around -- this is the exact bug
    report that motivated the split: max-extension enforcement turned off
    must not also silently disable the home side."""
    m = _homed_mode(tmp_path, home=0.0, max_turns=1.0)
    m.cable_state.train_home_guard_enforced = True
    m.cable_state.train_max_extension_enforced = False
    hw = RecordingHardware()
    _run(m, hw)

    past_home = 0.0 - m.cable_state.position_guard_hard_turns - 0.01
    hw.sample = _sample(t=1 / 50, position=past_home)
    with pytest.raises(RuntimeError):
        m.tick(hw, hw.sample)


def test_both_guards_disabled_does_not_raise_either_side(tmp_path):
    m = _homed_mode(tmp_path, home=0.0, max_turns=1.0)
    m.cable_state.train_home_guard_enforced = False
    m.cable_state.train_max_extension_enforced = False
    hw = RecordingHardware()
    _run(m, hw)

    past_home = 0.0 - m.cable_state.position_guard_hard_turns - 0.01
    hw.sample = _sample(t=1 / 50, position=past_home)
    m.tick(hw, hw.sample)  # must not raise

    past_max = 1.0 + m.cable_state.position_guard_hard_turns + 0.01
    hw.sample = _sample(t=2 / 50, position=past_max)
    m.tick(hw, hw.sample)  # must not raise


# ---- concentric/eccentric (resistance-modes sub-phase 4) ----


# 1.0 turns/s is comfortably above MIN_SUSTAINED_VELOCITY_M_S at the default
# r0 (turns/s * 2*pi*r0 ~= 0.22 m/s), same margin the phase_ramp_detector's
# own tests use -- not meant to be a realistic pull speed, just unambiguous.
_STRONG_TURNS_S = 1.0


def _drive_until_flip(mode, hw, start_t, start_turns, turns_per_s, max_ticks=60, dt=1 / 50):
    """Ticks at a constant velocity (turns/s, signed) from start_turns/
    start_t until the commanded phase changes from whatever it was on the
    first tick, or max_ticks is exhausted (comfortably more than the ~8-10
    ticks the default constants need at _STRONG_TURNS_S). Returns the final
    `extra` dict."""
    t = start_t
    turns = start_turns
    extra = None
    first_phase = None
    for i in range(max_ticks):
        t += dt
        turns += turns_per_s * dt
        hw.sample = _sample(t=t, position=turns, velocity=turns_per_s)
        extra = mode.tick(hw, hw.sample)
        if first_phase is None:
            first_phase = extra["phase"]
        elif extra["phase"] != first_phase:
            break
    return extra


def test_validate_target_phase_forces_defaults_to_none(tmp_path):
    m = _mode(tmp_path)
    validated = m.validate_target({"action": "run"})
    assert validated["phase_forces"] is None


def test_validate_target_accepts_valid_phase_forces(tmp_path):
    m = _mode(tmp_path)
    validated = m.validate_target(
        {"action": "run", "phase_forces": {"concentric_force_n": 40.0, "eccentric_force_n": 20.0}}
    )
    assert validated["phase_forces"] == {"concentric_force_n": 40.0, "eccentric_force_n": 20.0}


def test_validate_target_rejects_negative_phase_force(tmp_path):
    m = _mode(tmp_path)
    with pytest.raises(ValueError):
        m.validate_target({"action": "run", "phase_forces": {"concentric_force_n": -1.0, "eccentric_force_n": 20.0}})


def test_validate_target_rejects_missing_phase_force_key(tmp_path):
    m = _mode(tmp_path)
    with pytest.raises(ValueError):
        m.validate_target({"action": "run", "phase_forces": {"concentric_force_n": 40.0}})


def test_validate_target_rejects_non_numeric_phase_force(tmp_path):
    m = _mode(tmp_path)
    with pytest.raises(TypeError):
        m.validate_target({"action": "run", "phase_forces": {"concentric_force_n": "forty", "eccentric_force_n": 20.0}})


def test_validate_target_rejects_phase_force_delta_over_cap(tmp_path):
    m = _mode(tmp_path)
    cap = m.cable_state.phase_force_delta_max_n
    with pytest.raises(ValueError):
        m.validate_target(
            {"action": "run", "phase_forces": {"concentric_force_n": cap + 10.0, "eccentric_force_n": 0.0}}
        )


def test_validate_target_accepts_phase_force_delta_at_cap(tmp_path):
    m = _mode(tmp_path)
    cap = m.cable_state.phase_force_delta_max_n
    validated = m.validate_target({"action": "run", "phase_forces": {"concentric_force_n": cap, "eccentric_force_n": 0.0}})
    assert validated["phase_forces"]["concentric_force_n"] == pytest.approx(cap)


def test_validate_target_uses_live_phase_force_delta_cap(tmp_path):
    """The cap is read off cable_state at validate_target() time, not a
    fixed constant -- lowering it (GYM's Settings sub-tab) must reject a
    delta that was fine under the previous cap."""
    m = _mode(tmp_path)
    m.cable_state.set_phase_settings(phase_force_delta_max_n=5.0)
    with pytest.raises(ValueError):
        m.validate_target({"action": "run", "phase_forces": {"concentric_force_n": 10.0, "eccentric_force_n": 0.0}})


def test_run_requires_homed_with_phase_forces(tmp_path):
    m = _mode(tmp_path)
    hw = RecordingHardware()
    with pytest.raises(RuntimeError):
        _run(m, hw, phase_forces={"concentric_force_n": 40.0, "eccentric_force_n": 20.0})


def test_tick_phase_forces_starts_concentric_and_bypasses_profile(tmp_path):
    """A profile is irrelevant once phase_forces is active -- even a profile
    that would otherwise command a large force at this position must be
    ignored in favour of the phase-blended force."""
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 5.0, "constant", {"force_n": 999.0})])
    _run(m, hw, profile=profile, phase_forces={"concentric_force_n": 40.0, "eccentric_force_n": 20.0})

    hw.sample = _sample(t=1 / 50, position=0.1, velocity=0.0)
    extra = m.tick(hw, hw.sample)
    assert extra["phase"] == CONCENTRIC
    assert extra["target_force_n"] == pytest.approx(40.0)  # concentric_force_n, not the profile's 999N


def test_tick_phase_forces_flips_and_blends_to_eccentric(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    _run(m, hw, phase_forces={"concentric_force_n": 40.0, "eccentric_force_n": 10.0})

    extra = _drive_until_flip(m, hw, start_t=0.0, start_turns=0.0, turns_per_s=-_STRONG_TURNS_S)
    assert extra["phase"] == ECCENTRIC
    # Just past commit, the blend is still moving from 40N toward 10N -- not
    # yet fully settled, and never overshoots either bound.
    assert 10.0 <= extra["target_force_n"] <= 40.0


def test_tick_phase_forces_settles_fully_after_ramp_duration(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    _run(m, hw, phase_forces={"concentric_force_n": 40.0, "eccentric_force_n": 10.0})

    t = 0.0
    turns = 0.0
    dt = 1 / 50
    extra = None
    for _ in range(200):  # comfortably past both debounce AND the ramp itself
        t += dt
        turns -= _STRONG_TURNS_S * dt
        hw.sample = _sample(t=t, position=turns, velocity=-_STRONG_TURNS_S)
        extra = m.tick(hw, hw.sample)
    assert extra["phase"] == ECCENTRIC
    assert extra["target_force_n"] == pytest.approx(10.0)


def test_tick_profile_mode_does_not_set_extra_phase(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 1.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile=profile)  # no phase_forces -- ordinary profile mode

    hw.sample = _sample(t=1 / 50, position=0.1)
    extra = m.tick(hw, hw.sample)
    assert "phase" not in extra


def test_tick_phase_forces_still_clamped_to_force_max_n(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    huge = board_constants.FORCE_MAX_N * 10
    _run(m, hw, phase_forces={"concentric_force_n": huge, "eccentric_force_n": huge - 1})

    hw.sample = _sample(t=1 / 50, position=0.1, velocity=0.0)
    extra = m.tick(hw, hw.sample)
    assert extra["target_force_n"] == pytest.approx(board_constants.FORCE_MAX_N)


def test_tick_phase_forces_still_raises_past_guarded_max(tmp_path):
    """§6: reuse the existing guard-toggle infrastructure unchanged -- the
    home/max-extension safety stop must still fire in phase-forces mode."""
    m = _homed_mode(tmp_path, home=0.0, max_turns=1.0)
    m.cable_state.train_max_extension_enforced = True
    hw = RecordingHardware()
    _run(m, hw, phase_forces={"concentric_force_n": 40.0, "eccentric_force_n": 20.0})

    past_max = 1.0 + m.cable_state.position_guard_hard_turns + 0.01
    hw.sample = _sample(t=1 / 50, position=past_max)
    with pytest.raises(RuntimeError):
        m.tick(hw, hw.sample)


def test_phase_ramp_detector_resets_on_fresh_run(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    _run(m, hw, phase_forces={"concentric_force_n": 40.0, "eccentric_force_n": 10.0})
    extra = _drive_until_flip(m, hw, start_t=0.0, start_turns=0.0, turns_per_s=-_STRONG_TURNS_S)
    assert extra["phase"] == ECCENTRIC  # sanity: really flipped and left CONCENTRIC

    # A fresh "run" must reset back to the CONCENTRIC starting assumption --
    # not carry over ECCENTRIC from the previous session.
    _run(m, hw, phase_forces={"concentric_force_n": 40.0, "eccentric_force_n": 10.0})
    hw.sample = _sample(t=100.0, position=0.0, velocity=0.0)
    extra = m.tick(hw, hw.sample)
    assert extra["phase"] == CONCENTRIC
    assert extra["target_force_n"] == pytest.approx(40.0)


def test_phase_ramp_detector_state_preserved_across_set_profile_within_phase_mode(tmp_path):
    """Nudging the configured forces (e.g. Apply-ing a new eccentric_force_n
    mid-session) must not reset which direction is currently committed --
    only entering/leaving phase mode itself should reset the detector."""
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    _run(m, hw, phase_forces={"concentric_force_n": 40.0, "eccentric_force_n": 10.0})
    extra = _drive_until_flip(m, hw, start_t=0.0, start_turns=0.0, turns_per_s=-_STRONG_TURNS_S)
    assert extra["phase"] == ECCENTRIC

    # Live-retarget with different force values, same (phase) mode.
    target = m.validate_target({"action": "set_profile", "phase_forces": {"concentric_force_n": 50.0, "eccentric_force_n": 5.0}})
    m.apply_target(hw, target)

    hw.sample = _sample(t=1000.0, position=hw.sample.position, velocity=0.0)
    extra = m.tick(hw, hw.sample)
    # Still eccentric (not reset to the CONCENTRIC starting assumption), now
    # reflecting the newly-applied eccentric_force_n.
    assert extra["phase"] == ECCENTRIC
    assert extra["target_force_n"] == pytest.approx(5.0)


def test_phase_ramp_detector_resets_when_leaving_phase_mode(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    _run(m, hw, phase_forces={"concentric_force_n": 40.0, "eccentric_force_n": 10.0})
    extra = _drive_until_flip(m, hw, start_t=0.0, start_turns=0.0, turns_per_s=-_STRONG_TURNS_S)
    assert extra["phase"] == ECCENTRIC

    # Switch to ordinary profile mode, then back into phase mode -- the
    # detector must have been reset by the round trip, not still remember
    # ECCENTRIC from before.
    profile = TrainProfile(segments=[TrainSegment(0.0, 1.0, "constant", {"force_n": 40.0})])
    m.apply_target(hw, m.validate_target({"action": "set_profile", "profile": profile}))
    m.apply_target(
        hw,
        m.validate_target(
            {"action": "set_profile", "phase_forces": {"concentric_force_n": 40.0, "eccentric_force_n": 10.0}}
        ),
    )

    hw.sample = _sample(t=2000.0, position=hw.sample.position, velocity=0.0)
    extra = m.tick(hw, hw.sample)
    assert extra["phase"] == CONCENTRIC


# ---- rep counting + total work (sub-phase 5, GYM dashboard) ----
#
# Both are read-only telemetry: rep_count off a second, independent
# PhaseDetector+RepCounter (core/profiles/detectors.py, the exact pair
# ExerciseMode already uses -- see train_mode.py's module docstring for why
# it's not the same instance as _phase_ramp_detector), total_work_j off a
# plain force*|velocity|*dt accumulator. Neither feeds `force_n`.


def _rep_bump_sequence(n_reps, rep_period_s=2.0, amplitude=2.0, plateau_s=1.5, dt=1 / 50):
    """Raised-cosine position/velocity samples for `n_reps` clean reps, same
    shape core/tests/test_detectors.py's own _sinusoid_rep_sequence uses to
    validate PhaseDetector/RepCounter directly -- kept as a small local copy
    here (not a cross-test-module import) so this file's tick()-level tests
    stay self-contained, matching _drive_until_flip's own homegrown-driver
    style just above. Returns (t, position_turns, velocity_turns_s) triples."""
    import math

    samples = []
    t = 0.0
    n_plateau = int(plateau_s / dt)
    for _ in range(n_reps):
        for _ in range(n_plateau):
            samples.append((t, 0.0, 0.0))
            t += dt
        n_rep = int(rep_period_s / dt)
        omega = 2 * math.pi / rep_period_s
        for i in range(n_rep + 1):
            tp = i * dt
            position = amplitude / 2 * (1 - math.cos(omega * tp))
            velocity = amplitude / 2 * omega * math.sin(omega * tp)
            samples.append((t, position, velocity))
            t += dt
    for _ in range(n_plateau):
        samples.append((t, 0.0, 0.0))
        t += dt
    return samples


def test_rep_count_increments_across_synthetic_reps(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 1000.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile=profile)

    extra = None
    for t, position, velocity in _rep_bump_sequence(n_reps=3):
        hw.sample = _sample(t=t, position=position, velocity=velocity)
        extra = m.tick(hw, hw.sample)

    assert extra["rep_count"] == 3


def test_rep_count_resets_on_fresh_run(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 1000.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile=profile)

    extra = None
    for t, position, velocity in _rep_bump_sequence(n_reps=2):
        hw.sample = _sample(t=t, position=position, velocity=velocity)
        extra = m.tick(hw, hw.sample)
    assert extra["rep_count"] == 2

    # A fresh "run" must restart the count, not carry the previous set's
    # reps into a new one.
    _run(m, hw, profile=profile)
    hw.sample = _sample(t=1000.0, position=0.0, velocity=0.0)
    extra = m.tick(hw, hw.sample)
    assert extra["rep_count"] == 0


def test_rep_count_survives_a_live_retarget(tmp_path):
    """set_profile (the Apply button, mid-set) must NOT reset rep_count --
    only a fresh "run" (a new Start) should, mirroring _phase_ramp_detector's
    own value-change-doesn't-reset behaviour."""
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 1000.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile=profile)

    for t, position, velocity in _rep_bump_sequence(n_reps=1):
        hw.sample = _sample(t=t, position=position, velocity=velocity)
        extra = m.tick(hw, hw.sample)
    assert extra["rep_count"] == 1

    new_profile = TrainProfile(segments=[TrainSegment(0.0, 1000.0, "constant", {"force_n": 60.0})])
    m.apply_target(hw, m.validate_target({"action": "set_profile", "profile": new_profile}))

    hw.sample = _sample(t=1000.0, position=0.0, velocity=0.0)
    extra = m.tick(hw, hw.sample)
    assert extra["rep_count"] == 1


def test_total_work_j_accumulates_with_sustained_force_and_velocity(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 1000.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile=profile)

    hw.sample = _sample(t=0.0, position=0.0, velocity=0.0)
    extra = m.tick(hw, hw.sample)
    assert extra["total_work_j"] == pytest.approx(0.0)  # no elapsed dt yet

    running_totals = []
    turns = 0.0
    for i in range(1, 11):
        t = i * (1 / 50)
        turns += _STRONG_TURNS_S * (1 / 50)
        hw.sample = _sample(t=t, position=turns, velocity=_STRONG_TURNS_S)
        extra = m.tick(hw, hw.sample)
        running_totals.append(extra["total_work_j"])

    # Sustained nonzero force * nonzero velocity -- monotonically increasing.
    assert all(b > a for a, b in zip(running_totals, running_totals[1:]))
    assert running_totals[-1] > 0.0


def test_total_work_j_resets_on_fresh_run(tmp_path):
    m = _homed_mode(tmp_path)
    hw = RecordingHardware()
    profile = TrainProfile(segments=[TrainSegment(0.0, 1000.0, "constant", {"force_n": 40.0})])
    _run(m, hw, profile=profile)

    turns = 0.0
    for i in range(1, 11):
        t = i * (1 / 50)
        turns += _STRONG_TURNS_S * (1 / 50)
        hw.sample = _sample(t=t, position=turns, velocity=_STRONG_TURNS_S)
        extra = m.tick(hw, hw.sample)
    assert extra["total_work_j"] > 0.0

    _run(m, hw, profile=profile)
    hw.sample = _sample(t=1000.0, position=turns, velocity=0.0)
    extra = m.tick(hw, hw.sample)
    assert extra["total_work_j"] == pytest.approx(0.0)
