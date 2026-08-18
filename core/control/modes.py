"""Control modes: thin classes that know which HardwareInterface mode to
request and validate/forward their target type.

Session 2's modes are set-and-forget — ODrive's native closed loops (real or
simulated) do the work; there's no outer control loop here. Kept as classes
anyway so Session 3's profile layer can slot in as a third mode that *does*
run an outer loop (reading state, computing torque, calling
set_torque_target every tick) without changing ControlSession's API.

Session 3 adds three extension-point hooks to BaseMode (all concrete,
default no-ops/identity) so ControlSession's tick loop and start()/set_target()
stay fully generic across Velocity/Torque/Profile without isinstance checks:
  - tick(hardware, sample): per-tick outer-loop hook. Velocity/Torque are
    set-and-forget (no-op); ProfileMode overrides it to run the phase
    detector + rep counter + compute_torque + set_torque_target every tick.
  - csv_log_name(mode): filename/column mode-name override (identity by
    default; ProfileMode appends the active profile's name).
  - status_target(validated_value): JSON/CSV-safe representation of the
    currently active target (identity by default; ProfileMode reports the
    profile's current primary parameter instead of the raw profile object).

Control-tab telemetry (mirrors train_tab_build_spec.md's TrainMode amendment
-- see core/cable/train_mode.py's own tick() comment for the fuller
rationale): Velocity/Torque/Position all optionally take the shared
`CableState` singleton (backend/app/control_routes.py's `mode_factories`
overrides inject it, same "exercise"/"train" precedent) and, when given one,
fill the same sensor-derived CSV columns Train/Exercise do --
bus_voltage_v/estimated_power_w/estimated_force_n/cable_velocity_m_s/
cable_length_m/regen_power_w -- purely informational, never clamped
(power_limiter_active always False; nothing here changes what gets commanded
to the hardware). `cable_state` defaults to None so bare VelocityMode()/
TorqueMode()/PositionMode() construction (core/tests/test_modes.py, and
MODES_BY_NAME's own bare-class factories below) keeps working unchanged --
tick() just returns {} in that case, same as BaseMode's own default.
PositionMode additionally aliases cable_length_m/cable_velocity_m_s into
position_m/velocity_m_s and derives target_position_m from its own move
target -- the Testing tab drives this same "position" mode directly
(frontend/src/hooks/useTestingTelemetry.js's header comment) and already
computes those exact three fields client-side for its chart; this is that
same math, finally landing in the CSV instead of only ever existing in the
browser tab's memory.

`core.cable`'s geometry/power_limiter helpers are imported lazily inside
_cable_extra() below rather than at module level: core/cable/__init__.py
eagerly imports ExerciseMode/TrainMode, which import BaseMode from *this*
module, so a top-level `from core.cable... import ...` here would be a real
import cycle (core.control.modes -> core.cable -> core.control.modes,
mid-initialization) the first time anything imports this module before
core.cable has already been loaded. Deferring the import to call time sidesteps
it entirely -- by the time any tick() actually runs, the whole app has long
since finished importing both packages in whatever order backend/app/
control_routes.py (or a test) started with.
"""

import math
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from config import board_constants
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles import PhaseDetector, ProfileState, RepCounter, ResistanceProfile
from core.profiles.detectors import CABLE_SIGN
from core.profiles.units import torque_to_force


def _cable_extra(cable_state, sample: TelemetrySample) -> Dict[str, Any]:
    """Sensor-derived cable telemetry shared by Velocity/Torque/PositionMode
    below -- same formulas core/cable/train_mode.py's tick() uses (r_eff_at_
    position()/corrected_torque_nm() are CableState's shared home for the
    force<->torque conversion, per its own docstring), just factored out
    once here since three classes in this file need the identical
    computation rather than TrainMode/ExerciseMode's one-off need each."""
    if cable_state is None:
        return {}
    from core.cable.geometry import speed_m_s_from_turns_s
    from core.cable.power_limiter import estimate_regen_power_w

    estimated_force_n = torque_to_force(
        cable_state.corrected_torque_nm(sample.torque_est),
        r0=cable_state.r_eff_at_position(sample.position),
    )
    cable_velocity_m_s = speed_m_s_from_turns_s(CABLE_SIGN * sample.velocity, cable_state.r0)
    extra: Dict[str, Any] = {
        "bus_voltage_v": sample.bus_voltage_v,
        "estimated_power_w": sample.torque_est * sample.velocity * 2.0 * math.pi,
        "estimated_force_n": estimated_force_n,
        "cable_velocity_m_s": cable_velocity_m_s,
        "cable_length_m": None,
        # Informational only, same as TrainMode's own regen_power_w -- based
        # on the *estimated* (measured) force here rather than a commanded
        # one, since Velocity/Torque/Position don't command a target force
        # at all (there's nothing analogous to Train's profile/Exercise's
        # force-feedback target to base it on instead).
        "regen_power_w": estimate_regen_power_w(
            estimated_force_n,
            cable_velocity_m_s,
            board_constants.MOTOR_TORQUE_CONSTANT,
            board_constants.MOTOR_PHASE_RESISTANCE_OHM,
            cable_state.r0,
        ),
        "power_limiter_active": False,
    }
    if cable_state.is_homed:
        extra["cable_length_m"] = cable_state.spool_geometry.length_from_turns_delta(
            sample.position - cable_state.home_turns
        )
    return extra


