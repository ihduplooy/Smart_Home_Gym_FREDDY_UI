"""TrainMode — the Train tab's control mode (train_tab_build_spec.md §2).

Fixed to torque control for its lifecycle, same as the old ForceMode/current
ExerciseMode force-feedback side. Every tick it reads cable position and
computes a target force one of two ways, converts to torque via the existing
`core.profiles.units.force_to_torque()`, and commands it directly:

  - Normally: evaluates the active `train_profiles.TrainProfile` segment at
    the current position (plus constant+inertia, sub-phase 3). Wherever the
    cable is, that's the torque, same in both directions — no phase
    detection, no rep counting DRIVES THIS FORCE PATH (spec §4/original
    design). Resist the urge to add ramping/hysteresis to *this* path even
    though `ExerciseMode` next door has it for a different feature.
  - When `phase_forces` is set (resistance-modes sub-phase 4, concentric/
    eccentric): position-based profile evaluation is bypassed entirely in
    favour of `phase_ramp_detector.PhaseRampDetector` -- a dedicated,
    standalone detector (deliberately NOT `core/profiles/detectors.py`'s own
    `PhaseDetector`, which ExerciseMode still uses unchanged) feeding a
    smooth blend between two configured force values, concentric and
    eccentric. See `phase_ramp_detector.py`'s own docstring for why this
    needed a second detector rather than reusing/extending the first.

Rep counting (resistance-modes sub-phase 5, GYM dashboard): a THIRD, entirely
separate detector pair -- `core/profiles/detectors.py`'s own `PhaseDetector`
+ `RepCounter`, unchanged, the exact instances `ExerciseMode` already runs --
ticks every homed sample regardless of which force path above is active,
populating `extra["rep_count"]` (a column the CSV logger has reserved since
the original session-3 spec but TrainMode never populated). This is
read-only telemetry, not a third way to compute force: it never feeds into
`force_n`, so the "no rep counting drives this force path" sentence above
still holds for both paths. Runs alongside `_phase_ramp_detector` rather than
reusing it because the two answer different questions at different
granularities -- `_phase_ramp_detector`'s 2-state concentric/eccentric output
is tuned for smooth force-blend timing (sub-phase 4), while `PhaseDetector`'s
4-state phase (with top/bottom holds) plus `RepCounter`'s EWMA-proximity
check is what's actually validated for discrete rep boundaries.

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
import math
from typing import Any, Dict

from config import board_constants
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.profiles.detectors import CABLE_SIGN, PhaseDetector, RepCounter
from core.profiles.units import force_to_torque, torque_to_force

from ..control.modes import BaseMode
from .geometry import speed_m_s_from_turns_s
from .limits import check_runtime_guard_split, validate_homed
from .phase_ramp_detector import CONCENTRIC, ECCENTRIC, PhaseRampDetector
from .power_limiter import estimate_regen_power_w
from .state import CableState
from .train_profiles import TrainProfile

log = logging.getLogger(__name__)

# Both the inertia filter's alpha and the concentric/eccentric delta cap used
# to be fixed module constants here. Now live-adjustable via CableState
# (inertia_velocity_filter_alpha / phase_force_delta_max_n, resistance-modes
# sub-phases 3/4's "configure in a GYM Settings sub-tab" follow-up) -- read
# off self.cable_state every time instead, board_constants.py's
# INERTIA_VELOCITY_FILTER_ALPHA_DEFAULT / PHASE_FORCE_DELTA_MAX_N_DEFAULT are
# what a fresh CableState seeds itself with.


def _estimated_power_w(sample: TelemetrySample) -> float:
    """Mechanical power estimate: torque (Nm) * angular velocity (rad/s).
    Same formula ExerciseMode.tick() uses -- kept as a local helper rather
    than a shared import since the module it used to live in
    (core/experiments/telemetry.py) is gone from this checkout."""
    return sample.torque_est * sample.velocity * 2.0 * math.pi

_VALID_ACTIONS = frozenset({"run", "set_profile"})


def _coerce_profile(value: Any) -> TrainProfile:
    if isinstance(value, TrainProfile):
        return value
    if isinstance(value, dict):
        return TrainProfile.from_dict(value)
    raise TypeError(f"'profile' must be a TrainProfile or dict, got {value!r}")


def _require_nonneg_force(phase_forces: Dict[str, Any], key: str) -> float:
    if key not in phase_forces:
        raise ValueError(f"phase_forces missing required key {key!r}")
    value = phase_forces[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"phase_forces[{key!r}] must be numeric, got {value!r}")
    value = float(value)
    if value < 0:
        raise ValueError(f"phase_forces[{key!r}] must be non-negative, got {value!r}")
    return value


def _coerce_phase_forces(value: Any, phase_force_delta_max_n: float) -> Any:
    """None (the default -- ordinary profile-based playback) or
    {"concentric_force_n": .., "eccentric_force_n": ..}, both non-negative
    and no more than `phase_force_delta_max_n` apart (TrainMode passes
    self.cable_state.phase_force_delta_max_n -- live-adjustable, resistance-
    modes sub-phase 4's Settings-sub-tab follow-up, not a fixed constant).
    Presence of a non-None result is what tick() uses to decide whether to
    bypass profile evaluation for the phase-detector path (sub-phase 4) --
    mutually exclusive with position-based profile playback, not combined
    with it."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError(f"'phase_forces' must be a dict or None, got {value!r}")
    concentric_force_n = _require_nonneg_force(value, "concentric_force_n")
    eccentric_force_n = _require_nonneg_force(value, "eccentric_force_n")
    delta = abs(concentric_force_n - eccentric_force_n)
    if delta > phase_force_delta_max_n:
        raise ValueError(
            f"concentric/eccentric force delta ({delta!r} N) exceeds the conservative "
            f"cap ({phase_force_delta_max_n!r} N) -- bench-validate the ramp before raising this"
        )
    return {"concentric_force_n": concentric_force_n, "eccentric_force_n": eccentric_force_n}


class TrainMode(BaseMode):
    hardware_mode = ControlMode.TORQUE
    unit = "train"

    def __init__(self, cable_state: CableState):
        self.cable_state = cable_state
        self.profile = TrainProfile(name="empty", segments=[])
        self._commanded_torque_nm = 0.0
        self._target_force_n = 0.0
        # Constant+inertia filter state (sub-phase 3) -- EMA-filtered
        # cable_velocity_m_s and the tick timestamp it was filtered at, so
        # tick() can difference consecutive filtered samples into an
        # acceleration estimate. None until the first tick after a "run"
        # (see _apply_run's reset) -- that first tick seeds the filter rather
        # than differencing against a stale/absent previous value.
        self._filtered_velocity_m_s = None
        self._last_inertia_tick_t = None
        # Concentric/eccentric (sub-phase 4): None = ordinary profile-based
        # playback (the default, every existing Train/GYM Constant+Band
        # session); a dict = phase-detector mode, bypassing profile
        # evaluation entirely (see tick()). _phase_ramp_detector tracks
        # which direction is currently "active" and any in-progress ramp --
        # persists across ticks the same way _filtered_velocity_m_s does for
        # inertia, reset on a fresh "run" and when phase mode is entered/left
        # (see _apply_run/_apply_set_profile).
        self.phase_forces = None
        self._phase_ramp_detector = PhaseRampDetector()
        # Rep counting (sub-phase 5, GYM dashboard) -- read-only telemetry,
        # runs every tick regardless of the active force path (see module
        # docstring). A second, independent PhaseDetector instance from the
        # one _phase_ramp_detector uses -- reset alongside it on a fresh
        # "run", but NOT on a phase-mode transition in _apply_set_profile
        # (a mid-set retarget shouldn't restart the rep/work count the user
        # is watching).
        self._rep_phase_detector = PhaseDetector()
        self._rep_counter = RepCounter()
        self._total_work_j = 0.0
        self._last_work_tick_t = None

    # ---- BaseMode contract ----

    def validate_target(self, value) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError(f"Train target must be a dict, got {value!r}")
        action = value.get("action")
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Unknown train action: {action!r} (expected one of {sorted(_VALID_ACTIONS)})")

        profile = _coerce_profile(value.get("profile", TrainProfile(name="empty", segments=[])))
        phase_forces = _coerce_phase_forces(value.get("phase_forces"), self.cable_state.phase_force_delta_max_n)
        return {"action": action, "profile": profile, "phase_forces": phase_forces}

    def apply_target(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        action = value["action"]
        getattr(self, f"_apply_{action}")(hardware, value)

    def status_target(self, validated_value: Dict[str, Any]):
        return {
            "action": validated_value["action"],
            "profile": validated_value["profile"].to_dict(),
            "phase_forces": validated_value["phase_forces"],
        }

    def csv_log_name(self, mode: str) -> str:
        return f"{mode}-{self.profile.name}"

    # ---- action handlers ----

    def _apply_run(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        validate_homed(self.cable_state.is_homed)
        self.profile = value["profile"]
        self.phase_forces = value["phase_forces"]
        # Fresh session -- reset the inertia filter so a stale velocity/
        # timestamp from a previous run (or simulator jump) can't be
        # differenced against this run's first real sample, and the phase-
        # ramp detector so a stale committed direction/in-progress ramp from
        # a previous run can't leak into this one.
        self._filtered_velocity_m_s = None
        self._last_inertia_tick_t = None
        self._phase_ramp_detector.reset()
        # Fresh set -- rep count and accumulated work restart too, same
        # "stale state from a previous run can't leak into this one"
        # reasoning as the two resets above.
        self._rep_phase_detector.reset()
        self._rep_counter.reset()
        self._total_work_j = 0.0
        self._last_work_tick_t = None
        hardware.set_mode(ControlMode.TORQUE)
        hardware.set_torque_target(0.0)

    def _apply_set_profile(self, hardware: HardwareInterface, value: Dict[str, Any]) -> None:
        # Live retarget: swap the profile/phase_forces in place, no hardware
        # call needed here -- the next tick() picks it up (mirrors
        # ProfileMode's "adjusted in place, never replaced mid-run" retarget
        # shape, except Train replaces the whole object since there's no
        # single "primary parameter" to nudge). The phase-ramp detector only
        # resets when phase mode itself is being entered or left -- switching
        # phase_forces' VALUES while already in phase mode (e.g. nudging
        # concentric_force_n) should keep tracking the same in-progress
        # direction/ramp, same as changing a profile's forces mid-run
        # doesn't reset the inertia filter either.
        was_phase_mode = self.phase_forces is not None
        self.profile = value["profile"]
        self.phase_forces = value["phase_forces"]
        if was_phase_mode != (self.phase_forces is not None):
            self._phase_ramp_detector.reset()

    # ---- constant+inertia (sub-phase 3) ----

    def _filtered_acceleration_m_s2(self, cable_velocity_m_s: float, now_t: float) -> float:
        """EMA-smooth cable_velocity_m_s, then difference consecutive
        filtered samples over dt for an acceleration estimate. Kept as its
        own small function (not inlined into tick()) so its one constant
        (self.cable_state.inertia_velocity_filter_alpha -- live-adjustable,
        GYM's Settings sub-tab) is easy to find and retune after a bench
        session, per the sub-phase 3 doc's explicit ask.

        Runs every tick regardless of the active segment's inertia_kg (not
        just while inside an inertia segment) so the filter is already warm
        -- not cold-started mid-segment -- by the time a position with a
        nonzero inertia_kg is reached."""
        if self._filtered_velocity_m_s is None or self._last_inertia_tick_t is None:
            self._filtered_velocity_m_s = cable_velocity_m_s
            self._last_inertia_tick_t = now_t
            return 0.0

        dt = now_t - self._last_inertia_tick_t
        alpha = self.cable_state.inertia_velocity_filter_alpha
        prev_filtered_m_s = self._filtered_velocity_m_s
        self._filtered_velocity_m_s = alpha * cable_velocity_m_s + (1 - alpha) * prev_filtered_m_s
        self._last_inertia_tick_t = now_t
        if dt <= 0:
            # Non-advancing or out-of-order timestamp (e.g. a stray repeated
            # sample) -- can't safely divide by it; report no acceleration
            # this tick rather than a spurious spike.
            return 0.0
        return (self._filtered_velocity_m_s - prev_filtered_m_s) / dt

    def _profile_force_n(self, cable_length_m: float, cable_velocity_m_s: float, now_t: float) -> float:
        """Ordinary position-based profile playback (unchanged since
        sub-phase 3): the active segment's own force_at(), plus
        constant+inertia's F_inertia = inertia_kg * a_filtered. inertia_kg
        itself is clamped to the live cable_state.inertia_kg_max ceiling here
        -- TrainSegment accepts any non-negative value at construction (same
        "unbounded until delivered" split force_n itself uses), this is
        where that ceiling actually bites, same as force_max_n's own clamp
        below in tick()."""
        active_segment = self.profile.segment_at(cable_length_m)
        inertia_kg = active_segment.params.get("inertia_kg", 0.0) if active_segment is not None else 0.0
        inertia_kg = min(inertia_kg, self.cable_state.inertia_kg_max)
        a_filtered_m_s2 = self._filtered_acceleration_m_s2(cable_velocity_m_s, now_t)
        inertia_force_n = inertia_kg * a_filtered_m_s2
        base_force_n = self.profile.force_at(cable_length_m)
        return base_force_n + inertia_force_n

    def _phase_force_n(self, cable_length_m: float, cable_velocity_m_s: float, now_t: float):
        """Concentric/eccentric (sub-phase 4): total force = whichever of
        concentric_force_n/eccentric_force_n is currently active, blended
        toward it over the ramp when a direction flip just committed.
        Returns (force_n, phase_label) -- the label is only for `extra`
        telemetry, force_n is what actually gets commanded. The detector's
        own five tunable constants are read live off cable_state every tick
        (not baked into the detector instance), so a Settings-sub-tab change
        takes effect immediately, including mid-session."""
        state = self._phase_ramp_detector.update(
            cable_length_m,
            cable_velocity_m_s,
            now_t,
            velocity_deadband_m_s=self.cable_state.phase_velocity_deadband_m_s,
            min_sustained_velocity_m_s=self.cable_state.phase_min_sustained_velocity_m_s,
            sustain_window_s=self.cable_state.phase_sustain_window_s,
            reversal_distance_m=self.cable_state.phase_reversal_distance_m,
            ramp_duration_s=self.cable_state.phase_ramp_duration_s,
        )
        force_for_phase = {
            CONCENTRIC: self.phase_forces["concentric_force_n"],
            ECCENTRIC: self.phase_forces["eccentric_force_n"],
        }
        from_force_n = force_for_phase[state.previous_phase]
        to_force_n = force_for_phase[state.phase]
        force_n = from_force_n + state.ramp_progress * (to_force_n - from_force_n)
        return force_n, state.phase

    # ---- tick ----

    def tick(self, hardware: HardwareInterface, sample: TelemetrySample) -> Dict[str, Any]:
        # bus_voltage_v/estimated_power_w/estimated_force_n/cable_velocity_m_s
        # are plain sample-derived readings (not profile-dependent), so
        # they're set here unconditionally -- same reasoning as
        # ExerciseMode.tick()'s own top-of-function extra dict -- rather than
        # only on the profile-evaluated path below, so the CSV logger
        # (core/telemetry/csv_logger.py's already-reserved columns) gets them
        # even on the un-homed early return. r_eff_at_position()/r0 both fall
        # back to sensible un-homed defaults (see CableState), so these are
        # safe to compute before the is_homed check. commanded_force_n
        # mirrors target_force_n under the CSV logger's column name
        # (core/control/session.py reads "commanded_force_n", not
        # "target_force_n" -- that key is left alone since test_train_mode.py
        # and TrainTab.jsx both depend on it).
        #
        # force_state/experiment_state and Testing-tab's position_m/
        # velocity_m_s/target_position_m are left out of `extra` entirely --
        # they're concepts from ExerciseMode's force-feedback state machine
        # and the (currently unbuilt) Testing tab that don't map onto Train's
        # single-state profile playback; the CSV logger writes an empty cell
        # for any key a mode doesn't set. power_limiter_active is set (not
        # omitted) but always False: Train intentionally never clamps force
        # against the regen power budget the way ExerciseMode does, so False
        # here means "not applied", same as it would for any other mode that
        # doesn't use the limiter.
        cable_velocity_turns_s = CABLE_SIGN * sample.velocity  # + = paying out
        cable_velocity_m_s = speed_m_s_from_turns_s(cable_velocity_turns_s, self.cable_state.r0)
        extra: Dict[str, Any] = {
            "target_force_n": 0.0,
            "commanded_force_n": 0.0,
            "commanded_torque_nm": 0.0,
            "cable_length_m": None,
            "bus_voltage_v": sample.bus_voltage_v,
            "estimated_power_w": _estimated_power_w(sample),
            "estimated_force_n": torque_to_force(
                self.cable_state.corrected_torque_nm(sample.torque_est, cable_velocity_turns_s),
                r0=self.cable_state.r_eff_at_position(sample.position),
            ),
            "cable_velocity_m_s": cable_velocity_m_s,
            "regen_power_w": 0.0,
            "power_limiter_active": False,
            "rep_count": self._rep_counter.rep_count,
            "total_work_j": self._total_work_j,
        }

        if self.cable_state.is_homed:
            extra["cable_length_m"] = self.cable_state.spool_geometry.length_from_turns_delta(
                sample.position - self.cable_state.home_turns
            )
            # Rep counting (sub-phase 5): raw turns position/velocity, same
            # units ExerciseMode.tick() already feeds these two -- see the
            # module docstring for why this runs unconditionally rather than
            # only in one force path.
            rep_phase = self._rep_phase_detector.update(sample.velocity)
            extra["rep_count"] = self._rep_counter.update(sample.position, rep_phase)
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

        # Two mutually-exclusive ways to arrive at a target force, before the
        # existing force_max_n cap and torque-calibration pipeline below --
        # neither of those change, they just see a different input force.
        # phase_forces (sub-phase 4) bypasses position-based profile
        # evaluation entirely when set; otherwise this is exactly sub-phase
        # 3's constant+inertia-aware profile playback, unchanged.
        if self.phase_forces is not None:
            base_force_n, phase_label = self._phase_force_n(extra["cable_length_m"], cable_velocity_m_s, sample.t)
            extra["phase"] = phase_label
        else:
            base_force_n = self._profile_force_n(extra["cable_length_m"], cable_velocity_m_s, sample.t)
        # Floored at 0 same as TrainProfile.force_at() itself (module
        # docstring: "Force values here are never negative") -- inertia's
        # deceleration term could otherwise drive the total negative, which
        # would command the motor to actively assist/reel in rather than
        # just resist (phase_forces can't go negative itself -- both configured
        # values and every blend between them are already non-negative -- but
        # the shared clamp costs nothing to apply either way).
        force_n = min(max(base_force_n, 0.0), self.cable_state.force_max_n)
        # Work accumulator (sub-phase 5): mechanical work done against the
        # commanded force, |F * v| integrated over time -- not the "true"
        # work a load cell in the strap would report, but the same
        # commanded-force-times-velocity proxy _estimated_power_w()/
        # estimate_regen_power_w() already use elsewhere in this file for
        # informational telemetry. Guards a zero/negative dt the same way
        # _filtered_acceleration_m_s2() does (a stray repeated timestamp
        # can't silently subtract from the running total).
        if self._last_work_tick_t is not None:
            work_dt = sample.t - self._last_work_tick_t
            if work_dt > 0:
                self._total_work_j += force_n * abs(cable_velocity_m_s) * work_dt
        self._last_work_tick_t = sample.t
        extra["total_work_j"] = self._total_work_j
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
        raw_torque_nm = self.cable_state.raw_torque_nm_for_corrected(torque_nm, cable_velocity_turns_s)
        hardware.set_torque_target(-CABLE_SIGN * raw_torque_nm)

        self._target_force_n = force_n
        self._commanded_torque_nm = torque_nm
        extra["target_force_n"] = force_n
        extra["commanded_force_n"] = force_n
        extra["commanded_torque_nm"] = torque_nm
        # Informational only (spec decision: telemetry, not enforcement) --
        # P_mech - P_copper for the force actually being commanded here, same
        # formula ExerciseMode's power limiter uses, but Train never clamps
        # against it (power_limiter_active above stays False unconditionally).
        extra["regen_power_w"] = estimate_regen_power_w(
            force_n,
            cable_velocity_m_s,
            board_constants.MOTOR_TORQUE_CONSTANT,
            board_constants.MOTOR_PHASE_RESISTANCE_OHM,
            self.cable_state.r0,
        )
        return extra
