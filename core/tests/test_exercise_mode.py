"""core/cable/exercise_mode.py tests (exercise_tab_build_spec_layerA.md §4,
§8). Most tests drive ExerciseMode directly against a small recording fake
hardware (same style as core/tests/test_control_session.py's fakes) --
faster and more precise than round-tripping through ControlSession's thread,
and consistent with core/tests/test_modes.py's style for the other modes.
One end-to-end test exercises the real ControlSession + mode_factories
wiring.
"""

import time
from typing import List

import pytest

from config import board_constants
from core.cable.geometry import length_from_turns_delta, turns_delta_from_length
from core.cable.exercise_mode import ExerciseMode
from core.cable.homing import HomingState
from core.cable.state import CableState
from core.control.session import ControlSession
from core.control.modes import MODES_BY_NAME
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles.detectors import CABLE_SIGN
from core.profiles.units import force_to_torque


class RecordingHardware(HardwareInterface):
    """Records every call in order; get_state() returns whatever the test
    last set via `.sample`."""

    def __init__(self):
        self.connected = False
        self.calls: List[tuple] = []
        self.mode = None
        self.velocity_target = None
        self.torque_target = None
        self.current_limit = None
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
        self.calls.append(("set_position_target", turns, move_velocity, accel_decel))

    def set_current_limit(self, amps):
        self.calls.append(("set_current_limit", amps))
        self.current_limit = amps

    def stop(self):
        self.calls.append(("stop",))

    def get_errors(self):
        return []


def _mode(tmp_path):
    return ExerciseMode(CableState(sidecar_path=tmp_path / "spool_calibration.json"))


def _arm(mode, hw):
    mode.apply_target(hw, mode.validate_target({"action": "arm"}))


# ---- validate_target ----

def test_validate_target_rejects_non_dict(tmp_path):
    mode = _mode(tmp_path)
    with pytest.raises(TypeError):
        mode.validate_target("home")


def test_validate_target_rejects_unknown_action(tmp_path):
    mode = _mode(tmp_path)
    with pytest.raises(ValueError):
        mode.validate_target({"action": "levitate"})


# ---- safety §4 item 1: no motion without an explicit user action ----

def test_construction_does_not_move_anything(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    assert hw.calls == []
    assert mode._action == "idle"


def test_arm_holds_zero_velocity_no_homing_started(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    assert hw.mode == ControlMode.VELOCITY
    assert hw.velocity_target == 0.0
    extra = mode.tick(hw, hw.sample)
    assert extra["action"] == "idle"
    assert extra["is_homed"] is False


# ---- homing lifecycle ----

def test_home_action_starts_homing_only_explicitly(tmp_path, monkeypatch):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    assert mode._action == "idle"

    mode.apply_target(hw, mode.validate_target({"action": "home"}))
    assert mode._action == "homing"
    # Current limit lowered as part of arming homing, before the first
    # tick() ever issues a reel-in velocity command.
    assert ("set_current_limit", board_constants.HOMING_CURRENT_LIMIT_A) in hw.calls
    assert not any(c[0] == "set_velocity_target" and c[1] != 0.0 for c in hw.calls)


def test_home_rejected_while_already_homing(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "home"}))
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "home"}))


def test_homing_completes_latches_home_and_restores_current_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "HOMING_DEBOUNCE_SAMPLES", 3)
    monkeypatch.setattr(board_constants, "HOMING_STARTUP_GRACE_S", 0.02)
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "home"}))

    t = 0.0
    dt = 1.0 / 50.0
    position = 0.0
    # Clear grace.
    for _ in range(3):
        hw.sample = TelemetrySample(t=t, position=position, velocity=-0.15, current_iq=0.1, torque_est=0.0)
        mode.tick(hw, hw.sample)
        t += dt
        position -= 0.15 * dt
    # Cross threshold for the debounce window (above the live
    # HOMING_CURRENT_THRESHOLD_A=2.0, not a monkeypatched test value --
    # this test exercises the real board_constants default deliberately).
    extra = None
    for _ in range(3):
        hw.sample = TelemetrySample(t=t, position=position, velocity=-0.15, current_iq=2.5, torque_est=0.0)
        extra = mode.tick(hw, hw.sample)
        t += dt
        position -= 0.15 * dt

    assert extra["homing_state"] == HomingState.HOMED.value
    assert mode.cable_state.is_homed is True
    assert mode._action == "idle"
    assert mode.cable_state.homing_in_progress is False
    # Restored to the normal operating limit after homing succeeds.
    assert ("set_current_limit", board_constants.MOTOR_CURRENT_LIM) in hw.calls


