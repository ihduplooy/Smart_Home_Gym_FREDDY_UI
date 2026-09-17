"""core/cable/exercise_mode.py tests. Most tests drive ExerciseMode directly
against a small recording fake hardware (same style as
core/tests/test_control_session.py's fakes) -- faster and more precise than
round-tripping through ControlSession's thread. A handful of end-to-end
tests exercise the real ControlSession + mode_factories wiring.

Layer A (homing/max-extension/moves) and Layer B (force feedback) used to be
two separate mode classes (ExerciseMode/ForceMode) with two separate test
files; merged 24 July 2026 into one ExerciseMode and one test file, matching
the production merge (see core/cable/exercise_mode.py's module docstring).
"""

import time
from typing import List

import pytest

from config import board_constants
from core.cable.geometry import length_from_turns_delta, turns_delta_from_length
from core.cable.exercise_mode import ExerciseMode, ForceState
from core.cable.homing import HomingState
from core.cable.state import CableState
from core.control.session import ControlSession
from core.control.modes import MODES_BY_NAME
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles.detectors import CABLE_SIGN
from core.profiles.units import force_to_torque

DT = 1.0 / 50.0


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


def _mode(tmp_path):
    return ExerciseMode(CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json"))


def _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json")
    cable_state.latch_home(home)
    cable_state.set_max(marked_turns=max_turns, enforced_turns=max_turns)
    return ExerciseMode(cable_state)


def _sample(t, position, velocity, current_iq=0.0, torque_est=0.0):
    return TelemetrySample(t=t, position=position, velocity=velocity, current_iq=current_iq, torque_est=torque_est)


def _arm(mode, hw):
    mode.apply_target(hw, mode.validate_target({"action": "arm"}))


def _fast_ramp(monkeypatch):
    # Full-scale ramp in ~1 tick so tests don't need dozens of ticks to reach
    # steady state, without testing zero-time (instant) application. These
    # are read into CableState at construction, so the monkeypatch must
    # happen before the mode/CableState is built (every caller below does).
    monkeypatch.setattr(board_constants, "FORCE_RAMP_IN_S", 0.02)
    monkeypatch.setattr(board_constants, "FORCE_RAMP_OUT_S", 0.02)


def _engage(mode, hw, mode_name="constant", concentric_force_n=50.0, eccentric_force_n=50.0, **kwargs):
    payload = {
        "action": "engage",
        "mode": mode_name,
        "concentric_force_n": concentric_force_n,
        "eccentric_force_n": eccentric_force_n,
        **kwargs,
    }
    return mode.apply_target(hw, mode.validate_target(payload))


# ==========================================================================
# Layer A: homing / max-extension / moves / runtime guard
# ==========================================================================

# ---- validate_target ----

def test_validate_target_rejects_non_dict(tmp_path):
    mode = _mode(tmp_path)
    with pytest.raises(TypeError):
        mode.validate_target("home")


def test_validate_target_rejects_unknown_action(tmp_path):
    mode = _mode(tmp_path)
    with pytest.raises(ValueError):
        mode.validate_target({"action": "levitate"})


# ---- safety: no motion without an explicit user action ----

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
    for _ in range(3):
        hw.sample = TelemetrySample(t=t, position=position, velocity=-0.15, current_iq=0.1, torque_est=0.0)
        mode.tick(hw, hw.sample)
        t += dt
        position -= 0.15 * dt
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


def test_confirm_max_stores_marked_point_exactly(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.apply_target(hw, mode.validate_target({"action": "start_max_calibration"}))

    marked_turns = 10.0
    hw.sample = TelemetrySample(t=1.0, position=marked_turns, velocity=0.0, current_iq=0.0, torque_est=0.0)
    mode.apply_target(hw, mode.validate_target({"action": "confirm_max"}))

    assert mode.cable_state.max_turns == pytest.approx(marked_turns)
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


# ---- experimental multi-point spool-growth calibration (train tab
# calibration overhaul item 4) -- same hold-torque shape as max-extension
# calibration above ----

def test_spool_growth_calibration_requires_homed(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "start_spool_growth_calibration"}))


