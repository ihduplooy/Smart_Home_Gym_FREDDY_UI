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
    POSITION = "position"


@dataclass
class TelemetrySample:
    t: float  # monotonic seconds
    position: float  # turns
    velocity: float  # turns/s
    current_iq: float  # A — phase current (Iq_measured), not bus current
    torque_est: float  # Nm — torque_constant * current_iq
    # TODO(2A): torque_constant (config/board_constants.MOTOR_TORQUE_CONSTANT)
    # is a placeholder pending motor characterisation (open item #2), so
    # torque_est is only as accurate as that constant.
    # Testing tab (Testing tab Build Spec §3): added for the Testing tab's
    # power-draw telemetry channel. Defaulted so the many existing
    # TelemetrySample(...) construction call sites across core/tests/ (built
    # before this field existed) don't need updating.
    bus_voltage_v: float = 0.0  # V — odrv0.vbus_voltage (real); fixed placeholder (sim)


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
    def set_position_target(
        self,
        turns: float,
        move_velocity: float,
        accel_decel: float,
        torque_limit: float = None,
    ) -> None:
        """Command a trapezoidal move to an *absolute* position (turns), at
        the given cruise velocity (turns/s) and accel/decel rate (turns/s^2,
        applied symmetrically to both). PositionMode (core/control/modes.py)
        is responsible for turning a user-facing *relative* move into this
        absolute target — this layer only ever deals in absolute positions,
        matching every other HardwareInterface method. `torque_limit`, if
        given, overrides the currently configured torque limit for the
        move (None leaves whatever's already configured untouched)."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Set target to 0 and request idle. Must be safe to call at any
        time, from any thread, repeatedly — including when not connected."""
        ...

    @abstractmethod
    def set_current_limit(self, amps: float) -> None:
        """Live current limit (A) — added for the Exercise tab's homing mode
        (exercise_tab_build_spec_layerA.md §3.1/§4 item 4), which needs to
        temporarily lower this below the board's normal operating limit
        during a blind reel-in, then restore it. Unlike set_velocity_target/
        set_torque_target this isn't a per-tick control target — callers set
        it once before a homing run and once again to restore it. See
        odrive_hw.py's connect() for the reassert-on-connect backstop that
        guarantees a skipped restore (e.g. an abort mid-homing that tears
        the session down before cleanup runs) can never leak a lowered limit
        into a later session."""
        ...

    @abstractmethod
    def get_errors(self) -> List[str]:
        """Human-readable axis/motor/encoder error flags. Empty list means
        no errors (always true for the sim)."""
        ...