class BaseMode(ABC):
    hardware_mode: ControlMode
    unit: str

    @abstractmethod
    def validate_target(self, value) -> float:
        """Return `value` coerced to float, or raise ValueError/TypeError."""
        ...

    @abstractmethod
    def apply_target(self, hardware: HardwareInterface, value) -> None:
        ...

    def tick(self, hardware: HardwareInterface, sample: TelemetrySample) -> Dict[str, Any]:
        """Per-tick outer-loop hook, called once per telemetry tick after
        `sample` is read. Default: no-op (Velocity/Torque are set-and-forget
        — the target was already applied once by apply_target()). Returns
        extra fields (e.g. phase/rep_count) to fold into status()/CSV rows."""
        return {}

    def csv_log_name(self, mode: str) -> str:
        """CSV filename/mode-column override. Default: identity."""
        return mode

    def status_target(self, validated_value):
        """JSON/CSV-safe representation of the currently active target.
        Default: identity (already a plain float for Velocity/Torque)."""
        return validated_value


class VelocityMode(BaseMode):
    hardware_mode = ControlMode.VELOCITY
    unit = "turns/s"

    def __init__(self, cable_state=None):
        self.cable_state = cable_state

    def validate_target(self, value) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"Velocity target must be numeric, got {value!r}")
        return float(value)

    def apply_target(self, hardware: HardwareInterface, value: float) -> None:
        hardware.set_velocity_target(value)

    def tick(self, hardware: HardwareInterface, sample: TelemetrySample) -> Dict[str, Any]:
        return _cable_extra(self.cable_state, sample)


class TorqueMode(BaseMode):
    # TODO(2A): ODrive's enable_torque_mode_vel_limit may fight a profile
    # layer doing its own velocity-dependent control (open item #8) — becomes
    # live the moment this meets real hardware.
    hardware_mode = ControlMode.TORQUE
    unit = "Nm"

    def __init__(self, cable_state=None):
        self.cable_state = cable_state

    def validate_target(self, value) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"Torque target must be numeric, got {value!r}")
        return float(value)

    def apply_target(self, hardware: HardwareInterface, value: float) -> None:
        hardware.set_torque_target(value)

    def tick(self, hardware: HardwareInterface, sample: TelemetrySample) -> Dict[str, Any]:
        return _cable_extra(self.cable_state, sample)


