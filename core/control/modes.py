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
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles import PhaseDetector, ProfileState, RepCounter, ResistanceProfile


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
    "profile": ProfileMode,
}
