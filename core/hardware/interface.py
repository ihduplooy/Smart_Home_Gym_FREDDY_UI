"""Hardware interface contract shared by the real ODrive implementation
(odrive_hw.py) and the dynamic simulated one (sim_hw.py).

Shaped for Session 2 (set-and-forget velocity/torque targets) *and* Session 3
(a profile loop that reads state and writes a torque target every tick) —
state-read + target-write, never raw ODrive property-tree access. Units are
ODrive 0.5.1 native throughout: turns, turns/s, Nm, A. No degrees, no counts,
no cable-linear conversions (that's Session 3's spool-radius layer, not here).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List


class ControlMode(Enum):
    IDLE = "idle"
    VELOCITY = "velocity"
    TORQUE = "torque"


@dataclass
class TelemetrySample:
    t: float  # monotonic seconds
    position: float  # turns
    velocity: float  # turns/s
    current_iq: float  # A
    torque_est: float  # Nm — torque_constant * current_iq
    # TODO(2A): torque_constant (config/board_constants.MOTOR_TORQUE_CONSTANT)
    # is a placeholder pending motor characterisation (open item #2), so
    # torque_est is only as accurate as that constant.


class HardwareInterface(ABC):
    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    def get_state(self) -> TelemetrySample:
        ...

    @abstractmethod
    def set_mode(self, mode: ControlMode) -> None:
        ...

    @abstractmethod
    def set_velocity_target(self, turns_per_s: float) -> None:
        ...

    @abstractmethod
    def set_torque_target(self, nm: float) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        """Set target to 0 and request idle. Must be safe to call at any
        time, from any thread, repeatedly — including when not connected."""
        ...

    @abstractmethod
    def get_errors(self) -> List[str]:
        """Human-readable axis/motor/encoder error flags. Empty list means
        no errors (always true for the sim)."""
        ...