def test_spool_growth_calibration_applies_hold_torque(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)

    mode.apply_target(hw, mode.validate_target({"action": "start_spool_growth_calibration"}))
    assert hw.mode == ControlMode.TORQUE
    expected = -CABLE_SIGN * force_to_torque(board_constants.CALIB_HOLD_FORCE_N)
    assert hw.torque_target == pytest.approx(expected)
    assert mode._action == "spool_growth_calibrating"
    assert mode.cable_state.spool_growth_calibration_in_progress is True


def test_spool_growth_calibration_tick_reapplies_hold_torque(tmp_path):
    # tick() must route "spool_growth_calibrating" through the same generic
    # hold-torque handling max_calibrating already gets.
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.apply_target(hw, mode.validate_target({"action": "start_spool_growth_calibration"}))

    hw.torque_target = 0.0  # clear, so the tick below proves it re-applies
    mode.tick(hw, _sample(t=1.0, position=3.0, velocity=0.0))
    expected = -CABLE_SIGN * force_to_torque(board_constants.CALIB_HOLD_FORCE_N)
    assert hw.torque_target == pytest.approx(expected)


def test_end_spool_growth_calibration_tears_down_and_is_a_safe_no_op_when_idle(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.apply_target(hw, mode.validate_target({"action": "start_spool_growth_calibration"}))

    mode.apply_target(hw, mode.validate_target({"action": "end_spool_growth_calibration"}))
    assert mode._action == "idle"
    assert mode.cable_state.spool_growth_calibration_in_progress is False
    assert hw.torque_target == 0.0
    assert hw.mode == ControlMode.VELOCITY

    # Calling it again with nothing in progress must not raise or re-toggle
    # anything.
    mode.apply_target(hw, mode.validate_target({"action": "end_spool_growth_calibration"}))
    assert mode._action == "idle"


def test_spool_growth_calibration_rejected_while_max_calibrating(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.apply_target(hw, mode.validate_target({"action": "start_max_calibration"}))
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "start_spool_growth_calibration"}))


# ---- length-based moves ----

def test_move_rejected_when_unhomed(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "move", "target_length_m": 0.1}))


def test_move_allowed_without_max_set_clamped_to_home_only(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)

    target_length_m = length_from_turns_delta(5.0, mode.cable_state.r0, mode.cable_state.k)
    mode.apply_target(hw, mode.validate_target({"action": "move", "target_length_m": target_length_m}))

    set_pos_calls = [c for c in hw.calls if c[0] == "set_position_target"]
    assert set_pos_calls
    assert set_pos_calls[-1][1] == pytest.approx(5.0 * CABLE_SIGN)
    assert mode._action == "moving"


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


# ---- runtime guard (two-tier: warning band + hard stop) ----

def test_tick_raises_when_position_leaves_range_beyond_hard_tolerance(tmp_path):
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
    extra = mode.tick(hw, hw.sample)  # must not raise
    assert extra["position_warning"] is False


def test_runtime_guard_not_checked_before_max_is_set(tmp_path):
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    hw.sample = TelemetrySample(t=1.0, position=1000.0, velocity=0.0, current_iq=0.0, torque_est=0.0)
    mode.tick(hw, hw.sample)  # must not raise


def test_guard_disabled_when_both_enforcement_toggles_off(tmp_path):
    # Item 4: the runtime guard used to be unconditional here regardless of
    # train_home_guard_enforced/train_max_extension_enforced -- those two
    # toggles now gate ExerciseMode's guard the same way TrainMode's own
    # already was, so disabling them turns this off too (Go Home/Homing/
    # manual moves), not just Train sessions.
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.cable_state.set_max(marked_turns=10.0, enforced_turns=9.0)
    mode.cable_state.set_train_settings(max_extension_enforced=False, home_guard_enforced=False)

    hw.sample = TelemetrySample(t=1.0, position=20.0, velocity=0.0, current_iq=0.0, torque_est=0.0)
    extra = mode.tick(hw, hw.sample)  # must not raise
    assert extra["position_warning"] is False


def test_guard_still_fires_when_only_one_toggle_enabled(tmp_path):
    # Combined (OR) gating, not per-side like TrainMode's split check --
    # leaving either toggle on keeps the guard fully active.
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.cable_state.set_max(marked_turns=10.0, enforced_turns=9.0)
    mode.cable_state.set_train_settings(max_extension_enforced=True, home_guard_enforced=False)

    hw.sample = TelemetrySample(t=1.0, position=20.0, velocity=0.0, current_iq=0.0, torque_est=0.0)
    with pytest.raises(RuntimeError):
        mode.tick(hw, hw.sample)


