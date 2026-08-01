"""Dynamic simulated motor — the *dynamics* mock for the Control tab and
Session 3's profile development.

Distinct job from upstream's `mock_odrive.py` (see docs/decisions.md,
Session 2 §5.3): that one is a static property-tree mock for the raw-testing
tabs (Inspector/wizard/console) with no dynamics. This one has no property
tree at all — it implements HardwareInterface directly and actually moves.

Model: accel = (torque_cmd - b*velocity) / J, plain Euler integration at
whatever rate get_state() is called (telemetry loop rate, ~50 Hz target).
J/b are placeholders (open item #2, pending motor characterisation) chosen so
a 1 Nm command settles near its terminal velocity in about a second — see
docs/decisions.md for the reasoning. No noise, no load model, no cable
dynamics; do not gold-plate this.
"""

import time
from typing import List

from config import board_constants

from .interface import ControlMode, HardwareInterface, TelemetrySample

# Placeholders pending motor characterisation (open item #2). Tuned by eye so
# a 1 Nm step settles near steady state (v = 1/B turns/s) in ~1s (tau = J/B).
SIM_INERTIA_J = 0.15  # kg*m^2-equivalent
SIM_DAMPING_B = 0.5  # Nm / (turn/s)

# Sim-only velocity-mode proportional gain (Nm per turn/s of error). Doesn't
# need tuning finesse — ODrive's real closed loops do the work on hardware.
SIM_VELOCITY_KP = 2.0

# Sim-only position-mode outer loop (turns/s of velocity setpoint per turn of
# position error), capped at the caller's move_velocity — a cheap stand-in
# for ODrive's real trap_traj planner. Not trying to reproduce the real
# trapezoidal accel/cruise/decel shape, just "approaches then holds," which
# is all the sim needs to exercise PositionMode end-to-end.
SIM_POSITION_KP = 2.0


class SimHardware(HardwareInterface):
    def __init__(self):
        self._connected = False
        self._mode = ControlMode.IDLE
        self._velocity_target = 0.0
        self._torque_target = 0.0
        self._position_target = 0.0
        self._position_move_velocity = 0.0
        self._position = 0.0
        self._velocity = 0.0
        self._last_applied_torque = 0.0
        self._last_t = None
        self._current_limit_a = board_constants.MOTOR_CURRENT_LIM

    def connect(self) -> None:
        self._connected = True
        self._last_t = time.monotonic()

    def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _commanded_torque(self) -> float:
        if self._mode == ControlMode.TORQUE:
            return self._torque_target
        if self._mode == ControlMode.VELOCITY:
            return SIM_VELOCITY_KP * (self._velocity_target - self._velocity)
        if self._mode == ControlMode.POSITION:
            pos_error = self._position_target - self._position
            vel_setpoint = SIM_POSITION_KP * pos_error
            limit = self._position_move_velocity
            vel_setpoint = max(-limit, min(limit, vel_setpoint))
            return SIM_VELOCITY_KP * (vel_setpoint - self._velocity)
        return 0.0

    def _integrate(self) -> None:
        now = time.monotonic()
        if self._last_t is None:
            self._last_t = now
            return
        dt = now - self._last_t
        self._last_t = now
        if dt <= 0:
            return
        torque_cmd = self._commanded_torque()
        accel = (torque_cmd - SIM_DAMPING_B * self._velocity) / SIM_INERTIA_J
        self._velocity += accel * dt
        self._position += self._velocity * dt
        self._last_applied_torque = torque_cmd

    def get_state(self) -> TelemetrySample:
        self._integrate()
        current_iq = self._last_applied_torque / board_constants.MOTOR_TORQUE_CONSTANT
        torque_est = board_constants.MOTOR_TORQUE_CONSTANT * current_iq
        return TelemetrySample(
            t=time.monotonic(),
            position=self._position,
            velocity=self._velocity,
            current_iq=current_iq,
            torque_est=torque_est,
            bus_voltage_v=board_constants.SIM_BUS_VOLTAGE_V,
        )

    def set_mode(self, mode: ControlMode) -> None:
        self._mode = mode

    def set_velocity_target(self, turns_per_s: float) -> None:
        self._velocity_target = turns_per_s

    def set_torque_target(self, nm: float) -> None:
        self._torque_target = nm

    def set_position_target(
        self,
        turns: float,
        move_velocity: float,
        accel_decel: float,  # unused by the sim's simplified P-loop model — see SIM_POSITION_KP
        torque_limit: float = None,  # unused: the sim's torque isn't limited, matching TorqueMode's sim behaviour
    ) -> None:
        self._position_target = turns
        self._position_move_velocity = abs(move_velocity)

    def set_current_limit(self, amps: float) -> None:
        # Stored for interface conformance/test assertions only. Deliberately
        # not fed into _commanded_torque()'s dynamics: the sim's TorqueMode
        # is already documented as unclamped, matching real hardware's
        # current-limit-derived clamp only loosely (core/control/modes.py's
        # ProfileMode docstring) -- adding a second clamp here for this one
        # caller would be new sim behavior nothing else expects, not
        # something Layer A actually needs (the real safety guarantee this
        # exists for only matters against real hardware).
        self._current_limit_a = amps

    def stop(self) -> None:
        self._velocity_target = 0.0
        self._torque_target = 0.0
        self._position_target = self._position
        self._position_move_velocity = 0.0
        self._mode = ControlMode.IDLE

    def get_errors(self) -> List[str]:
        return []
