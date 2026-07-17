"""Control modes: thin classes that know which HardwareInterface mode to
request and validate/forward their target type.

Session 2's modes are set-and-forget — ODrive's native closed loops (real or
simulated) do the work; there's no outer control loop here. Kept as classes
anyway so Session 3's profile layer can slot in as a third mode that *does*
run an outer loop (reading state, computing torque, calling
set_torque_target every tick) without changing ControlSession's API.
"""

from abc import ABC, abstractmethod

from core.hardware.interface import ControlMode, HardwareInterface


class BaseMode(ABC):
    hardware_mode: ControlMode
    unit: str

    @abstractmethod
    def validate_target(self, value) -> float:
        """Return `value` coerced to float, or raise ValueError/TypeError."""
        ...

    @abstractmethod
    def apply_target(self, hardware: HardwareInterface, value: float) -> None:
        ...


class VelocityMode(BaseMode):
    hardware_mode = ControlMode.VELOCITY
    unit = "turns/s"

    def validate_target(self, value) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"Velocity target must be numeric, got {value!r}")
        return float(value)

    def apply_target(self, hardware: HardwareInterface, value: float) -> None:
        hardware.set_velocity_target(value)


class TorqueMode(BaseMode):
    # TODO(2A): ODrive's enable_torque_mode_vel_limit may fight a profile
    # layer doing its own velocity-dependent control (open item #8) — becomes
    # live the moment this meets real hardware.
    hardware_mode = ControlMode.TORQUE
    unit = "Nm"

    def validate_target(self, value) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"Torque target must be numeric, got {value!r}")
        return float(value)

    def apply_target(self, hardware: HardwareInterface, value: float) -> None:
        hardware.set_torque_target(value)


MODES_BY_NAME = {
    "velocity": VelocityMode,
    "torque": TorqueMode,
}
