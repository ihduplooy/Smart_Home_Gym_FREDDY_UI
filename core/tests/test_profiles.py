import pytest

from core.hardware.interface import TelemetrySample
from core.profiles import (
    BellCurveProfile,
    ConstantProfile,
    OverloadWrapper,
    PROFILE_REGISTRY,
    Phase,
    ProfileState,
    ResistanceProfile,
    VBTProfile,
)
from core.profiles.units import force_to_torque, torque_to_force


def _state(position=0.0, velocity=0.0, phase=Phase.CONCENTRIC, rep_count=0, t=0.0) -> ProfileState:
    sample = TelemetrySample(t=t, position=position, velocity=velocity, current_iq=0.0, torque_est=0.0)
    return ProfileState(t=t, position=position, velocity=velocity, phase=phase, rep_count=rep_count, sample=sample)


# ---- units ----

def test_force_to_torque_and_back():
    assert force_to_torque(100.0) == pytest.approx(100.0 * 0.05)
    assert torque_to_force(force_to_torque(37.0)) == pytest.approx(37.0)


# ---- ConstantProfile ----

def test_constant_profile_emits_force_times_radius_exactly():
    profile = ConstantProfile(base_force_n=120.0)
    torque = profile.compute_torque(_state())
    assert torque == pytest.approx(force_to_torque(120.0))


def test_constant_profile_primary_parameter_roundtrip():
    profile = ConstantProfile(base_force_n=50.0)
    assert profile.get_primary_parameter() == 50.0
    profile.set_primary_parameter(75.0)
    assert profile.get_primary_parameter() == 75.0
    assert profile.compute_torque(_state()) == pytest.approx(force_to_torque(75.0))


# ---- BellCurveProfile ----

def test_bell_curve_equals_base_force_outside_range():
    profile = BellCurveProfile(base_force_n=100.0, x_start=0.0, x_end=1.0, peak_multiplier=1.5)
    below = profile.compute_torque(_state(position=-0.5))
    above = profile.compute_torque(_state(position=1.5))
    assert below == pytest.approx(force_to_torque(100.0))
    assert above == pytest.approx(force_to_torque(100.0))


def test_bell_curve_peaks_at_midrange():
    profile = BellCurveProfile(base_force_n=100.0, x_start=0.0, x_end=1.0, peak_multiplier=1.5)
    mid_torque = profile.compute_torque(_state(position=0.5))
    quarter_torque = profile.compute_torque(_state(position=0.25))
    assert mid_torque == pytest.approx(force_to_torque(150.0))
    assert quarter_torque > force_to_torque(100.0)
    assert quarter_torque < mid_torque


def test_bell_curve_curve_factor_is_injectable():
    calls = []

    def custom_curve(position):
        calls.append(position)
        return 2.0

    profile = BellCurveProfile(base_force_n=10.0, curve_factor=custom_curve)
    torque = profile.compute_torque(_state(position=0.42))
    assert calls == [0.42]
    assert torque == pytest.approx(force_to_torque(20.0))


# ---- OverloadWrapper ----

@pytest.mark.parametrize("target_phase", [Phase.ECCENTRIC, Phase.CONCENTRIC])
def test_overload_wrapper_multiplies_only_in_target_phase(target_phase):
    base = ConstantProfile(base_force_n=100.0)
    wrapper = OverloadWrapper(wrapped=base, ratio=1.35, target_phase=target_phase)

    other_moving_phase = Phase.CONCENTRIC if target_phase == Phase.ECCENTRIC else Phase.ECCENTRIC
    base_torque = force_to_torque(100.0)

    assert wrapper.compute_torque(_state(phase=target_phase)) == pytest.approx(base_torque * 1.35)
    assert wrapper.compute_torque(_state(phase=other_moving_phase)) == pytest.approx(base_torque)


@pytest.mark.parametrize("target_phase", [Phase.ECCENTRIC, Phase.CONCENTRIC])
@pytest.mark.parametrize("hold_phase", [Phase.TOP_HOLD, Phase.BOTTOM_HOLD])
def test_overload_wrapper_never_multiplies_holds(target_phase, hold_phase):
    base = ConstantProfile(base_force_n=100.0)
    wrapper = OverloadWrapper(wrapped=base, ratio=1.35, target_phase=target_phase)
    assert wrapper.compute_torque(_state(phase=hold_phase)) == pytest.approx(force_to_torque(100.0))


