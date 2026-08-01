"""core/cable/train_mode.py tests. Same RecordingHardware-fake style as
core/tests/test_exercise_mode.py -- faster and more precise than
round-tripping through ControlSession's thread.
"""

from typing import List

import pytest

from config import board_constants
from core.cable import geometry
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
    return TrainMode(CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json"))


def _homed_mode(tmp_path, home=0.0, max_turns=None):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json")
    cable_state.latch_home(home)
    if max_turns is not None:
        cable_state.set_max(marked_turns=max_turns, enforced_turns=max_turns)
    return TrainMode(cable_state)


def _run(mode, hw, profile=None):
    target = {"action": "run"}
    if profile is not None:
        target["profile"] = profile
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