class PositionMode(BaseMode):
    """Trapezoidal position moves. Unlike Velocity/Torque, the target is a
    small dict, not a bare float — {"position", "move_velocity",
    "accel_decel", "torque_limit"?} — since a move needs more than just a
    destination (see HardwareInterface.set_position_target's docstring for
    what each maps to on the hardware).

    "position" is a *relative* move (spec: how far to move from wherever the
    axis is right now), resolved to an absolute target fresh on every
    apply_target() call — both the initial start() and any later
    set_target() retarget — by reading the hardware's current position at
    that moment. This mode intentionally does not fight ODrive's own
    closed-loop hold once the move completes: entering position control +
    reaching the target is *itself* what holds it there, no extra code
    needed here.
    """

    hardware_mode = ControlMode.POSITION
    unit = "turns"

    def __init__(self, cable_state=None):
        self._last_absolute_target = None
        self.cable_state = cable_state

    def validate_target(self, value) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError(f"Position target must be a dict, got {value!r}")

        def _num(key, required=True, default=None):
            v = value.get(key, default)
            if v is None:
                if required:
                    raise ValueError(f"Position target missing required field '{key}'")
                return None
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise TypeError(f"Position target field '{key}' must be numeric, got {v!r}")
            return float(v)

        position = _num("position")
        move_velocity = _num("move_velocity")
        if move_velocity <= 0:
            raise ValueError(f"move_velocity must be positive, got {move_velocity!r}")
        accel_decel = _num("accel_decel")
        if accel_decel <= 0:
            raise ValueError(f"accel_decel must be positive, got {accel_decel!r}")
        torque_limit = _num("torque_limit", required=False)
        if torque_limit is not None and torque_limit < 0:
            raise ValueError(f"torque_limit must be non-negative, got {torque_limit!r}")

        return {
            "position": position,
            "move_velocity": move_velocity,
            "accel_decel": accel_decel,
            "torque_limit": torque_limit,
        }

    def apply_target(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        current_position = hardware.get_state().position
        absolute = current_position + value["position"]
        self._last_absolute_target = absolute
        hardware.set_position_target(
            absolute,
            move_velocity=value["move_velocity"],
            accel_decel=value["accel_decel"],
            torque_limit=value["torque_limit"],
        )

    def status_target(self, validated_value: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "position": self._last_absolute_target,
            "move_velocity": validated_value["move_velocity"],
            "accel_decel": validated_value["accel_decel"],
            "torque_limit": validated_value["torque_limit"],
        }

    def tick(self, hardware: HardwareInterface, sample: TelemetrySample) -> Dict[str, Any]:
        extra = _cable_extra(self.cable_state, sample)
        # The Testing tab drives this same mode directly (see module
        # docstring) and already names these fields position_m/velocity_m_s/
        # target_position_m for its own chart -- aliased here from the
        # cable_length_m/cable_velocity_m_s _cable_extra() already computed,
        # rather than recomputing the same conversion twice.
        extra["position_m"] = extra.get("cable_length_m")
        extra["velocity_m_s"] = extra.get("cable_velocity_m_s")
        extra["target_position_m"] = None
        if (
            self.cable_state is not None
            and self.cable_state.is_homed
            and self._last_absolute_target is not None
        ):
            extra["target_position_m"] = self.cable_state.spool_geometry.length_from_turns_delta(
                self._last_absolute_target - self.cable_state.home_turns
            )
        return extra


class ProfileMode(BaseMode):
    """Resistance profiles run as a third mode inside the existing 50 Hz
    ControlSession loop, not a new thread (spec §3 — the one real
    architectural decision this session makes). Hardware mode is TORQUE:
    profiles are an outer loop around ODrive's inner torque loop (master
    plan §9.3).

    # TODO(2A): enable_torque_mode_vel_limit (open item #8, also flagged on
    # TorqueMode) is *directly* load-bearing here — it can fight this mode's
    # own velocity-dependent torque commands as velocity rises. Still a 2A
    # decision pending real hardware.

    `validate_target`/`apply_target` do double duty by design (spec §3):
    called once at start() with a `ResistanceProfile` instance (the "target"
    the mode carries), and again on every `set_target()` retarget with a
    plain float (the profile's primary parameter — see
    ResistanceProfile.set_primary_parameter). The profile object itself is
    never replaced mid-run, only adjusted in place.
    """

    hardware_mode = ControlMode.TORQUE
    unit = "profile"

    def __init__(self):
        self.profile = None
        self.phase_detector = PhaseDetector()
        self.rep_counter = RepCounter()

    def validate_target(self, value):
        if isinstance(value, ResistanceProfile):
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"Profile target must be a ResistanceProfile (at start) or numeric "
                f"(on retarget), got {value!r}"
            )
        return float(value)

    def apply_target(self, hardware: HardwareInterface, value) -> None:
        if isinstance(value, ResistanceProfile):
            self.profile = value
            self.profile.reset()
            self.phase_detector.reset()
            self.rep_counter.reset()
            hardware.set_torque_target(0.0)
            return
        if self.profile is None:
            raise RuntimeError("ProfileMode has no active profile to retarget")
        self.profile.set_primary_parameter(value)

    def tick(self, hardware: HardwareInterface, sample: TelemetrySample) -> Dict[str, Any]:
        if self.profile is None:
            return {}

        phase = self.phase_detector.update(sample.velocity)
        rep_count = self.rep_counter.update(sample.position, phase)
        state = ProfileState(
            t=sample.t,
            position=sample.position,
            velocity=sample.velocity,
            phase=phase,
            rep_count=rep_count,
            sample=sample,
        )
        # STUB(2A+): torque write below reuses hardware.set_torque_target()
        # unmodified -- the same clamp path Session 2's TorqueMode already
        # goes through (real hardware clamps to the current-limit-derived
        # torque bound; the sim doesn't clamp, matching its existing
        # torque-mode behaviour). No second clamp added here.
        torque = self.profile.compute_torque(state)
        hardware.set_torque_target(torque)
        return {"phase": phase.value, "rep_count": rep_count}

    def csv_log_name(self, mode: str) -> str:
        name = self.profile.name if self.profile is not None else "unknown"
        return f"{mode}-{name}"

    def status_target(self, validated_value):
        if self.profile is None:
            return None
        return self.profile.get_primary_parameter()


MODES_BY_NAME = {
    "velocity": VelocityMode,
    "torque": TorqueMode,
    "position": PositionMode,
    "profile": ProfileMode,
}