def test_position_warning_tier_fires_before_hard_tier(tmp_path):
    # Sitting between the warning and hard tolerances: warned, not stopped.
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)
    mode.cable_state.set_max(marked_turns=10.0, enforced_turns=9.0)
    warning_t = mode.cable_state.position_guard_warning_turns
    hard_t = mode.cable_state.position_guard_hard_turns
    assert warning_t < hard_t  # precondition for this test to mean anything

    midpoint_excess = (warning_t + hard_t) / 2.0
    hw.sample = TelemetrySample(t=1.0, position=9.0 + midpoint_excess, velocity=0.0, current_iq=0.0, torque_est=0.0)
    extra = mode.tick(hw, hw.sample)  # must not raise
    assert extra["position_warning"] is True


# ---- gating: Layer A actions require force feedback to be ARMED ----

def test_home_rejected_while_force_engaged(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)
    assert mode._force_state == ForceState.ENGAGED
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "home"}))


def test_move_rejected_while_force_engaged(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "move", "target_length_m": 0.1}))


def test_start_max_calibration_rejected_while_force_engaged(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "start_max_calibration"}))


def test_home_allowed_again_after_disengage(tmp_path, monkeypatch):
    # This is the whole point of the merge: disengage (a fast, in-session
    # action) is enough to unblock Layer A actions again -- no session stop
    # needed.
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "disengage"}))
    assert mode._force_state == ForceState.ARMED
    mode.apply_target(hw, mode.validate_target({"action": "home"}))  # must not raise
    assert mode._action == "homing"


def test_engage_rejected_while_homing(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.apply_target(hw, mode.validate_target({"action": "home"}))
    assert mode._action == "homing"
    with pytest.raises(RuntimeError):
        _engage(mode, hw)


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


def test_cable_length_reflects_experimental_growth_model_once_saved(tmp_path):
    # Proves the refactored call site (cable_state.spool_geometry, not the
    # bare r0/k free functions) actually takes effect: once growth points
    # are set, tick()'s cable_length_m must follow the piecewise model, not
    # the plain linear one.
    mode = _mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    mode.cable_state.latch_home(0.0)

    r0 = mode.cable_state.r0
    theta_turns = 3.0
    theta_rad = 2.0 * 3.141592653589793 * theta_turns
    piecewise_length = r0 * theta_rad + (0.002 / 2.0) * theta_rad * theta_rad  # a slope unrelated to k
    mode.cable_state.set_growth_points([(theta_turns, piecewise_length)])

    hw.sample = TelemetrySample(t=1.0, position=theta_turns, velocity=0.0, current_iq=0.0, torque_est=0.0)
    extra = mode.tick(hw, hw.sample)
    assert extra["cable_length_m"] == pytest.approx(piecewise_length)
    linear_length = length_from_turns_delta(theta_turns, r0, mode.cable_state.k)
    assert extra["cable_length_m"] != pytest.approx(linear_length)


# ---- end-to-end via the real ControlSession + mode_factories injection ----

def test_exercise_csv_gains_cable_length_column(tmp_path):
    import csv as csv_module

    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json")
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

    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json")
    cable_state.latch_home(0.0)
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
    float(cell)


def test_exercise_mode_end_to_end_via_control_session(tmp_path):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json")
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


# ==========================================================================
# Layer B: force feedback (formerly ForceMode / test_force_mode.py)
# ==========================================================================

# ---- no torque without explicit engagement ----

def test_construction_and_arm_apply_zero_torque(tmp_path):
    # Merged mode: arm() is the one shared idle state for both Layer A and
    # Layer B, so it puts the hardware in VELOCITY mode at 0 (not TORQUE) --
    # torque mode is only ever entered explicitly, by engage(). Either way
    # the invariant holds: no torque is ever commanded without an explicit
    # engage.
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    assert hw.calls == []
    _arm(mode, hw)
    assert hw.mode == ControlMode.VELOCITY
    assert hw.velocity_target == 0.0
    assert hw.torque_target is None
    assert mode._force_state == ForceState.ARMED


def test_engage_requires_explicit_action(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    extra = mode.tick(hw, _sample(0.0, 0.0, 0.0))
    assert extra["force_state"] == "armed"
    assert extra["commanded_force_n"] == 0.0


def test_engage_requires_homed(tmp_path):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json")
    mode = ExerciseMode(cable_state)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(RuntimeError):
        _engage(mode, hw)


def test_engage_without_max_requires_explicit_end(tmp_path):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json")
    cable_state.latch_home(0.0)
    mode = ExerciseMode(cable_state)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(ValueError):
        _engage(mode, hw)


def test_engage_without_max_succeeds_with_explicit_end(tmp_path):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json")
    cable_state.latch_home(0.0)
    mode = ExerciseMode(cable_state)
    hw = RecordingHardware()
    _arm(mode, hw)
    end_length_m = length_from_turns_delta(10.0, cable_state.r0, cable_state.k)
    _engage(mode, hw, end_length_m=end_length_m)
    assert mode._force_state == ForceState.ENGAGED
    assert mode._range_start_turns == pytest.approx(0.0)
    assert mode._range_end_turns == pytest.approx(10.0 * CABLE_SIGN)


def test_engage_rejected_while_already_engaged(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)
    with pytest.raises(RuntimeError):
        _engage(mode, hw)


# ---- force ramps, never steps ----

def test_force_ramps_in_not_instant(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=100.0, eccentric_force_n=100.0)

    mode.tick(hw, _sample(0.0, 0.0, 0.0))
    extra = mode.tick(hw, _sample(0.02, 0.0, 0.0))
    assert 0.0 < extra["commanded_force_n"] < 100.0


def test_force_ramps_in_reaches_target_eventually(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=100.0, eccentric_force_n=100.0)

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
    _engage(mode, hw, concentric_force_n=100.0, eccentric_force_n=100.0)
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
    assert 0.0 <= extra["commanded_force_n"] < 100.0


# ---- let-go detector: fires during concentric hold-adjacent motion, gated off elsewhere ----

def test_letgo_fires_on_sustained_reel_in_and_hard_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 5)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=100.0, eccentric_force_n=100.0)

    t = 0.0
    extra = None
    reel_in_velocity = -CABLE_SIGN * 0.5  # well past the (lowered, for this test) threshold
    for _ in range(6):
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        extra = mode.tick(hw, hw.sample)

    assert mode._force_state == ForceState.FAULT
    assert extra["force_state"] == "fault"
    assert hw.stop_calls >= 1
    assert hw.torque_target == 0.0
    assert extra["fault_reason"] is not None


