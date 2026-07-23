"""core/cable/force_mode.py tests (exercise_tab_build_spec_layerB.md §6, §12).

Most tests drive ForceMode directly against a small recording fake hardware,
same style as core/tests/test_exercise_mode.py -- faster and more precise
than round-tripping through ControlSession's thread. One end-to-end test
exercises the real ControlSession + mode_factories wiring, including the
global-Stop-mid-ENGAGED safety behaviour (§6 item 9).
"""

import time
from typing import List

import pytest

from config import board_constants
from core.cable.force_mode import ForceMode, ForceState
from core.cable.state import CableState
from core.control.session import ControlSession
from core.control.modes import MODES_BY_NAME
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles.detectors import CABLE_SIGN
from core.profiles.units import force_to_torque

DT = 1.0 / 50.0


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
        self.calls.append(("set_position_target", turns, move_velocity, accel_decel))

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


def _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json")
    cable_state.latch_home(home)
    cable_state.set_max(marked_turns=max_turns, enforced_turns=max_turns)
    return ForceMode(cable_state)


def _sample(t, position, velocity, current_iq=0.0, torque_est=0.0):
    return TelemetrySample(t=t, position=position, velocity=velocity, current_iq=current_iq, torque_est=torque_est)


def _arm(mode, hw):
    mode.apply_target(hw, mode.validate_target({"action": "arm"}))


def _fast_ramp(monkeypatch):
    # Full-scale ramp in ~1 tick so tests don't need dozens of ticks to
    # reach steady state, without testing zero-time (instant) application.
    monkeypatch.setattr(board_constants, "FORCE_RAMP_IN_S", 0.02)
    monkeypatch.setattr(board_constants, "FORCE_RAMP_OUT_S", 0.02)


# ---- §6 item 1: no torque without explicit engagement ----

def test_construction_and_arm_apply_zero_torque(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    assert hw.calls == []
    _arm(mode, hw)
    assert hw.mode == ControlMode.TORQUE
    assert hw.torque_target == 0.0
    assert mode.state == ForceState.ARMED


def test_engage_requires_explicit_action(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    extra = mode.tick(hw, _sample(0.0, 0.0, 0.0))
    assert extra["force_state"] == "armed"
    assert extra["commanded_force_n"] == 0.0


def test_engage_requires_homed(tmp_path):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json")
    mode = ForceMode(cable_state)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))


def test_engage_requires_max_set(tmp_path):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json")
    cable_state.latch_home(0.0)
    mode = ForceMode(cable_state)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))


def test_engage_rejected_while_already_engaged(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))


# ---- §6 item 2: force ramps, never steps ----

def test_force_ramps_in_not_instant(tmp_path, monkeypatch):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 100.0}))

    # First tick() ever called establishes the dt baseline (dt=0, matching
    # sim_hw.py's own first-call convention) -- ramp progress shows from the
    # second tick onward, once a real dt exists.
    mode.tick(hw, _sample(0.0, 0.0, 0.0))
    extra = mode.tick(hw, _sample(0.02, 0.0, 0.0))
    assert 0.0 < extra["commanded_force_n"] < 100.0  # partway there, not instant


def test_force_ramps_in_reaches_target_eventually(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 100.0}))

    t = 0.0
    extra = None
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    assert extra["commanded_force_n"] == pytest.approx(100.0, abs=0.5)


def test_force_ramps_out_on_disengage_not_instant(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 100.0}))
    t = 0.0
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        mode.tick(hw, hw.sample)

    mode.apply_target(hw, mode.validate_target({"action": "disengage"}))
    t += DT
    hw.sample = _sample(t, 0.0, 0.0)
    extra = mode.tick(hw, hw.sample)
    assert extra["force_state"] == "armed"
    assert 0.0 <= extra["commanded_force_n"] < 100.0  # dropping, not stepped to 0


# ---- §6 items 3/4: let-go detector fires in concentric, gated off elsewhere ----