def test_homing_fault_restores_current_limit_and_records_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "HOMING_TIMEOUT_S", 0.02)
    monkeypatch.setattr(board_constants, "HOMING_MAX_TRAVEL_TURNS", 1000.0)
    monkeypatch.setattr(board_constants, "HOMING_STARTUP_GRACE_S", 0.01)
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "home"}))

    t = 0.0
    dt = 1.0 / 50.0
    extra = None
    for _ in range(20):
        hw.sample = TelemetrySample(t=t, position=0.0, velocity=0.0, current_iq=0.0, torque_est=0.0)
        extra = mode.tick(hw, hw.sample)
        t += dt
        if extra.get("homing_state") == HomingState.FAULT_TIMEOUT.value:
            break

    assert extra["homing_state"] == HomingState.FAULT_TIMEOUT.value
    assert mode.cable_state.is_homed is False
    assert mode.cable_state.last_homing_fault is not None
    assert ("set_current_limit", board_constants.MOTOR_CURRENT_LIM) in hw.calls


def test_abort_homing_restores_current_limit_and_stops_immediately(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "home"}))
    mode.tick(hw, hw.sample)  # partway through, still homing

    mode.apply_target(hw, mode.validate_target({"action": "abort_homing"}))
    assert mode._action == "idle"
    assert mode.cable_state.homing_in_progress is False
    assert hw.velocity_target == 0.0
    assert hw.current_limit == board_constants.MOTOR_CURRENT_LIM
    assert mode.cable_state.is_homed is False


def test_abort_homing_when_not_homing_is_a_safe_no_op(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "abort_homing"}))  # must not raise
    assert mode._action == "idle"


# ---- max-extension calibration ----

def test_max_calibration_requires_homed(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "start_max_calibration"}))


def test_max_calibration_applies_hold_torque_toward_home(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)

    mode.apply_target(hw, mode.validate_target({"action": "start_max_calibration"}))
    assert hw.mode == ControlMode.TORQUE
    expected = -CABLE_SIGN * force_to_torque(board_constants.CALIB_HOLD_FORCE_N)
    assert hw.torque_target == pytest.approx(expected)
    assert mode._action == "max_calibrating"


def test_confirm_max_stores_margin_adjusted_value(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.apply_target(hw, mode.validate_target({"action": "start_max_calibration"}))

    marked_turns = 10.0
    hw.sample = TelemetrySample(t=1.0, position=marked_turns, velocity=0.0, current_iq=0.0, torque_est=0.0)
    mode.apply_target(hw, mode.validate_target({"action": "confirm_max"}))

    margin_turns = turns_delta_from_length(board_constants.MAX_EXTENSION_SAFETY_MARGIN_M, mode.cable_state.r0, mode.cable_state.k)
    assert mode.cable_state.max_turns == pytest.approx(marked_turns - CABLE_SIGN * margin_turns)
    assert mode.cable_state.marked_max_turns == marked_turns
    assert mode._action == "idle"
    assert mode.cable_state.max_calibration_in_progress is False
    assert hw.torque_target == 0.0
    assert hw.mode == ControlMode.VELOCITY


def test_confirm_max_rejects_implausibly_close_point_and_stays_in_progress(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.apply_target(hw, mode.validate_target({"action": "start_max_calibration"}))

    hw.sample = TelemetrySample(t=1.0, position=0.01, velocity=0.0, current_iq=0.0, torque_est=0.0)
    with pytest.raises(ValueError):
        mode.apply_target(hw, mode.validate_target({"action": "confirm_max"}))
    # Rejected candidate must not have ended the calibration.
    assert mode._action == "max_calibrating"
    assert mode.cable_state.has_max is False


def test_cancel_max_calibration_discards_without_storing(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.apply_target(hw, mode.validate_target({"action": "start_max_calibration"}))
    mode.apply_target(hw, mode.validate_target({"action": "cancel_max_calibration"}))

    assert mode.cable_state.has_max is False
    assert mode._action == "idle"
    assert hw.torque_target == 0.0


# ---- length-based moves ----

def test_move_rejected_when_unhomed(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "move", "target_length_m": 0.1}))


def test_move_rejected_without_max_set(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "move", "target_length_m": 0.1}))