def test_letgo_does_not_fire_on_normal_controlled_eccentric_speed(tmp_path):
    # The whole point of raising the default threshold (24 July 2026): a
    # real controlled return must not read as a let-go. Uses the live
    # board_constants default (not monkeypatched down), well above a modest
    # controlled reel-in speed.
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=50.0, eccentric_force_n=20.0)

    t = 0.0
    controlled_reel_in = -CABLE_SIGN * 0.15  # a real, deliberate return -- not a drop
    extra = None
    for _ in range(30):
        t += DT
        hw.sample = _sample(t, 0.0, controlled_reel_in)
        extra = mode.tick(hw, hw.sample)

    assert mode._force_state == ForceState.ENGAGED
    assert extra["phase"] == "eccentric"


def test_letgo_does_not_fire_during_holding(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 3)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)
    mode._force_state = ForceState.HOLDING  # force into HOLDING directly for isolation

    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    extra = None
    for _ in range(10):
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        extra = mode.tick(hw, hw.sample)

    assert mode._force_state == ForceState.HOLDING  # not faulted -- let-go gated off here
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
        mode.tick(hw, hw.sample)
    assert mode._force_state == ForceState.ARMED


def test_letgo_does_not_fire_on_subdebounce_transient(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 5)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=100.0, eccentric_force_n=100.0)

    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    for _ in range(4):  # one short of the debounce window
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        mode.tick(hw, hw.sample)
    assert mode._force_state == ForceState.ENGAGED


# ---- no integrator / no wind-up ----

