import pytest

from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.hardware.odrive_hw import OdriveHardware
from core.hardware.sim_hw import SimHardware


def test_abc_cannot_be_instantiated():
    with pytest.raises(TypeError):
        HardwareInterface()


@pytest.mark.parametrize("cls", [SimHardware, OdriveHardware])
def test_implementations_satisfy_the_contract(cls):
    """Both implementations are concrete subclasses with every abstract
    method overridden, and neither imports the real `odrive` package (or
    touches hardware) merely by being constructed."""
    instance = cls()
    assert isinstance(instance, HardwareInterface)
    assert instance.is_connected is False


def test_sim_is_connected_after_connect():
    hw = SimHardware()
    hw.connect()
    assert hw.is_connected is True
    hw.disconnect()
    assert hw.is_connected is False


def test_sim_get_state_returns_telemetry_sample():
    hw = SimHardware()
    hw.connect()
    sample = hw.get_state()
    assert isinstance(sample, TelemetrySample)
    assert sample.position == 0.0
    assert sample.velocity == 0.0


def test_sim_errors_always_empty():
    hw = SimHardware()
    hw.connect()
    assert hw.get_errors() == []


def test_odrive_hw_stop_is_safe_before_connect():
    """stop() must be safe to call at any time, including before connect()."""
    hw = OdriveHardware()
    hw.stop()  # must not raise
    assert hw.get_errors() == []


def test_sim_set_current_limit_is_stored():
    hw = SimHardware()
    hw.connect()
    hw.set_current_limit(3.0)
    assert hw._current_limit_a == 3.0


def test_odrive_hw_set_current_limit_requires_connection():
    hw = OdriveHardware()
    with pytest.raises(RuntimeError):
        hw.set_current_limit(3.0)