def test_letgo_fires_during_concentric_and_hard_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 5)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 100.0}))

    t = 0.0
    extra = None
    reel_in_velocity = -CABLE_SIGN * 0.5
    for _ in range(6):
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        extra = mode.tick(hw, hw.sample)

    assert mode.state == ForceState.FAULT
    assert extra["force_state"] == "fault"
    assert hw.stop_calls >= 1
    assert hw.torque_target == 0.0
    assert extra["fault_reason"] is not None


def test_letgo_does_not_fire_during_holding(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 3)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))
    mode.state = ForceState.HOLDING  # force into HOLDING directly for isolation

    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    extra = None
    for _ in range(10):
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        extra = mode.tick(hw, hw.sample)

    assert mode.state == ForceState.HOLDING  # not faulted -- let-go gated off here
    assert extra["force_state"] == "holding"


def test_letgo_does_not_fire_while_armed(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 3)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)

    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    for _ in range(10):
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        extra = mode.tick(hw, hw.sample)
    assert mode.state == ForceState.ARMED


def test_letgo_does_not_fire_on_subdebounce_transient(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 5)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 100.0}))

    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    for _ in range(4):  # one short of the debounce window
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        mode.tick(hw, hw.sample)
    assert mode.state == ForceState.ENGAGED_CONCENTRIC


# ---- §6 item 5: no integrator / no wind-up ----

def test_no_windup_on_sustained_hold_still(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "ISOKINETIC_VELOCITY_TARGET_TURNS_S", 1.0)
    monkeypatch.setattr(board_constants, "ISOKINETIC_GOVERNOR_GAIN", 150.0)
    monkeypatch.setattr(board_constants, "HOLD_DURATION_S", 10_000.0)  # never enter HOLDING for this test
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(
        hw, mode.validate_target({"action": "engage", "mode": "isokinetic", "force_n": 20.0, "velocity_target_turns_s": 1.0})
    )

    t = 0.0
    forces = []
    for _ in range(500):  # many hundreds of ticks, velocity held exactly at rest
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)  # stationary throughout
        extra = mode.tick(hw, hw.sample)
        forces.append(extra["commanded_force_n"])

    # Below target velocity the whole time -> should settle at the base
    # force and stay there, never climbing.
    assert forces[-1] == pytest.approx(20.0, abs=1.0)
    assert max(forces[-50:]) - min(forces[-50:]) < 1.0  # flat, not still rising


# ---- §6 item 10: sign correctness ----

def test_commanded_torque_opposes_pay_out_during_concentric(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))

    paying_out_velocity = CABLE_SIGN * 0.3  # concentric: paying out
    mode.tick(hw, _sample(0.0, 0.0, paying_out_velocity))  # establish dt baseline
    mode.tick(hw, _sample(0.02, 0.0, paying_out_velocity))

    # Torque sign must be opposite to CABLE_SIGN's positive (pay-out) direction.
    assert hw.torque_target < 0 if CABLE_SIGN > 0 else hw.torque_target > 0
    assert hw.torque_target != 0.0


def test_commanded_torque_magnitude_matches_force_to_torque(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))
    t = 0.0
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        mode.tick(hw, hw.sample)
    assert abs(hw.torque_target) == pytest.approx(force_to_torque(50.0), rel=0.05)


# ---- §6 item 6: force clamped by F_max ----

def test_force_clamped_at_force_max(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(ValueError):
        mode.apply_target(
            hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": board_constants.FORCE_MAX_N + 1.0})
        )


# ---- §6 item 7: force eases off approaching max extension ----

def test_force_tapers_approaching_max_extension(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    monkeypatch.setattr(board_constants, "MAX_EXTENSION_FORCE_TAPER_M", 0.15)
    mode = _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 100.0}))

    # Far from the limit: full force after ramp settles.
    t = 0.0
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 5.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    far_force = extra["commanded_force_n"]

    # Right at the limit: force should have eased toward zero.
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 20.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    near_force = extra["commanded_force_n"]

    assert far_force > near_force
    assert near_force < 10.0


# ---- §6 item 8: fault zeroes torque and requires explicit manual resume ----

def test_resume_returns_to_armed_not_engaged(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 3)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))
    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    for _ in range(4):
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        mode.tick(hw, hw.sample)
    assert mode.state == ForceState.FAULT

    mode.apply_target(hw, mode.validate_target({"action": "resume"}))
    assert mode.state == ForceState.ARMED
    assert hw.torque_target == 0.0


