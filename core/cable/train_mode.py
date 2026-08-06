"""TrainMode — the Train tab's control mode (train_tab_build_spec.md §2).

Fixed to torque control for its lifecycle, same as the old ForceMode/current
ExerciseMode force-feedback side, but deliberately *without* any governor,
ramp, hold-detector, or let-go machinery: every tick it reads cable position,
evaluates the active `train_profiles.TrainProfile` segment, converts to
torque via the existing `core.profiles.units.force_to_torque()`, and commands
it directly. Wherever the cable is, that's the torque, same in both
directions — no phase detection, no rep counting (spec §4). That simplicity
is the point; resist the urge to add ramping/hysteresis here even though
`ExerciseMode` next door has it for a different feature.

Two actions, dispatched the same `_apply_<action>` way `ExerciseMode` already
does (spec §0's "confirm against the real code" turned up this convention,
worth reusing rather than inventing a second dispatch shape):
  - "run": (re)sets the active TrainProfile at session start. The only
    action start() ever receives.
  - "set_profile": a later retarget while the session is live (profile
    editor's "Apply" button).

Manual jogging used to be a third action here (a bounded trapezoidal
position move) but was removed 25 July 2026 at the user's request — it
coupled to "Start Train session" in a way that didn't make sense, and the
Control tab's own Position mode already covers manual moves better (PI
tuning, velocity control). See docs/decisions.md ("Train tab refinements").
TrainMode is single-state again as a result: no more "running"/"moving"
distinction, tick() always evaluates the profile.

Registered as a `mode_factories` override in backend/app/control_routes.py
(`"train": lambda: TrainMode(cable_state)`), sharing the same `CableState`
singleton Exercise/Force already use — same pattern, not `MODES_BY_NAME`
itself (see decisions.md; "exercise" was never added there either).
"""

import logging
from typing import Any, Dict

from config import board_constants
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles.detectors import CABLE_SIGN
from core.profiles.units import force_to_torque

from ..control.modes import BaseMode
from .limits import check_runtime_guard_split, validate_homed
from .state import CableState
from .train_profiles import TrainProfile

log = logging.getLogger(__name__)

_VALID_ACTIONS = frozenset({"run", "set_profile"})


def _coerce_profile(value: Any) -> TrainProfile:
    if isinstance(value, TrainProfile):
        return value
    if isinstance(value, dict):
        return TrainProfile.from_dict(value)
    raise TypeError(f"'profile' must be a TrainProfile or dict, got {value!r}")