def test_move_clamps_target_beyond_max(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.cable_state.set_max(marked_turns=10.0, enforced_turns=9.0)

    huge_length_m = length_from_turns_delta(50.0, mode.cable_state.r0, mode.cable_state.k)
    mode.apply_target(hw, mode.validate_target({"action": "move", "target_length_m": huge_length_m}))

    set_pos_calls = [c for c in hw.calls if c[0] == "set_position_target"]
    assert set_pos_calls
    assert set_pos_calls[-1][1] == pytest.approx(9.0)
    assert mode._action == "moving"


def test_move_completion_flips_action_back_to_idle(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.cable_state.set_max(marked_turns=10.0, enforced_turns=9.0)
    mode.apply_target(hw, mode.validate_target({"action": "move", "target_length_m": 0.5}))
    assert mode._action == "moving"

    target = mode._move_target_turns
    hw.sample = TelemetrySample(t=1.0, position=target, velocity=0.0, current_iq=0.0, torque_est=0.0)
    extra = mode.tick(hw, hw.sample)
    assert extra["action"] == "idle"


# ---- runtime guard (§4 item 6) ----

def test_tick_raises_when_position_leaves_range_beyond_tolerance(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.cable_state.set_max(marked_turns=10.0, enforced_turns=9.0)

    hw.sample = TelemetrySample(t=1.0, position=20.0, velocity=0.0, current_iq=0.0, torque_est=0.0)
    with pytest.raises(RuntimeError):
        mode.tick(hw, hw.sample)


def test_tick_does_not_raise_within_range(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.cable_state.set_max(marked_turns=10.0, enforced_turns=9.0)

    hw.sample = TelemetrySample(t=1.0, position=5.0, velocity=0.0, current_iq=0.0, torque_est=0.0)
    mode.tick(hw, hw.sample)  # must not raise


def test_runtime_guard_not_checked_before_max_is_set(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    # No max set -- an arbitrarily large position must not trip the guard.
    hw.sample = TelemetrySample(t=1.0, position=1000.0, velocity=0.0, current_iq=0.0, torque_est=0.0)
    mode.tick(hw, hw.sample)  # must not raise


# ---- telemetry ----

def test_cable_length_is_none_until_homed(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    extra = mode.tick(hw, hw.sample)
    assert extra["cable_length_m"] is None


def test_cable_length_matches_geometry_once_homed(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    hw.sample = TelemetrySample(t=1.0, position=3.0, velocity=0.0, current_iq=0.0, torque_est=0.0)
    extra = mode.tick(hw, hw.sample)
    expected = length_from_turns_delta(3.0, mode.cable_state.r0, mode.cable_state.k)
    assert extra["cable_length_m"] == pytest.approx(expected)


# ---- end-to-end via the real ControlSession + mode_factories injection ----

def test_exercise_csv_gains_cable_length_column(tmp_path):
    import csv as csv_module

    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json")
    session = ControlSession(
        hardware_source="sim",
        mode_factories={**MODES_BY_NAME, "exercise": lambda: ExerciseMode(cable_state)},
    )
    session.start(mode="exercise", target={"action": "arm"})
    time.sleep(0.1)
    log_path = session.status()["log_path"]
    session.stop()

    with open(log_path, newline="") as f:
        rows = list(csv_module.reader(f))
    header = rows[0]
    assert "cable_length_m" in header
    data_row = rows[1]
    assert data_row[header.index("cable_length_m")] == ""  # un-homed


def test_exercise_csv_cable_length_populated_once_homed(tmp_path):
    import csv as csv_module

    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json")
    cable_state.latch_home(0.0)  # bypass a full homing run; latch directly
    session = ControlSession(
        hardware_source="sim",
        mode_factories={**MODES_BY_NAME, "exercise": lambda: ExerciseMode(cable_state)},
    )
    session.start(mode="exercise", target={"action": "arm"})
    time.sleep(0.1)
    log_path = session.status()["log_path"]
    session.stop()

    with open(log_path, newline="") as f:
        rows = list(csv_module.reader(f))
    header = rows[0]
    data_row = rows[1]
    cell = data_row[header.index("cable_length_m")]
    assert cell != ""
    float(cell)  # must parse as a number


def test_exercise_mode_end_to_end_via_control_session(tmp_path):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json")
    session = ControlSession(
        hardware_source="sim",
        mode_factories={**MODES_BY_NAME, "exercise": lambda: ExerciseMode(cable_state)},
    )
    session.start(mode="exercise", target={"action": "arm"})
    time.sleep(0.05)
    status = session.status()
    assert status["running"] is True
    assert status["mode"] == "exercise"
    assert status["extra"]["action"] == "idle"
    assert status["extra"]["is_homed"] is False

    session.set_target({"action": "home"})
    time.sleep(0.05)
    status = session.status()
    assert status["extra"]["action"] == "homing" or status["extra"]["homing_state"] is not None

    session.stop()
    assert session.status()["running"] is False