def test_overload_wrapper_primary_parameter_passes_through():
    base = ConstantProfile(base_force_n=100.0)
    wrapper = OverloadWrapper(wrapped=base)
    assert wrapper.get_primary_parameter() == 100.0
    wrapper.set_primary_parameter(60.0)
    assert base.get_primary_parameter() == 60.0
    assert wrapper.get_primary_parameter() == 60.0


def test_overload_wrapper_zero_arg_constructible():
    wrapper = OverloadWrapper()
    assert isinstance(wrapper.wrapped, ResistanceProfile)
    assert wrapper.describe()["is_wrapper"] is True


# ---- VBTProfile ----

def _run_rep(profile: VBTProfile, mean_velocity: float, rep_count: int, n_ticks: int = 10):
    """Simulate one completed rep: n_ticks of CONCENTRIC at a constant
    velocity, then one tick where rep_count increments (finalizing it)."""
    torque = None
    for _ in range(n_ticks):
        torque = profile.compute_torque(_state(phase=Phase.CONCENTRIC, velocity=mean_velocity, rep_count=rep_count - 1))
    torque = profile.compute_torque(_state(phase=Phase.BOTTOM_HOLD, velocity=0.0, rep_count=rep_count))
    return torque


def test_vbt_scales_down_after_a_slow_rep():
    profile = VBTProfile(base_force_n=100.0, v_low=0.3, v_high=0.6, adjust_step=0.05)
    _run_rep(profile, mean_velocity=0.1, rep_count=1)  # below v_low
    assert profile._scalar == pytest.approx(0.95)


def test_vbt_scales_up_after_a_fast_rep():
    profile = VBTProfile(base_force_n=100.0, v_low=0.3, v_high=0.6, adjust_step=0.05)
    _run_rep(profile, mean_velocity=1.0, rep_count=1)  # above v_high
    assert profile._scalar == pytest.approx(1.05)


def test_vbt_holds_scalar_in_band():
    profile = VBTProfile(base_force_n=100.0, v_low=0.3, v_high=0.6, adjust_step=0.05)
    _run_rep(profile, mean_velocity=0.45, rep_count=1)  # in band
    assert profile._scalar == pytest.approx(1.0)


def test_vbt_only_adjusts_on_rep_boundary_not_every_tick():
    profile = VBTProfile(base_force_n=100.0, v_low=0.3, v_high=0.6, adjust_step=0.05)
    for _ in range(20):
        profile.compute_torque(_state(phase=Phase.CONCENTRIC, velocity=0.1, rep_count=0))
        assert profile._scalar == pytest.approx(1.0)  # unchanged mid-rep
    profile.compute_torque(_state(phase=Phase.BOTTOM_HOLD, velocity=0.0, rep_count=1))
    assert profile._scalar == pytest.approx(0.95)  # adjusted exactly once, at the boundary


def test_vbt_reset_clears_scalar_and_accumulator():
    profile = VBTProfile(base_force_n=100.0)
    _run_rep(profile, mean_velocity=0.1, rep_count=1)
    profile.reset()
    assert profile._scalar == 1.0
    assert profile._concentric_v_ticks == 0


# ---- registry ----

def test_profile_registry_has_all_four_and_overload_flagged_as_wrapper():
    assert set(PROFILE_REGISTRY) == {"constant", "bell_curve", "vbt", "overload"}
    for name, factory in PROFILE_REGISTRY.items():
        instance = factory()
        assert isinstance(instance, ResistanceProfile)
        assert instance.describe()["is_wrapper"] == (name == "overload")


# ---- a raising profile (safety behaviour extended to profiles) ----

class _RaisingProfile(ResistanceProfile):
    name = "raising"

    def compute_torque(self, state):
        raise RuntimeError("boom")

    def describe(self):
        return {"name": self.name, "is_wrapper": False, "primary_parameter": "x", "parameters": {}}

    @property
    def primary_parameter_label(self):
        return "x"

    def get_primary_parameter(self):
        return 0.0

    def set_primary_parameter(self, value):
        pass

    def reset(self):
        pass


def test_raising_profile_compute_torque_raises():
    profile = _RaisingProfile()
    with pytest.raises(RuntimeError, match="boom"):
        profile.compute_torque(_state())
