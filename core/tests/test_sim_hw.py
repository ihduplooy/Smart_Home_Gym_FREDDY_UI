import time

from core.hardware.interface import ControlMode
from core.hardware.sim_hw import SimHardware


def test_positive_torque_makes_velocity_rise():
    hw = SimHardware()
    hw.connect()
    hw.set_mode(ControlMode.TORQUE)
    hw.set_torque_target(1.0)

    hw.get_state()  # prime last_t
    time.sleep(0.05)
    v1 = hw.get_state().velocity
    time.sleep(0.05)
    v2 = hw.get_state().velocity

    assert v1 > 0.0
    assert v2 > v1


def test_stop_zeroes_targets_and_idles():
    hw = SimHardware()
    hw.connect()
    hw.set_mode(ControlMode.TORQUE)
    hw.set_torque_target(1.0)
    hw.get_state()
    time.sleep(0.05)
    moving_velocity = hw.get_state().velocity
    assert moving_velocity > 0.0

    hw.stop()
    assert hw._mode == ControlMode.IDLE
    assert hw._velocity_target == 0.0
    assert hw._torque_target == 0.0

    # With mode idle, damping should now be pulling velocity back toward 0,
    # not pushing it further away.
    hw.get_state()
    time.sleep(0.05)
    v_after_stop_1 = hw.get_state().velocity
    time.sleep(0.05)
    v_after_stop_2 = hw.get_state().velocity
    assert v_after_stop_2 < v_after_stop_1


def test_velocity_mode_converges_toward_target():
    hw = SimHardware()
    hw.connect()
    hw.set_mode(ControlMode.VELOCITY)
    hw.set_velocity_target(1.0)

    hw.get_state()
    last = 0.0
    for _ in range(20):
        time.sleep(0.02)
        sample = hw.get_state()
        assert sample.velocity >= last - 1e-9  # monotonically approaching target
        last = sample.velocity

    assert 0.0 < last <= 1.0 + 1e-6


def test_torque_est_round_trips_from_current_iq():
    from config import board_constants

    hw = SimHardware()
    hw.connect()
    hw.set_mode(ControlMode.TORQUE)
    hw.set_torque_target(0.5)
    hw.get_state()
    time.sleep(0.05)
    sample = hw.get_state()
    assert sample.torque_est == board_constants.MOTOR_TORQUE_CONSTANT * sample.current_iq