def test_no_windup_on_sustained_hold_still(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "ISOKINETIC_VELOCITY_TARGET_TURNS_S", 1.0)
    monkeypatch.setattr(board_constants, "ISOKINETIC_GOVERNOR_GAIN", 150.0)
    monkeypatch.setattr(board_constants, "HOLD_DURATION_S", 10_000.0)  # never enter HOLDING for this test
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, mode_name="isokinetic", concentric_force_n=20.0, eccentric_force_n=20.0, velocity_target_turns_s=1.0)

    t = 0.0
    forces = []
    for _ in range(500):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)  # stationary throughout -> BOTTOM_HOLD -> concentric target
        extra = mode.tick(hw, hw.sample)
        forces.append(extra["commanded_force_n"])

    assert forces[-1] == pytest.approx(20.0, abs=1.0)
    assert max(forces[-50:]) - min(forces[-50:]) < 1.0  # flat, not still rising


# ---- sign correctness ----

def test_commanded_torque_opposes_pay_out_during_concentric(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)

    paying_out_velocity = CABLE_SIGN * 0.3  # concentric: paying out
    mode.tick(hw, _sample(0.0, 0.0, paying_out_velocity))
    mode.tick(hw, _sample(0.02, 0.0, paying_out_velocity))

    assert hw.torque_target < 0 if CABLE_SIGN > 0 else hw.torque_target > 0
    assert hw.torque_target != 0.0


def test_commanded_torque_magnitude_matches_force_to_torque(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=50.0, eccentric_force_n=50.0)
    t = 0.0
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        mode.tick(hw, hw.sample)
    assert abs(hw.torque_target) == pytest.approx(force_to_torque(50.0), rel=0.05)


def test_commanded_torque_applies_torque_calibration_inverse_correction(tmp_path, monkeypatch):
    """Items 6/7: the force-feedback torque command must go through the
    calibration's INVERSE correction -- the raw Nm actually sent to
    hardware, not the real/intended torque -- so the physical torque
    delivered matches the calibrated real-world relationship."""
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    r_eff = mode.cable_state.r_eff_at_position(0.0)
    mode.cable_state.add_torque_calibration_point(
        known_weight_kg=5.0, raw_torque_nm=0.9, r_eff_m=r_eff, direction="up"
    )
    assert mode.cable_state.torque_calibration.scale["up"] != pytest.approx(1.0)  # sanity

    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=50.0, eccentric_force_n=50.0)
    # velocity<0 (CABLE_SIGN=1) -> cable_velocity_turns_s<0 -> "up" line,
    # the one just calibrated above. Comfortably below LETGO_VELOCITY_TURNS_S
    # (0.4) so this doesn't trip the let-go detector into FAULT.
    velocity = -CABLE_SIGN * 0.1
    t = 0.0
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 0.0, velocity)
        mode.tick(hw, hw.sample)

    real_torque_nm = force_to_torque(50.0)
    cable_velocity_turns_s = CABLE_SIGN * velocity
    expected_raw = mode.cable_state.raw_torque_nm_for_corrected(real_torque_nm, cable_velocity_turns_s)
    assert abs(hw.torque_target) == pytest.approx(abs(expected_raw), rel=0.05)
    assert abs(hw.torque_target) != pytest.approx(real_torque_nm, rel=0.05)


def test_commanded_torque_uses_cable_state_r0_not_board_constants(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    mode.cable_state.set_r0(0.05)  # different from board_constants.SPOOL_RADIUS_M
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=50.0, eccentric_force_n=50.0)
    t = 0.0
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        mode.tick(hw, hw.sample)
    assert abs(hw.torque_target) == pytest.approx(force_to_torque(50.0, r0=0.05), rel=0.05)
    assert abs(hw.torque_target) != pytest.approx(force_to_torque(50.0), rel=0.05)


# ---- force clamped by F_max ----