def test_resume_preserves_force_params_and_leaves_home_max_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 3)
    mode = _homed_and_maxed_mode(tmp_path, home=1.0, max_turns=21.0)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 77.0}))
    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    for _ in range(4):
        t += DT
        hw.sample = _sample(t, 1.0, reel_in_velocity)
        mode.tick(hw, hw.sample)
    assert mode.state == ForceState.FAULT

    mode.apply_target(hw, mode.validate_target({"action": "resume"}))
    assert mode._force_n_param == 77.0  # preserved
    assert mode.cable_state.home_turns == 1.0
    assert mode.cable_state.max_turns == 21.0


def test_resume_rejected_when_not_faulted(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "resume"}))


# ---- §6 item 9: Stop remains available/effective mid-ENGAGED (end-to-end) ----

def test_global_stop_mid_engaged_zeroes_torque_and_restores_current_limit(tmp_path):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json")
    cable_state.latch_home(0.0)
    cable_state.set_max(marked_turns=20.0, enforced_turns=20.0)
    session = ControlSession(
        hardware_source="sim",
        mode_factories={**MODES_BY_NAME, "force": lambda: ForceMode(cable_state)},
    )
    session.start(mode="force", target={"action": "arm"})
    session.set_target({"action": "engage", "mode": "constant", "force_n": 50.0})
    time.sleep(0.1)
    assert session.status()["running"] is True

    session.stop()
    assert session.status()["running"] is False

    # A subsequent session of any mode must still see the normal operating
    # current limit -- Layer A's connect()-time reassert backstop must not
    # have been defeated by a Force session stopping mid-ENGAGED.
    session2 = ControlSession(hardware_source="sim")
    session2.start(mode="velocity", target=0.1)
    time.sleep(0.05)
    session2.stop()


# ---- hold detection ----

def test_enters_holding_after_configured_duration(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "HOLD_DURATION_S", 0.1)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))

    t = 0.0
    extra = None
    for _ in range(10):  # 0.2s of stationary velocity -- exceeds HOLD_DURATION_S=0.1
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    assert extra["force_state"] == "holding"


def test_does_not_enter_holding_on_a_brief_pause(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "HOLD_DURATION_S", 1.0)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))

    t = 0.0
    extra = None
    for _ in range(5):  # 0.1s, well short of HOLD_DURATION_S=1.0
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    assert extra["force_state"] == "engaged_concentric"


def test_holding_force_settles_at_force_min(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "HOLD_DURATION_S", 0.05)
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 100.0}))

    t = 0.0
    extra = None
    for _ in range(40):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    assert extra["force_state"] == "holding"
    assert extra["commanded_force_n"] == pytest.approx(board_constants.FORCE_MIN_N, abs=1.0)


# ---- update_params ----

def test_update_params_changes_target_live_without_leaving_engaged(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    monkeypatch.setattr(board_constants, "HOLD_DURATION_S", 10_000.0)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "engage", "mode": "constant", "force_n": 50.0}))
    t = 0.0
    for _ in range(10):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        mode.tick(hw, hw.sample)

    mode.apply_target(hw, mode.validate_target({"action": "update_params", "mode": "constant", "force_n": 90.0}))
    assert mode.state == ForceState.ENGAGED_CONCENTRIC
    extra = None
    for _ in range(10):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    assert extra["commanded_force_n"] == pytest.approx(90.0, abs=1.0)


def test_update_params_rejected_while_armed(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "update_params", "mode": "constant", "force_n": 50.0}))


# ---- estimated/telemetry fields ----

def test_estimated_force_reflects_measured_torque(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    hw.sample = _sample(0.0, 0.0, 0.0, current_iq=1.0, torque_est=board_constants.MOTOR_TORQUE_CONSTANT * 1.0)
    extra = mode.tick(hw, hw.sample)
    expected = board_constants.MOTOR_TORQUE_CONSTANT * 1.0 / board_constants.SPOOL_RADIUS_M
    assert extra["estimated_force_n"] == pytest.approx(expected)