class TrainMode(BaseMode):
    hardware_mode = ControlMode.TORQUE
    unit = "train"

    def __init__(self, cable_state: CableState):
        self.cable_state = cable_state
        self.profile = TrainProfile(name="empty", segments=[])
        self._commanded_torque_nm = 0.0
        self._target_force_n = 0.0

    # ---- BaseMode contract ----

    def validate_target(self, value) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError(f"Train target must be a dict, got {value!r}")
        action = value.get("action")
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Unknown train action: {action!r} (expected one of {sorted(_VALID_ACTIONS)})")

        profile = _coerce_profile(value.get("profile", TrainProfile(name="empty", segments=[])))
        return {"action": action, "profile": profile}

    def apply_target(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        action = value["action"]
        getattr(self, f"_apply_{action}")(hardware, value)

    def status_target(self, validated_value: Dict[str, Any]):
        return {"action": validated_value["action"], "profile": validated_value["profile"].to_dict()}

    def csv_log_name(self, mode: str) -> str:
        return f"{mode}-{self.profile.name}"

    # ---- action handlers ----

    def _apply_run(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        validate_homed(self.cable_state.is_homed)
        self.profile = value["profile"]
        hardware.set_mode(ControlMode.TORQUE)
        hardware.set_torque_target(0.0)

    def _apply_set_profile(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        # Live retarget: swap the profile in place, no hardware call needed
        # here -- the next tick() picks it up (mirrors ProfileMode's
        # "adjusted in place, never replaced mid-run" retarget shape, except
        # Train replaces the whole object since there's no single "primary
        # parameter" to nudge).
        self.profile = value["profile"]

    # ---- tick ----

    def tick(self, hardware: HardwareInterface, sample: TelemetrySample) -> Dict[str, Any]:
        extra: Dict[str, Any] = {
            "target_force_n": 0.0,
            "commanded_torque_nm": 0.0,
            "cable_length_m": None,
        }

        if self.cable_state.is_homed:
            extra["cable_length_m"] = self.cable_state.spool_geometry.length_from_turns_delta(
                sample.position - self.cable_state.home_turns
            )
        else:
            # No motion command if un-homed -- guards against a stray tick
            # landing here before the first "run" (which itself requires
            # homed), and after a homing reference is later cleared mid-run.
            hardware.set_torque_target(0.0)
            return extra

        if self.cable_state.has_max and (self.cable_state.train_home_guard_enforced or self.cable_state.train_max_extension_enforced):
            min_violated, max_violated = check_runtime_guard_split(
                sample.position,
                self.cable_state.home_turns,
                self.cable_state.max_turns,
                self.cable_state.position_guard_hard_turns,
            )
            # Each side only trips its own toggle -- a violation on a
            # disabled side is ignored, not just under-reported, so "relax
            # home, keep max enforced" (or vice versa) behaves as named.
            if (min_violated and self.cable_state.train_home_guard_enforced) or (
                max_violated and self.cable_state.train_max_extension_enforced
            ):
                side = "home" if min_violated else "max"
                raise RuntimeError(
                    f"Cable position ({sample.position:.4f} turns) left the permitted "
                    f"range [home={self.cable_state.home_turns:.4f}, "
                    f"max={self.cable_state.max_turns:.4f}] beyond the hard tolerance "
                    f"({self.cable_state.position_guard_hard_turns:.4f}) on the {side} "
                    f"side -- Train safety stop."
                )

        force_n = min(self.profile.force_at(extra["cable_length_m"]), board_constants.FORCE_MAX_N)
        # Torque = force * radius at the CURRENT effective spool radius, not
        # the bare r0 -- r_eff grows as cable pays in/out (k or, more
        # accurately, the piecewise growth-calibration model, whichever is
        # active -- see SpoolGeometry). Using a static r0 here while
        # cable_length_m above already tracks the growing radius meant the
        # torque commanded for a given target force silently drifted across
        # the travel range (spec: "calibration overhaul" item 3 -- surfaced
        # by a strap-thickness change large enough to make the drift
        # noticeable). CableState.r_eff_at_position() is the shared home for
        # this conversion (also used by ExerciseMode's force feedback and
        # calibration holds, and the Testing tab) -- reduces to plain r0 when
        # uncalibrated, and floors at SPOOL_MIN_EFFECTIVE_RADIUS_M so a
        # disabled range guard traveling past the last calibration point
        # can't drive r_eff toward zero/negative.
        r_eff = self.cable_state.r_eff_at_position(sample.position)
        torque_nm = force_to_torque(force_n, r0=r_eff)
        # Torque-calibration inverse correction (items 6/7): torque_nm above
        # is the real, physical torque this force is supposed to need --
        # raw_torque_nm_for_corrected() maps that to whatever raw Nm value
        # actually needs to be commanded so the calibrated real-world
        # relationship holds (identity until at least one calibration point
        # is recorded). `extra`/`_commanded_torque_nm` keep reporting the
        # real torque_nm, not the raw command -- that's what's meaningful to
        # a human reading it back.
        raw_torque_nm = self.cable_state.raw_torque_nm_for_corrected(torque_nm)
        hardware.set_torque_target(-CABLE_SIGN * raw_torque_nm)

        self._target_force_n = force_n
        self._commanded_torque_nm = torque_nm
        extra["target_force_n"] = force_n
        extra["commanded_torque_nm"] = torque_nm
        return extra