def test_force_clamped_at_force_max(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(ValueError):
        _engage(mode, hw, concentric_force_n=board_constants.FORCE_MAX_N + 1.0, eccentric_force_n=1.0)


# ---- force eases off approaching max extension ----

def test_force_tapers_approaching_max_extension(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    monkeypatch.setattr(board_constants, "MAX_EXTENSION_FORCE_TAPER_M", 0.15)
    mode = _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=100.0, eccentric_force_n=100.0)

    t = 0.0
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 5.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    far_force = extra["commanded_force_n"]

    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 20.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    near_force = extra["commanded_force_n"]

    assert far_force > near_force
    assert near_force < 10.0


# ---- configurable start/end sub-range ----

def test_engage_without_range_defaults_to_full_home_to_max(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)
    extra = mode.tick(hw, _sample(DT, 0.0, 0.0))
    assert extra["range_start_length_m"] == pytest.approx(0.0)
    assert extra["range_end_length_m"] == pytest.approx(length_from_turns_delta(20.0, mode.cable_state.r0, mode.cable_state.k))


def test_engage_with_custom_range_converts_lengths_to_turns(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, start_length_m=1.0, end_length_m=2.0)
    extra = mode.tick(hw, _sample(DT, 0.0, 0.0))
    assert extra["range_start_length_m"] == pytest.approx(1.0, abs=1e-6)
    assert extra["range_end_length_m"] == pytest.approx(2.0, abs=1e-6)


def test_engage_rejects_range_start_beyond_calibrated_max(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(ValueError):
        _engage(mode, hw, start_length_m=10.0)


def test_engage_rejects_zero_width_range(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(ValueError):
        _engage(mode, hw, start_length_m=1.0, end_length_m=1.0)


def test_default_range_applies_full_force_at_home_no_start_side_taper(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=50.0, eccentric_force_n=50.0)
    t = 0.0
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)  # right at home the whole time
        extra = mode.tick(hw, hw.sample)
    assert extra["commanded_force_n"] == pytest.approx(50.0, rel=0.05)


def test_custom_range_tapers_at_start_edge(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    monkeypatch.setattr(board_constants, "MAX_EXTENSION_FORCE_TAPER_M", 0.15)
    mode = _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0)
    r0, k = mode.cable_state.r0, mode.cable_state.k
    start_turns = turns_delta_from_length(1.0, r0, k)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=100.0, eccentric_force_n=100.0, start_length_m=1.0)

    moving_velocity = CABLE_SIGN * 0.5  # keep moving concentric so a hold never confounds this
    t = 0.0
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, start_turns, moving_velocity)
        extra = mode.tick(hw, hw.sample)
    at_edge_force = extra["commanded_force_n"]

    well_past_start_turns = turns_delta_from_length(1.0 + 1.0, r0, k)
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, well_past_start_turns, moving_velocity)
        extra = mode.tick(hw, hw.sample)
    past_taper_force = extra["commanded_force_n"]

    assert at_edge_force < 10.0
    assert past_taper_force > at_edge_force
    assert past_taper_force == pytest.approx(100.0, rel=0.05)


def test_custom_range_tapers_at_end_edge(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    monkeypatch.setattr(board_constants, "MAX_EXTENSION_FORCE_TAPER_M", 0.15)
    mode = _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0)
    r0, k = mode.cable_state.r0, mode.cable_state.k
    end_turns = turns_delta_from_length(2.0, r0, k)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=100.0, eccentric_force_n=100.0, end_length_m=2.0)

    moving_velocity = CABLE_SIGN * 0.5
    well_before_end_turns = turns_delta_from_length(1.0, r0, k)
    t = 0.0
    for _ in range(20):
        t += DT
        hw.sample = _sample(t, well_before_end_turns, moving_velocity)
        extra = mode.tick(hw, hw.sample)
    before_end_force = extra["commanded_force_n"]

    for _ in range(20):
        t += DT
        hw.sample = _sample(t, end_turns, moving_velocity)
        extra = mode.tick(hw, hw.sample)
    at_end_force = extra["commanded_force_n"]

    assert before_end_force == pytest.approx(100.0, rel=0.05)
    assert at_end_force < 10.0


def test_update_params_can_change_range_while_engaged(tmp_path, monkeypatch):
    _fast_ramp(monkeypatch)
    monkeypatch.setattr(board_constants, "HOLD_DURATION_S", 10_000.0)
    mode = _homed_and_maxed_mode(tmp_path, home=0.0, max_turns=20.0)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)

    mode.apply_target(hw, mode.validate_target(
        {"action": "update_params", "mode": "constant", "concentric_force_n": 50.0, "eccentric_force_n": 50.0,
         "start_length_m": 0.5, "end_length_m": 3.0}
    ))
    extra = mode.tick(hw, _sample(DT, 0.0, 0.0))
    assert extra["range_start_length_m"] == pytest.approx(0.5, abs=1e-6)
    assert extra["range_end_length_m"] == pytest.approx(3.0, abs=1e-6)


