"""CableState — Exercise tab Layer A (exercise_tab_build_spec_layerA.md §6).

A deliberate departure from the spec's suggested `exercise_mode.py`-ties-
everything-together shape (§2.1): `core/control/session.py::ControlSession
.stop()` sets `self._mode_handler = None`, destroying whatever a BaseMode
instance owns. But §3.5 requires "Reset Position" to be available *while
idle* (no session running) -- which only makes sense if a still-valid home
reference can survive a Stop. So home/max cannot live inside ExerciseMode
the way ProfileMode's phase detector lives inside ProfileMode; they need a
home with a longer lifetime than any single ControlSession run.

CableState is that home: constructed once per backend process (same
lifetime as control_routes.py's `control_session` singleton) and injected
into ExerciseMode via ControlSession's mode_factories hook, rather than
being rebuilt by `mode_cls()` on every start(). See docs/decisions.md
("Exercise tab Layer A" entry) for the full reasoning.

Persistence split (spec §6), enforced here:
  - home_turns / max_turns / marked_max_turns: in-memory only, never written
    to disk. A freshly-constructed CableState (i.e. every backend process
    start) is un-homed -- this IS the "backend restart comes up un-homed"
    guarantee, by construction, not by a separate reset-on-boot step.
  - k, r0, and the homing tuning settings below: persisted to a small JSON
    sidecar (config/spool_calibration.json, gitignored -- it's bench/
    physical-spool-specific state, not source), loaded at construction,
    written back only on an explicit change.
  - spool_growth_points (the experimental multi-point growth calibration,
    train tab calibration overhaul): persisted the same way, but to its own
    sidecar (config/spool_growth_calibration.json) since a list of (turns,
    length) pairs doesn't fit the float-only mechanism the settings above
    share. pending_growth_points (points recorded but not yet saved) is
    in-memory only, same character as home_turns/max_turns above.

Live-adjustable homing settings (velocity/current threshold/current limit),
spool radius, and max-extension calibration hold force added 23 July 2026,
after the first live-hardware session:
the bench-tuned board_constants.py defaults didn't match what the real
board needed closely enough to be useful as fixed values, and the user
explicitly asked for on-screen control over them rather than editing
board_constants.py and restarting the backend each time. These are
per-spool/per-bench properties, the same character as `k`, so they persist
the same way and through the same sidecar file rather than inventing a
second mechanism.

Force/safety "feel" settings (let-go threshold/debounce, hold duration,
force ramp rates, isokinetic governor gain/filter, max-extension force
taper, two-tier position guard) added 24 July 2026, same rationale and same
mechanism: every one of these was a board_constants placeholder its own
file header admitted was untested. Deliberately NOT extended to
MOTOR_CURRENT_LIM or the DC bus regen limits -- those stay fixed
board_constants, since raising them live could put real hardware at risk
with no software backstop of their own.

FORCE_MAX_N/REGEN_POWER_BUDGET_W (18 Aug 2026): made live-adjustable too,
via set_power_limits() below, but NOT with the same bare "any positive
number" validation the settings above get -- set_power_limits() rejects a
force_max_n above the structural ceiling _TORQUE_LIMIT_NM (core/hardware/
odrive_hw.py) implies (MOTOR_CURRENT_LIM * MOTOR_TORQUE_CONSTANT /
SPOOL_RADIUS_M), the same hardware-derived envelope FORCE_MAX_N's own
board_constants.py comment already reasons from. This keeps the "can't
exceed what the motor can structurally deliver" guarantee the old
fixed-constant approach gave for free, while still letting FORCE_MAX_N be
lowered (or raised toward that ceiling) from the Configuration tab without
editing board_constants.py and restarting the backend -- the same
motivation the homing settings above were added for. REGEN_POWER_BUDGET_W
has no equivalent hardware-derived ceiling in this codebase (the 30W
default is a conservative derate of the brake resistor's rated
dissipation, not a computed structural limit), so it only gets the
"positive number" check; a value chosen well above the resistor's real
rating won't be caught here, same live-hardware-risk caveat as always.

This module is still hardware-free/Flask-free (only reads config.
board_constants and a local JSON file), but it is NOT pure/stateless like
geometry.py, homing.py, limits.py -- it is the one stateful piece in
core/cable/, by design.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from config import board_constants
from core.profiles.detectors import CABLE_SIGN

from . import geometry
from .limits import validate_max_extension_candidate
from .torque_calibration import TorqueCalibration, TorqueCalibrationPoint

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SIDECAR_PATH = _REPO_ROOT / "config" / "spool_calibration.json"
_DEFAULT_GROWTH_SIDECAR_PATH = _REPO_ROOT / "config" / "spool_growth_calibration.json"
_DEFAULT_TORQUE_CALIBRATION_SIDECAR_PATH = _REPO_ROOT / "config" / "torque_calibration.json"

# Settings key -> board_constants default. Single source of truth for what
# persists in the sidecar file and what each falls back to when the file is
# absent/corrupt/missing a key (e.g. an older sidecar written before this
# entry was added).
_PERSISTED_DEFAULTS = {
    "k": lambda: board_constants.SPOOL_CORRECTION_K_DEFAULT,
    "r0": lambda: board_constants.SPOOL_RADIUS_M,
    "homing_current_threshold_a": lambda: board_constants.HOMING_CURRENT_THRESHOLD_A,
    "homing_velocity_turns_s": lambda: board_constants.HOMING_VELOCITY_TURNS_S,
    "homing_current_limit_a": lambda: board_constants.HOMING_CURRENT_LIMIT_A,
    "calib_hold_force_n": lambda: board_constants.CALIB_HOLD_FORCE_N,
    "letgo_velocity_turns_s": lambda: board_constants.LETGO_VELOCITY_TURNS_S,
    "letgo_debounce_samples": lambda: board_constants.LETGO_DEBOUNCE_SAMPLES,
    "hold_duration_s": lambda: board_constants.HOLD_DURATION_S,
    "force_ramp_in_s": lambda: board_constants.FORCE_RAMP_IN_S,
    "force_ramp_out_s": lambda: board_constants.FORCE_RAMP_OUT_S,
    "isokinetic_governor_gain": lambda: board_constants.ISOKINETIC_GOVERNOR_GAIN,
    "isokinetic_velocity_filter_alpha": lambda: board_constants.ISOKINETIC_VELOCITY_FILTER_ALPHA,
    "max_extension_force_taper_m": lambda: board_constants.MAX_EXTENSION_FORCE_TAPER_M,
    "position_guard_warning_turns": lambda: board_constants.POSITION_GUARD_WARNING_TURNS,
    "position_guard_hard_turns": lambda: board_constants.POSITION_GUARD_TOLERANCE_TURNS,
    "train_max_extension_enforced": lambda: board_constants.TRAIN_MAX_EXTENSION_ENFORCED_DEFAULT,
    "train_home_guard_enforced": lambda: board_constants.TRAIN_HOME_GUARD_ENFORCED_DEFAULT,
    "train_telemetry_buffer_s": lambda: board_constants.TRAIN_TELEMETRY_BUFFER_S,
    "resistance_display_unit_kg": lambda: board_constants.RESISTANCE_DISPLAY_UNIT_KG_DEFAULT,
    "force_max_n": lambda: board_constants.FORCE_MAX_N,
    "regen_power_budget_w": lambda: board_constants.REGEN_POWER_BUDGET_W,
}


class CableState:
    def __init__(
        self,
        sidecar_path: Optional[Path] = None,
        growth_sidecar_path: Optional[Path] = None,
        torque_calibration_sidecar_path: Optional[Path] = None,
    ):
        self._sidecar_path = sidecar_path if sidecar_path is not None else _DEFAULT_SIDECAR_PATH
        self._growth_sidecar_path = growth_sidecar_path if growth_sidecar_path is not None else _DEFAULT_GROWTH_SIDECAR_PATH
        self._torque_calibration_sidecar_path = (
            torque_calibration_sidecar_path
            if torque_calibration_sidecar_path is not None
            else _DEFAULT_TORQUE_CALIBRATION_SIDECAR_PATH
        )
        settings = self._load_settings()
        self.k = settings["k"]
        self.r0 = settings["r0"]
        self.homing_current_threshold_a = settings["homing_current_threshold_a"]
        self.homing_velocity_turns_s = settings["homing_velocity_turns_s"]
        self.homing_current_limit_a = settings["homing_current_limit_a"]
        self.calib_hold_force_n = settings["calib_hold_force_n"]
        self.letgo_velocity_turns_s = settings["letgo_velocity_turns_s"]
        self.letgo_debounce_samples = settings["letgo_debounce_samples"]
        self.hold_duration_s = settings["hold_duration_s"]
        self.force_ramp_in_s = settings["force_ramp_in_s"]
        self.force_ramp_out_s = settings["force_ramp_out_s"]
        self.isokinetic_governor_gain = settings["isokinetic_governor_gain"]
        self.isokinetic_velocity_filter_alpha = settings["isokinetic_velocity_filter_alpha"]
        self.max_extension_force_taper_m = settings["max_extension_force_taper_m"]
        self.position_guard_warning_turns = settings["position_guard_warning_turns"]
        self.position_guard_hard_turns = settings["position_guard_hard_turns"]
        # bool(...) here, not a bare assignment: _load_settings() always
        # runs persisted values through float() when they come from the JSON
        # sidecar (see that method), so a round-tripped boolean would
        # otherwise land here as 1.0/0.0 rather than True/False. Re-coercing
        # on load keeps this attribute a genuine bool for the rest of its
        # lifetime, including the next _save_settings() write.
        self.train_max_extension_enforced = bool(settings["train_max_extension_enforced"])
        self.train_home_guard_enforced = bool(settings["train_home_guard_enforced"])
        self.train_telemetry_buffer_s = settings["train_telemetry_buffer_s"]
        self.resistance_display_unit_kg = bool(settings["resistance_display_unit_kg"])
        self.force_max_n = settings["force_max_n"]
        self.regen_power_budget_w = settings["regen_power_budget_w"]

        # Experimental multi-point spool-growth calibration (turns_from_home,
        # length_m) pairs -- persisted separately from the float-only sidecar
        # above since these are tuples, not floats (see _load_growth_points/
        # _save_growth_points). Empty by default: falls back to the plain
        # r0+k*theta model below, completely unchanged from before this
        # existed.
        self.spool_growth_points: List[Tuple[float, float]] = self._load_growth_points()
        self.spool_geometry = geometry.SpoolGeometry(self.r0, self.k, self.spool_growth_points)

        # Torque/force calibration (items 6/7) -- corrects the fixed-
        # MOTOR_TORQUE_CONSTANT torque estimate against known-weight
        # measurements. Same "own dedicated sidecar, empty/identity by
        # default" pattern as spool_growth_points above -- see
        # core/cable/torque_calibration.py's module docstring for the model.
        self.torque_calibration_points: List[TorqueCalibrationPoint] = self._load_torque_calibration_points()
        self.torque_calibration = TorqueCalibration(self.torque_calibration_points)

        # Physical max-extension length (m, from home), persisted the same
        # sidecar as k/r0 above but handled as its own explicit Optional key
        # (like spool_growth_points) rather than through the float-only
        # _PERSISTED_DEFAULTS loop, since "not yet calibrated" (None) is a
        # real, valid state. Unlike home_turns/max_turns (absolute encoder
        # turns, meaningless once the reference frame moves), a physical
        # length survives a re-home unchanged -- latch_home() below
        # reapplies it against the new home_turns automatically, so a
        # calibrated max extension is only ever lost by an explicit new
        # calibration, never by re-homing or reset().
        self.max_extension_length_m: Optional[float] = settings["max_extension_length_m"]

        # In-memory only -- see module docstring.
        self.home_turns: Optional[float] = None
        self.max_turns: Optional[float] = None  # enforced (safety-margined)
        self.marked_max_turns: Optional[float] = None  # raw marked point, display-only

        self.homing_in_progress = False
        self.max_calibration_in_progress = False
        self.spool_growth_calibration_in_progress = False
        # Points recorded during an in-progress spool-growth calibration,
        # not yet saved -- discarded on cancel, committed via
        # set_growth_points() on save (mirrors how home/max stay in-memory
        # only until an explicit commit).
        self.pending_growth_points: List[Tuple[float, float]] = []
        self.last_homing_fault: Optional[str] = None

    def r_eff_at_position(self, position_turns: float) -> float:
        """The effective spool radius to use for a force<->torque conversion
        at a live position -- the ONE place that decision is made, so every
        caller (force feedback, calibration holds, telemetry display) uses
        the same growth-corrected radius core/cable/train_mode.py already
        uses, instead of each re-deriving (or forgetting to derive) it
        themselves. Floored at SPOOL_MIN_EFFECTIVE_RADIUS_M for the same
        reason train_mode.py's own inline version is: the piecewise growth
        model's final segment extrapolates unbounded past the last
        calibration point. Falls back to the bare r0 when not yet homed --
        there's no turns-from-home reference to compute r_eff against."""
        if not self.is_homed:
            return self.r0
        r_eff = self.spool_geometry.r_eff_at_turns_delta(position_turns - self.home_turns)
        return max(r_eff, board_constants.SPOOL_MIN_EFFECTIVE_RADIUS_M)

    def corrected_torque_nm(self, raw_nm: float, cable_velocity_turns_s: float = 0.0) -> float:
        """Raw (motor-constant-only) torque estimate -> calibrated real
        torque -- the ONE place that decision is made, mirroring
        r_eff_at_position() above. Identity (no-op) until at least one
        torque-calibration point is recorded in the direction picked by
        `cable_velocity_turns_s` (CABLE-frame, + = paying out/lowering --
        see torque_calibration.py's module docstring)."""
        return self.torque_calibration.corrected_torque_nm(raw_nm, cable_velocity_turns_s)

    def raw_torque_nm_for_corrected(self, corrected_nm: float, cable_velocity_turns_s: float = 0.0) -> float:
        """Inverse of corrected_torque_nm() -- what raw Nm value to actually
        command so the real, physical torque delivered matches
        `corrected_nm` (the value the rest of the codebase reasons about in
        force/torque terms). Identity until calibrated. Same `cable_velocity
        _turns_s` direction selection as corrected_torque_nm above."""
        return self.torque_calibration.raw_torque_nm_for_corrected(corrected_nm, cable_velocity_turns_s)

    def add_torque_calibration_point(
        self, known_weight_kg: float, raw_torque_nm: float, r_eff_m: float, direction: str
    ) -> None:
        """Records one calibration measurement, sourced from the steady-
        state portion of a real repeated-lift run -- see
        core/cable/torque_calibration_run.py.extract_calibration_points_from
        _run(), whose DirectionCalibrationResult.point is what callers
        (backend/app/exercise_routes.py) pass straight through here.
        `r_eff_m` and `direction` are taken as given rather than re-derived
        (unlike the old single-live-snapshot workflow this replaces) because
        they're already an average over the run's steady-state samples --
        there's no single live position/velocity for this method to derive
        them from."""
        if not self.is_homed:
            raise RuntimeError("Cable is not homed -- home before recording a torque calibration point")
        if known_weight_kg < 0:
            raise ValueError(f"known_weight_kg must be non-negative, got {known_weight_kg!r}")
        point = TorqueCalibrationPoint(
            known_weight_kg=known_weight_kg, raw_torque_nm=raw_torque_nm, r_eff_m=r_eff_m, direction=direction
        )
        self.torque_calibration_points.append(point)
        self.torque_calibration = TorqueCalibration(self.torque_calibration_points)
        self._save_torque_calibration_points()

    def clear_torque_calibration(self) -> None:
        """Wipes every recorded point, reverting to the identity model --
        same "start over" convention clear_growth_calibration() already has."""
        self.torque_calibration_points = []
        self.torque_calibration = TorqueCalibration(self.torque_calibration_points)
        self._save_torque_calibration_points()

    @property
    def is_homed(self) -> bool:
        return self.home_turns is not None

    @property
    def has_max(self) -> bool:
        return self.max_turns is not None

    def latch_home(self, position_turns: float) -> None:
        """A fresh home reference always clears the old, turns-based max
        (it was marked relative to the now-discarded reference). If a
        physical max-extension LENGTH is already known (max_extension_length_m,
        persisted across re-homes -- see module docstring), it's immediately
        reapplied against the new home reference instead of being lost: the
        physical travel range of the rig didn't change just because the
        encoder's zero point did. Falls back to a bare ValueError from
        validate_max_extension_candidate propagating up (leaving max
        uncalibrated) only if the persisted length has somehow become
        invalid for the new reference -- a discarded/corrupt sidecar, not a
        normal case."""
        self.home_turns = position_turns
        self.max_turns = None
        self.marked_max_turns = None
        if self.max_extension_length_m is not None:
            turns_delta = self.spool_geometry.turns_delta_from_length(self.max_extension_length_m)
            marked_turns = self.home_turns + CABLE_SIGN * turns_delta
            validate_max_extension_candidate(marked_turns, self.home_turns, board_constants.MAX_EXTENSION_MIN_TRAVEL_TURNS)
            self.set_max(marked_turns, marked_turns)

    def set_max(self, marked_turns: float, enforced_turns: float) -> None:
        self.marked_max_turns = marked_turns
        self.max_turns = enforced_turns
        # Persist the physical length (not the turns) so it survives a
        # future re-home -- see latch_home() above and the module docstring.
        self.max_extension_length_m = self.spool_geometry.length_from_turns_delta(enforced_turns - self.home_turns)
        self._save_settings()

    def reset(self) -> None:
        """Manual position reset (spec §3.5) -- clears home/max, does NOT
        touch k/r0/homing settings (physical/bench properties, not session
        artifacts)."""
        self.home_turns = None
        self.max_turns = None
        self.marked_max_turns = None

    def set_k(self, k: float) -> None:
        self.k = k
        self.spool_geometry = geometry.SpoolGeometry(self.r0, self.k, self.spool_growth_points)
        self._save_settings()

    def set_r0(self, r0: float) -> None:
        if r0 <= 0:
            raise ValueError(f"r0 (spool radius) must be positive, got {r0!r}")
        self.r0 = r0
        self.spool_geometry = geometry.SpoolGeometry(self.r0, self.k, self.spool_growth_points)
        self._save_settings()

    def check_k_against_travel_range(self, k: float) -> None:
        """Precise, exact-range validation for a candidate k, ADDITIONAL to
        the coarse fat-finger SPOOL_CORRECTION_K_BOUNDS check the caller
        already did (board_constants.py) -- if a max extension is
        calibrated, reject a k that would take r_eff at or below
        board_constants.SPOOL_MIN_EFFECTIVE_RADIUS_M anywhere before the
        cable's actual max extension. This is tighter or looser than a
        static guess depending on the real travel range, rather than always
        conservative the way a fixed bound has to be."""
        if not (self.is_homed and self.has_max):
            return  # nothing to check against yet -- no real range known
        theta_max_rad = geometry.radians_from_turns(abs(self.max_turns - self.home_turns))
        r_eff_at_max = self.r0 + k * theta_max_rad
        floor = board_constants.SPOOL_MIN_EFFECTIVE_RADIUS_M
        if r_eff_at_max <= floor:
            max_turns_from_home = geometry.turns_from_radians(theta_max_rad)
            raise ValueError(
                f"k={k!r} would take the effective spool radius to {r_eff_at_max!r} m "
                f"by the calibrated max extension ({max_turns_from_home:.3f} turns from "
                f"home), at or below the {floor!r} m floor -- check the measured length "
                f"used to compute this k."
            )

    def set_growth_points(self, points: List[Tuple[float, float]]) -> None:
        """Persist the experimental multi-point spool-growth calibration
        (turns_from_home, length_m) pairs, replacing whatever was there
        before -- an empty list reverts to the plain r0+k*theta model.
        Validates via geometry.build_growth_segments (surfacing its
        ValueError unchanged) before committing anything, so a bad set of
        points never partially overwrites a good one."""
        if points:
            points_rad = [(geometry.radians_from_turns(t), length_m) for t, length_m in points]
            geometry.build_growth_segments(
                self.r0, points_rad, min_r_eff_m=board_constants.SPOOL_MIN_EFFECTIVE_RADIUS_M
            )
        self.spool_growth_points = list(points)
        self.spool_geometry = geometry.SpoolGeometry(self.r0, self.k, self.spool_growth_points)
        self._save_growth_points()

    def add_pending_growth_point(self, turns_from_home: float, length_m: float) -> None:
        self.pending_growth_points.append((turns_from_home, length_m))

    def remove_pending_growth_point(self, index: int) -> None:
        if not (0 <= index < len(self.pending_growth_points)):
            raise ValueError(f"index {index!r} out of range for {len(self.pending_growth_points)} pending points")
        del self.pending_growth_points[index]

    def clear_pending_growth_points(self) -> None:
        self.pending_growth_points = []

    def set_max_extension_manual(self, length_m: float) -> None:
        """Manual max-extension entry (train tab calibration overhaul item
        1) -- an alternative to the physical-pull start/confirm flow
        (exercise_mode.py's max_calibrating action) for when the max
        extension is already known (measured by hand, or already set on a
        near-identical rig). Converts via the currently-active spool model
        (plain k or the experimental piecewise growth model, whichever is
        active) and applies the exact same sanity check
        (validate_max_extension_candidate) and no-margin convention
        (marked_turns == enforced_turns) the physical flow uses, so both
        paths produce an equally-trustworthy max_turns."""
        if not self.is_homed:
            raise RuntimeError("Cable is not homed -- home before setting a max extension")
        if length_m < 0:
            raise ValueError(f"length_m must be non-negative, got {length_m!r}")
        turns_delta = self.spool_geometry.turns_delta_from_length(length_m)
        marked_turns = self.home_turns + CABLE_SIGN * turns_delta
        validate_max_extension_candidate(marked_turns, self.home_turns, board_constants.MAX_EXTENSION_MIN_TRAVEL_TURNS)
        self.set_max(marked_turns, marked_turns)

    def set_homing_settings(
        self,
        current_threshold_a: Optional[float] = None,
        velocity_turns_s: Optional[float] = None,
        current_limit_a: Optional[float] = None,
    ) -> None:
        """Any subset may be updated at once; omitted ones are left as-is.
        Validated together so a bad combination (e.g. limit below threshold)
        is rejected as a whole, not applied partially."""
        new_threshold = current_threshold_a if current_threshold_a is not None else self.homing_current_threshold_a
        new_velocity = velocity_turns_s if velocity_turns_s is not None else self.homing_velocity_turns_s
        new_limit = current_limit_a if current_limit_a is not None else self.homing_current_limit_a

        if new_threshold <= 0:
            raise ValueError(f"homing current threshold must be positive, got {new_threshold!r}")
        if new_velocity <= 0:
            raise ValueError(f"homing velocity must be positive, got {new_velocity!r}")
        if new_limit <= new_threshold:
            raise ValueError(
                f"homing current limit ({new_limit!r}) must be greater than the "
                f"detection threshold ({new_threshold!r}) -- otherwise the motor "
                f"can never draw enough current to ever detect the cable going taut."
            )
        if new_limit > board_constants.MOTOR_CURRENT_LIM:
            raise ValueError(
                f"homing current limit ({new_limit!r}) must not exceed the board's "
                f"operating current limit ({board_constants.MOTOR_CURRENT_LIM!r})."
            )

        self.homing_current_threshold_a = new_threshold
        self.homing_velocity_turns_s = new_velocity
        self.homing_current_limit_a = new_limit
        self._save_settings()

    def set_calib_hold_force(self, force_n: float) -> None:
        if force_n <= 0:
            raise ValueError(f"calibration hold force must be positive, got {force_n!r}")
        self.calib_hold_force_n = force_n
        self._save_settings()

    def set_force_settings(
        self,
        letgo_velocity_turns_s: Optional[float] = None,
        letgo_debounce_samples: Optional[float] = None,
        hold_duration_s: Optional[float] = None,
        force_ramp_in_s: Optional[float] = None,
        force_ramp_out_s: Optional[float] = None,
        isokinetic_governor_gain: Optional[float] = None,
        isokinetic_velocity_filter_alpha: Optional[float] = None,
        max_extension_force_taper_m: Optional[float] = None,
        position_guard_warning_turns: Optional[float] = None,
        position_guard_hard_turns: Optional[float] = None,
    ) -> None:
        """Live-adjustable force/safety "feel" settings (spec: requested 24
        July 2026, same rationale/mechanism as set_homing_settings -- any
        subset may be updated at once, omitted ones left as-is, validated
        together so a bad combination is rejected as a whole. Deliberately
        does NOT cover hard hardware ceilings (FORCE_MAX_N,
        REGEN_POWER_BUDGET_W, MOTOR_CURRENT_LIM, DC bus regen limits) -- see
        the module docstring."""
        new = {
            "letgo_velocity_turns_s": letgo_velocity_turns_s if letgo_velocity_turns_s is not None else self.letgo_velocity_turns_s,
            "letgo_debounce_samples": letgo_debounce_samples if letgo_debounce_samples is not None else self.letgo_debounce_samples,
            "hold_duration_s": hold_duration_s if hold_duration_s is not None else self.hold_duration_s,
            "force_ramp_in_s": force_ramp_in_s if force_ramp_in_s is not None else self.force_ramp_in_s,
            "force_ramp_out_s": force_ramp_out_s if force_ramp_out_s is not None else self.force_ramp_out_s,
            "isokinetic_governor_gain": isokinetic_governor_gain if isokinetic_governor_gain is not None else self.isokinetic_governor_gain,
            "isokinetic_velocity_filter_alpha": (
                isokinetic_velocity_filter_alpha if isokinetic_velocity_filter_alpha is not None else self.isokinetic_velocity_filter_alpha
            ),
            "max_extension_force_taper_m": max_extension_force_taper_m if max_extension_force_taper_m is not None else self.max_extension_force_taper_m,
            "position_guard_warning_turns": position_guard_warning_turns if position_guard_warning_turns is not None else self.position_guard_warning_turns,
            "position_guard_hard_turns": position_guard_hard_turns if position_guard_hard_turns is not None else self.position_guard_hard_turns,
        }

        if new["letgo_velocity_turns_s"] <= 0:
            raise ValueError(f"letgo_velocity_turns_s must be positive, got {new['letgo_velocity_turns_s']!r}")
        if new["letgo_debounce_samples"] < 1:
            raise ValueError(f"letgo_debounce_samples must be at least 1, got {new['letgo_debounce_samples']!r}")
        if new["hold_duration_s"] < 0:
            raise ValueError(f"hold_duration_s must be non-negative, got {new['hold_duration_s']!r}")
        if new["force_ramp_in_s"] <= 0:
            raise ValueError(f"force_ramp_in_s must be positive, got {new['force_ramp_in_s']!r}")
        if new["force_ramp_out_s"] <= 0:
            raise ValueError(f"force_ramp_out_s must be positive, got {new['force_ramp_out_s']!r}")
        if new["isokinetic_governor_gain"] < 0:
            raise ValueError(f"isokinetic_governor_gain must be non-negative, got {new['isokinetic_governor_gain']!r}")
        if not (0 < new["isokinetic_velocity_filter_alpha"] <= 1):
            raise ValueError(
                f"isokinetic_velocity_filter_alpha must be in (0, 1], got {new['isokinetic_velocity_filter_alpha']!r}"
            )
        if new["max_extension_force_taper_m"] <= 0:
            raise ValueError(f"max_extension_force_taper_m must be positive, got {new['max_extension_force_taper_m']!r}")
        if new["position_guard_warning_turns"] <= 0:
            raise ValueError(f"position_guard_warning_turns must be positive, got {new['position_guard_warning_turns']!r}")
        if new["position_guard_hard_turns"] <= 0:
            raise ValueError(f"position_guard_hard_turns must be positive, got {new['position_guard_hard_turns']!r}")
        if new["position_guard_hard_turns"] < new["position_guard_warning_turns"]:
            raise ValueError(
                f"position_guard_hard_turns ({new['position_guard_hard_turns']!r}) must be >= "
                f"position_guard_warning_turns ({new['position_guard_warning_turns']!r}) -- the warning "
                f"tier must trip before, not after, the hard tier."
            )

        for key, value in new.items():
            setattr(self, key, value)
        self._save_settings()

    def set_power_limits(
        self,
        force_max_n: Optional[float] = None,
        regen_power_budget_w: Optional[float] = None,
    ) -> None:
        """Live-adjustable hardware safety ceilings (added 18 Aug 2026 -- see
        module docstring for why this differs from set_force_settings()
        above). Any subset may be updated at once, omitted ones left as-is,
        validated together like every other setter here.

        force_max_n is bounded above by the structural ceiling implied by
        this board's current_lim/torque_constant/spool_radius (mirrors
        _TORQUE_LIMIT_NM in core/hardware/odrive_hw.py) -- this is the one
        thing standing between "live-adjustable" and "can be set to a
        physically nonsensical value the motor can never actually deliver,"
        so it stays enforced even though the other bound in this method
        (regen_power_budget_w) doesn't have an equivalent computed limit."""
        new_force_max_n = force_max_n if force_max_n is not None else self.force_max_n
        new_regen_budget_w = regen_power_budget_w if regen_power_budget_w is not None else self.regen_power_budget_w

        if new_force_max_n <= 0:
            raise ValueError(f"force_max_n must be positive, got {new_force_max_n!r}")
        structural_ceiling_n = (
            board_constants.MOTOR_CURRENT_LIM * board_constants.MOTOR_TORQUE_CONSTANT / board_constants.SPOOL_RADIUS_M
        )
        if new_force_max_n > structural_ceiling_n:
            raise ValueError(
                f"force_max_n ({new_force_max_n!r}) exceeds the structural ceiling this board can "
                f"deliver ({structural_ceiling_n:.1f} N, from MOTOR_CURRENT_LIM * MOTOR_TORQUE_CONSTANT "
                f"/ SPOOL_RADIUS_M) -- lower the request or raise MOTOR_CURRENT_LIM in board_constants.py."
            )
        if new_regen_budget_w <= 0:
            raise ValueError(f"regen_power_budget_w must be positive, got {new_regen_budget_w!r}")

        self.force_max_n = new_force_max_n
        self.regen_power_budget_w = new_regen_budget_w
        self._save_settings()

    def set_train_settings(
        self,
        max_extension_enforced: Optional[bool] = None,
        home_guard_enforced: Optional[bool] = None,
        telemetry_buffer_s: Optional[float] = None,
        resistance_display_unit_kg: Optional[bool] = None,
    ) -> None:
        """Train tab settings (train_tab_build_spec.md §1/§3): same subset-
        update/validate-together/persist pattern as set_homing_settings/
        set_force_settings. `max_extension_enforced`/`home_guard_enforced`
        independently scope the runtime range guard's two sides to TrainMode
        only (split 25 July 2026 -- a session left the range on the home
        side while only max-extension enforcement had been disabled, and a
        single combined toggle can't express "relax one side, keep the
        other"). ExerciseMode's own runtime guard is untouched by either
        flag.

        `resistance_display_unit_kg` (item 2, 5 Aug 2026) is display-only --
        it never changes what unit force is stored/evaluated in
        (core/cable/train_profiles.py stays Newtons throughout); it only
        tells the frontend which unit to show/accept in the Train tab's
        profile builder (and anywhere else resistance is presented to a
        user, not a developer)."""
        new_max_enforced = self.train_max_extension_enforced if max_extension_enforced is None else bool(max_extension_enforced)
        new_home_enforced = self.train_home_guard_enforced if home_guard_enforced is None else bool(home_guard_enforced)
        new_buffer_s = self.train_telemetry_buffer_s if telemetry_buffer_s is None else telemetry_buffer_s
        new_resistance_unit_kg = (
            self.resistance_display_unit_kg if resistance_display_unit_kg is None else bool(resistance_display_unit_kg)
        )

        if isinstance(new_buffer_s, bool) or not isinstance(new_buffer_s, (int, float)) or new_buffer_s <= 0:
            raise ValueError(f"telemetry_buffer_s must be a positive number, got {new_buffer_s!r}")

        self.train_max_extension_enforced = new_max_enforced
        self.train_home_guard_enforced = new_home_enforced
        self.train_telemetry_buffer_s = float(new_buffer_s)
        self.resistance_display_unit_kg = new_resistance_unit_kg
        self._save_settings()

    def _load_settings(self) -> dict:
        data = {}
        try:
            with open(self._sidecar_path) as f:
                data = json.load(f)
        except FileNotFoundError:
            pass
        except Exception:
            log.exception("Failed to load %s; using board_constants defaults", self._sidecar_path)
            data = {}
        settings = {key: float(data[key]) if key in data else default() for key, default in _PERSISTED_DEFAULTS.items()}
        # Optional, unlike everything in _PERSISTED_DEFAULTS above -- "not yet
        # calibrated" (None) is a real, common state, not a missing-key
        # fallback to a board_constants default (see set_max()/latch_home()).
        raw_max_length = data.get("max_extension_length_m")
        settings["max_extension_length_m"] = float(raw_max_length) if raw_max_length is not None else None
        return settings

    def _save_settings(self) -> None:
        self._sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: getattr(self, key) for key in _PERSISTED_DEFAULTS}
        payload["max_extension_length_m"] = self.max_extension_length_m
        tmp = self._sidecar_path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f)
        tmp.replace(self._sidecar_path)

    def _load_growth_points(self) -> List[Tuple[float, float]]:
        """Separate sidecar from _load_settings above: growth points are a
        list of (turns, length) pairs, not a flat float, so they don't fit
        the _PERSISTED_DEFAULTS float-only mechanism -- same
        load-tolerant-of-missing/corrupt-file behavior as that one, just a
        dedicated small file so that well-tested path stays untouched."""
        try:
            with open(self._growth_sidecar_path) as f:
                data = json.load(f)
            return [(float(t), float(length_m)) for t, length_m in data.get("points", [])]
        except FileNotFoundError:
            return []
        except Exception:
            log.exception("Failed to load %s; starting with no spool-growth calibration", self._growth_sidecar_path)
            return []

    def _save_growth_points(self) -> None:
        self._growth_sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"points": [[t, length_m] for t, length_m in self.spool_growth_points]}
        tmp = self._growth_sidecar_path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f)
        tmp.replace(self._growth_sidecar_path)

    def _load_torque_calibration_points(self) -> List[TorqueCalibrationPoint]:
        """Own dedicated sidecar, same load-tolerant-of-missing/corrupt-file
        shape as _load_growth_points() above -- a list of calibration
        points doesn't fit the float-only _PERSISTED_DEFAULTS mechanism.
        Points from before the direction-aware model (21 Aug 2026, see
        torque_calibration.py's module docstring) have no "direction" key --
        they were sourced from a static hold, which the new model has no
        equivalent line for, so they can't be migrated. Skipped individually
        (not treated as a whole-file corruption) so a sidecar with a mix of
        old and new-format points still loads whatever's usable."""
        try:
            with open(self._torque_calibration_sidecar_path) as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except Exception:
            log.exception(
                "Failed to load %s; starting with no torque calibration", self._torque_calibration_sidecar_path
            )
            return []

        points = []
        for p in data.get("points", []):
            try:
                points.append(
                    TorqueCalibrationPoint(
                        known_weight_kg=float(p["known_weight_kg"]),
                        raw_torque_nm=float(p["raw_torque_nm"]),
                        r_eff_m=float(p["r_eff_m"]),
                        direction=p["direction"],
                    )
                )
            except (KeyError, ValueError, TypeError):
                log.warning(
                    "Skipping torque calibration point with no/invalid direction (pre-21-Aug-2026 "
                    "static-hold format, no longer supported) in %s: %r",
                    self._torque_calibration_sidecar_path,
                    p,
                )
        return points

    def _save_torque_calibration_points(self) -> None:
        self._torque_calibration_sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "points": [
                {
                    "known_weight_kg": p.known_weight_kg,
                    "raw_torque_nm": p.raw_torque_nm,
                    "r_eff_m": p.r_eff_m,
                    "direction": p.direction,
                }
                for p in self.torque_calibration_points
            ]
        }
        tmp = self._torque_calibration_sidecar_path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f)
        tmp.replace(self._torque_calibration_sidecar_path)
