import pytest

from core.control.modes import MODES_BY_NAME, TorqueMode, VelocityMode
from core.hardware.interface import ControlMode
from core.hardware.sim_hw import SimHardware


def test_velocity_mode_hardware_mode_and_unit():
    m = VelocityMode()
    assert m.hardware_mode == ControlMode.VELOCITY
    assert m.unit == "turns/s"


def test_torque_mode_hardware_mode_and_unit():
    m = TorqueMode()
    assert m.hardware_mode == ControlMode.TORQUE
    assert m.unit == "Nm"


@pytest.mark.parametrize("mode_cls", [VelocityMode, TorqueMode])
def test_validate_target_coerces_numeric(mode_cls):
    m = mode_cls()
    assert m.validate_target(1) == 1.0
    assert isinstance(m.validate_target(1), float)
    assert m.validate_target(-0.5) == -0.5


@pytest.mark.parametrize("mode_cls", [VelocityMode, TorqueMode])
def test_validate_target_rejects_non_numeric(mode_cls):
    m = mode_cls()
    for bad in ["1.0", None, [1.0], True, False]:
        with pytest.raises(TypeError):
            m.validate_target(bad)


def test_apply_target_forwards_to_hardware():
    hw = SimHardware()
    hw.connect()

    VelocityMode().apply_target(hw, 1.5)
    assert hw._velocity_target == 1.5

    TorqueMode().apply_target(hw, 0.3)
    assert hw._torque_target == 0.3


def test_modes_by_name_registry():
    assert MODES_BY_NAME["velocity"] is VelocityMode
    assert MODES_BY_NAME["torque"] is TorqueMode