# ---- fault zeroes torque, requires explicit manual resume, resume settles before re-engage ----

def test_resume_moves_to_settling_not_armed(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 3)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)
    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    for _ in range(4):
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        mode.tick(hw, hw.sample)
    assert mode._force_state == ForceState.FAULT

    mode.apply_target(hw, mode.validate_target({"action": "resume"}))
    assert mode._force_state == ForceState.SETTLING
    assert hw.torque_target == 0.0


def test_engage_rejected_while_settling(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 3)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)
    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    for _ in range(4):
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        mode.tick(hw, hw.sample)
    mode.apply_target(hw, mode.validate_target({"action": "resume"}))
    assert mode._force_state == ForceState.SETTLING

    # Still drifting fast (cable free during the fault) -- must not be able
    # to re-engage into an immediate re-fault.
    with pytest.raises(RuntimeError):
        _engage(mode, hw)


def test_settling_transitions_to_armed_once_velocity_settles(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 3)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)
    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    for _ in range(4):
        t += DT
        hw.sample = _sample(t, 0.0, reel_in_velocity)
        mode.tick(hw, hw.sample)
    mode.apply_target(hw, mode.validate_target({"action": "resume"}))
    assert mode._force_state == ForceState.SETTLING

    # Velocity has now settled well below the let-go threshold.
    for _ in range(5):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        mode.tick(hw, hw.sample)
    assert mode._force_state == ForceState.ARMED
    _engage(mode, hw)  # must not raise now
    assert mode._force_state == ForceState.ENGAGED


def test_resume_preserves_force_params_and_leaves_home_max_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "LETGO_VELOCITY_TURNS_S", 0.1)
    monkeypatch.setattr(board_constants, "LETGO_DEBOUNCE_SAMPLES", 3)
    mode = _homed_and_maxed_mode(tmp_path, home=1.0, max_turns=21.0)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=77.0, eccentric_force_n=33.0)
    t = 0.0
    reel_in_velocity = -CABLE_SIGN * 0.5
    for _ in range(4):
        t += DT
        hw.sample = _sample(t, 1.0, reel_in_velocity)
        mode.tick(hw, hw.sample)
    assert mode._force_state == ForceState.FAULT

    mode.apply_target(hw, mode.validate_target({"action": "resume"}))
    assert mode._concentric_force_n == 77.0  # preserved
    assert mode._eccentric_force_n == 33.0
    assert mode.cable_state.home_turns == 1.0
    assert mode.cable_state.max_turns == 21.0


def test_resume_rejected_when_not_faulted(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    with pytest.raises(RuntimeError):
        mode.apply_target(hw, mode.validate_target({"action": "resume"}))


# ---- Stop remains available/effective mid-engagement (end-to-end) ----

def test_global_stop_mid_engaged_zeroes_torque_and_restores_current_limit(tmp_path):
    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json")
    cable_state.latch_home(0.0)
    cable_state.set_max(marked_turns=20.0, enforced_turns=20.0)
    session = ControlSession(
        hardware_source="sim",
        mode_factories={**MODES_BY_NAME, "exercise": lambda: ExerciseMode(cable_state)},
    )
    session.start(mode="exercise", target={"action": "arm"})
    session.set_target({"action": "engage", "mode": "constant", "concentric_force_n": 50.0, "eccentric_force_n": 50.0})
    time.sleep(0.1)
    assert session.status()["running"] is True

    session.stop()
    assert session.status()["running"] is False

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
    _engage(mode, hw)

    t = 0.0
    extra = None
    for _ in range(10):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    assert extra["force_state"] == "holding"


def test_does_not_enter_holding_on_a_brief_pause(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "HOLD_DURATION_S", 1.0)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw)

    t = 0.0
    extra = None
    for _ in range(5):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        extra = mode.tick(hw, hw.sample)
    assert extra["force_state"] == "engaged"


