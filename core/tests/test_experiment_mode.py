"""core/experiments/mode.py tests. Same RecordingHardware-fake style as
core/tests/test_train_mode.py -- faster and more precise than round-tripping
through ControlSession's thread.
"""

from typing import List

import pytest

from core.cable.geometry import turns_delta_from_length
from core.cable.state import CableState
from core.experiments.base import ExperimentState
from core.experiments.mode import ExperimentMode
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample


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


def _sample(t, position=0.0, velocity=0.0):
    return TelemetrySample(t=t, position=position, velocity=velocity, current_iq=0.0, torque_est=0.0)


def _homed_cable_state(tmp_path, home=0.0, max_turns=10.0):
    cs = CableState(sidecar_path=tmp_path / "s.json", growth_sidecar_path=tmp_path / "g.json")
    cs.latch_home(home)
    cs.set_max(marked_turns=max_turns, enforced_turns=max_turns)
    return cs


def _config_dict(**overrides):
    base = dict(
        known_weight_kg=1.0,
        initial_position_m=0.0,
        target_position_m=1.0,
        initial_torque_nm=0.1,
        torque_ramp_rate_nm_per_s=0.05,
        movement_threshold_m_per_s=0.01,
        hold_deadband_m=0.005,
        hold_gain=5.0,
        max_torque_nm=2.0,
        max_duration_s=60.0,
    )
    base.update(overrides)
    return base


class TestValidateTarget:
    def test_unknown_action_rejected(self, tmp_path):
        mode = ExperimentMode(_homed_cable_state(tmp_path))
        with pytest.raises(ValueError):
            mode.validate_target({"action": "bogus"})

    def test_unknown_experiment_rejected(self, tmp_path):
        mode = ExperimentMode(_homed_cable_state(tmp_path))
        with pytest.raises(ValueError):
            mode.validate_target({"action": "configure", "experiment": "nope", "config": _config_dict()})

    def test_configure_missing_field_rejected(self, tmp_path):
        mode = ExperimentMode(_homed_cable_state(tmp_path))
        bad_config = _config_dict()
        del bad_config["max_torque_nm"]
        with pytest.raises(ValueError):
            mode.validate_target({"action": "configure", "experiment": "static_hold", "config": bad_config})


class TestApplyTargetAndTick:
    def test_configure_does_not_energize_motor(self, tmp_path):
        cable_state = _homed_cable_state(tmp_path)
        mode = ExperimentMode(cable_state)
        hw = RecordingHardware()
        value = mode.validate_target({"action": "configure", "experiment": "static_hold", "config": _config_dict()})
        mode.apply_target(hw, value)

        assert hw.torque_target == 0.0
        assert mode.experiment.state == ExperimentState.CONFIGURED

        extra = mode.tick(hw, _sample(t=0.0))
        assert extra["experiment_state"] == "configured"
        assert hw.torque_target == 0.0  # still not energized

    def test_confirm_start_before_configure_raises(self, tmp_path):
        mode = ExperimentMode(_homed_cable_state(tmp_path))
        hw = RecordingHardware()
        value = mode.validate_target({"action": "confirm_start"})
        with pytest.raises(RuntimeError):
            mode.apply_target(hw, value)

    def test_full_cycle_ramping_lifting_holding(self, tmp_path):
        cable_state = _homed_cable_state(tmp_path)
        mode = ExperimentMode(cable_state)
        hw = RecordingHardware()

        configure_value = mode.validate_target(
            {"action": "configure", "experiment": "static_hold", "config": _config_dict()}
        )
        mode.apply_target(hw, configure_value)

        confirm_value = mode.validate_target({"action": "confirm_start"})
        mode.apply_target(hw, confirm_value)
        assert mode.experiment.state == ExperimentState.RAMPING

        hw.sample = _sample(t=0.0, position=0.0, velocity=0.0)
        extra = mode.tick(hw, hw.sample)
        assert extra["experiment_state"] == "ramping"
        assert hw.torque_target == pytest.approx(0.1)

        # Movement threshold tripped -> LIFTING, torque frozen.
        hw.sample = _sample(t=1.0, position=0.0, velocity=0.06)
        extra = mode.tick(hw, hw.sample)
        assert extra["experiment_state"] == "lifting"
        frozen_torque = hw.torque_target
        assert frozen_torque == pytest.approx(0.1 + 0.05 * 1.0)

        # Reach target -> HOLDING.
        target_turns = turns_delta_from_length(1.0, cable_state.r0, cable_state.k)
        hw.sample = _sample(t=2.0, position=target_turns, velocity=0.0)
        extra = mode.tick(hw, hw.sample)
        assert extra["experiment_state"] == "holding"
        assert extra["commanded_torque_nm"] == pytest.approx(frozen_torque)
        assert "bus_voltage_v" in extra
        assert "estimated_power_w" in extra

    def test_max_torque_breach_stops_hardware_same_tick(self, tmp_path):
        cable_state = _homed_cable_state(tmp_path)
        mode = ExperimentMode(cable_state)
        hw = RecordingHardware()

        config = _config_dict(
            initial_torque_nm=0.1,
            torque_ramp_rate_nm_per_s=0.5,
            movement_threshold_m_per_s=100.0,
            max_torque_nm=0.2,
        )
        mode.apply_target(hw, mode.validate_target({"action": "configure", "experiment": "static_hold", "config": config}))
        mode.apply_target(hw, mode.validate_target({"action": "confirm_start"}))

        # First tick establishes t0 (elapsed=0 there); a later tick's
        # elapsed-since-t0 is what needs to breach max_torque_nm.
        hw.sample = _sample(t=10.0, position=0.0, velocity=0.0)
        mode.tick(hw, hw.sample)
        hw.sample = _sample(t=10.3, position=0.0, velocity=0.0)
        extra = mode.tick(hw, hw.sample)

        assert extra["experiment_state"] == "aborted"
        assert hw.stop_calls == 1  # immediate, same-tick safe shutdown
        assert hw.torque_target == 0.0

    def test_csv_log_name_includes_experiment_name(self, tmp_path):
        cable_state = _homed_cable_state(tmp_path)
        mode = ExperimentMode(cable_state)
        hw = RecordingHardware()
        mode.apply_target(
            hw, mode.validate_target({"action": "configure", "experiment": "static_hold", "config": _config_dict()})
        )
        assert mode.csv_log_name("experiment") == "experiment-static_hold"