def test_holding_force_settles_at_force_min(tmp_path, monkeypatch):
    monkeypatch.setattr(board_constants, "HOLD_DURATION_S", 0.05)
    _fast_ramp(monkeypatch)
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    _engage(mode, hw, concentric_force_n=100.0, eccentric_force_n=100.0)

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
    _engage(mode, hw)
    t = 0.0
    for _ in range(10):
        t += DT
        hw.sample = _sample(t, 0.0, 0.0)
        mode.tick(hw, hw.sample)

    mode.apply_target(hw, mode.validate_target(
        {"action": "update_params", "mode": "constant", "concentric_force_n": 90.0, "eccentric_force_n": 90.0}
    ))
    assert mode._force_state == ForceState.ENGAGED
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
        mode.apply_target(hw, mode.validate_target(
            {"action": "update_params", "mode": "constant", "concentric_force_n": 50.0, "eccentric_force_n": 50.0}
        ))


# ---- estimated/telemetry fields ----

def test_estimated_force_reflects_measured_torque(tmp_path):
    mode = _homed_and_maxed_mode(tmp_path)
    hw = RecordingHardware()
    _arm(mode, hw)
    hw.sample = _sample(0.0, 0.0, 0.0, current_iq=1.0, torque_est=board_constants.MOTOR_TORQUE_CONSTANT * 1.0)
    extra = mode.tick(hw, hw.sample)
    expected = board_constants.MOTOR_TORQUE_CONSTANT * 1.0 / board_constants.SPOOL_RADIUS_M
    assert extra["estimated_force_n"] == pytest.approx(expected)


def test_estimated_force_applies_torque_calibration_correction(tmp_path):
    """Items 6/7: estimated_force_n must run the raw torque_est through the
    torque calibration's forward correction before converting to force --
    otherwise a recorded calibration would have no effect on what's
    displayed/logged as the measured force."""
    mode = _homed_and_maxed_mode(tmp_path)
    r_eff = mode.cable_state.r_eff_at_position(0.0)
    mode.cable_state.add_torque_calibration_point(
        known_weight_kg=5.0, raw_torque_nm=0.9, r_eff_m=r_eff, direction="up"
    )
    assert mode.cable_state.torque_calibration.scale["up"] != pytest.approx(1.0)  # sanity

    hw = RecordingHardware()
    _arm(mode, hw)
    raw_torque_est = board_constants.MOTOR_TORQUE_CONSTANT * 1.0
    # velocity<0 (CABLE_SIGN=1) -> cable_velocity_turns_s<0 -> "up" line,
    # the one just calibrated above.
    velocity = -CABLE_SIGN * 0.5
    hw.sample = _sample(0.0, 0.0, velocity, current_iq=1.0, torque_est=raw_torque_est)
    extra = mode.tick(hw, hw.sample)

    cable_velocity_turns_s = CABLE_SIGN * velocity
    corrected = mode.cable_state.corrected_torque_nm(raw_torque_est, cable_velocity_turns_s)
    assert corrected != pytest.approx(raw_torque_est)  # sanity: correction changes something
    expected = corrected / board_constants.SPOOL_RADIUS_M
    assert extra["estimated_force_n"] == pytest.approx(expected)


# ---- CSV telemetry ----

def test_force_csv_gains_columns(tmp_path):
    import csv as csv_module

    cable_state = CableState(sidecar_path=tmp_path / "spool_calibration.json", growth_sidecar_path=tmp_path / "spool_growth_calibration.json", torque_calibration_sidecar_path=tmp_path / "torque_calibration.json")
    cable_state.latch_home(0.0)
    cable_state.set_max(marked_turns=20.0, enforced_turns=20.0)
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
    for col in (
        "commanded_force_n", "estimated_force_n", "cable_velocity_m_s",
        "regen_power_w", "force_state", "power_limiter_active",
    ):
        assert col in header
    data_row = rows[1]
    assert data_row[header.index("force_state")] == "armed"
    assert data_row[header.index("commanded_force_n")] == "0.0"


def test_velocity_mode_csv_leaves_force_columns_empty(tmp_path):
    import csv as csv_module

    session = ControlSession(hardware_source="sim")
    session.start(mode="velocity", target=0.3)
    time.sleep(0.1)
    log_path = session.status()["log_path"]
    session.stop()

    with open(log_path, newline="") as f:
        rows = list(csv_module.reader(f))
    header = rows[0]
    data_row = rows[1]
    for col in (
        "commanded_force_n", "estimated_force_n", "cable_velocity_m_s",
        "regen_power_w", "force_state", "power_limiter_active",
    ):
        assert data_row[header.index(col)] == ""
