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
file header admitted was untested. Deliberately NOT extended to hard
hardware safety ceilings (FORCE_MAX_N, REGEN_POWER_BUDGET_W,
MOTOR_CURRENT_LIM, the DC bus regen limits) -- those stay fixed
board_constants, since they're tied to physical component ratings (the
brake resistor's wattage, the board's current limit) rather than to feel or
per-spool calibration, and raising them live could put real hardware at
risk.

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

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SIDECAR_PATH = _REPO_ROOT / "config" / "spool_calibration.json"
_DEFAULT_GROWTH_SIDECAR_PATH = _REPO_ROOT / "config" / "spool_growth_calibration.json"

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
    "test_initial_torque_nm": lambda: board_constants.TEST_INITIAL_TORQUE_NM_DEFAULT,
    "test_torque_ramp_rate_nm_per_s": lambda: board_constants.TEST_TORQUE_RAMP_RATE_NM_PER_S_DEFAULT,
    "test_movement_threshold_m_per_s": lambda: board_constants.TEST_MOVEMENT_THRESHOLD_M_PER_S_DEFAULT,
    "test_hold_deadband_m": lambda: board_constants.TEST_HOLD_DEADBAND_M_DEFAULT,
    "test_hold_gain": lambda: board_constants.TEST_HOLD_GAIN_DEFAULT,
    "test_max_torque_nm": lambda: board_constants.TEST_MAX_TORQUE_NM_DEFAULT,
    "test_max_duration_s": lambda: board_constants.TEST_MAX_DURATION_S_DEFAULT,
}


class CableState:
    def __init__(self, sidecar_path: Optional[Path] = None, growth_sidecar_path: Optional[Path] = None):
        self._sidecar_path = sidecar_path if sidecar_path is not None else _DEFAULT_SIDECAR_PATH
        self._growth_sidecar_path = growth_sidecar_path if growth_sidecar_path is not None else _DEFAULT_GROWTH_SIDECAR_PATH
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
        self.test_initial_torque_nm = settings["test_initial_torque_nm"]
        self.test_torque_ramp_rate_nm_per_s = settings["test_torque_ramp_rate_nm_per_s"]
        self.test_movement_threshold_m_per_s = settings["test_movement_threshold_m_per_s"]
        self.test_hold_deadband_m = settings["test_hold_deadband_m"]
        self.test_hold_gain = settings["test_hold_gain"]
        self.test_max_torque_nm = settings["test_max_torque_nm"]
        self.test_max_duration_s = settings["test_max_duration_s"]

        # Experimental multi-point spool-growth calibration (turns_from_home,
        # length_m) pairs -- persisted separately from the float-only sidecar
        # above since these are tuples, not floats (see _load_growth_points/
        # _save_growth_points). Empty by default: falls back to the plain
        # r0+k*theta model below, completely unchanged from before this
        # existed.
        self.spool_growth_points: List[Tuple[float, float]] = self._load_growth_points()
        self.spool_geometry = geometry.SpoolGeometry(self.r0, self.k, self.spool_growth_points)

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

    @property
    def is_homed(self) -> bool:
        return self.home_turns is not None

    @property
    def has_max(self) -> bool:
        return self.max_turns is not None

    def latch_home(self, position_turns: float) -> None:
        """A fresh home reference invalidates any previously-set max: max was
        marked relative to the old (now-discarded) reference, and re-homing
        only ever happens because something about the physical setup may
        have changed (cable slip, reattachment) -- the old marking can't be
        trusted to still be valid either."""
        self.home_turns = position_turns
        self.max_turns = None
        self.marked_max_turns = None

    def set_max(self, marked_turns: float, enforced_turns: float) -> None:
        self.marked_max_turns = marked_turns
        self.max_turns = enforced_turns

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

    def set_train_settings(
        self,
        max_extension_enforced: Optional[bool] = None,
        home_guard_enforced: Optional[bool] = None,
        telemetry_buffer_s: Optional[float] = None,
    ) -> None:
        """Train tab settings (train_tab_build_spec.md §1/§3): same subset-
        update/validate-together/persist pattern as set_homing_settings/
        set_force_settings. `max_extension_enforced`/`home_guard_enforced`
        independently scope the runtime range guard's two sides to TrainMode
        only (split 25 July 2026 -- a session left the range on the home
        side while only max-extension enforcement had been disabled, and a
        single combined toggle can't express "relax one side, keep the
        other"). ExerciseMode's own runtime guard is untouched by either
        flag."""
        new_max_enforced = self.train_max_extension_enforced if max_extension_enforced is None else bool(max_extension_enforced)
        new_home_enforced = self.train_home_guard_enforced if home_guard_enforced is None else bool(home_guard_enforced)
        new_buffer_s = self.train_telemetry_buffer_s if telemetry_buffer_s is None else telemetry_buffer_s

        if isinstance(new_buffer_s, bool) or not isinstance(new_buffer_s, (int, float)) or new_buffer_s <= 0:
            raise ValueError(f"telemetry_buffer_s must be a positive number, got {new_buffer_s!r}")

        self.train_max_extension_enforced = new_max_enforced
        self.train_home_guard_enforced = new_home_enforced
        self.train_telemetry_buffer_s = float(new_buffer_s)
        self._save_settings()

    def set_test_settings(
        self,
        initial_torque_nm: Optional[float] = None,
        torque_ramp_rate_nm_per_s: Optional[float] = None,
        movement_threshold_m_per_s: Optional[float] = None,
        hold_deadband_m: Optional[float] = None,
        hold_gain: Optional[float] = None,
        max_torque_nm: Optional[float] = None,
        max_duration_s: Optional[float] = None,
    ) -> None:
        """Testing tab (Testing tab Build Spec §2.1) persisted defaults --
        same subset-update/validate-together/persist pattern as
        set_force_settings/set_train_settings. These are only the *defaults*
        a new experiment's config form pre-fills from -- a per-run
        ExperimentConfig snapshots its own values at configure() time, so
        editing these never touches an experiment already in progress."""
        new = {
            "initial_torque_nm": initial_torque_nm if initial_torque_nm is not None else self.test_initial_torque_nm,
            "torque_ramp_rate_nm_per_s": torque_ramp_rate_nm_per_s if torque_ramp_rate_nm_per_s is not None else self.test_torque_ramp_rate_nm_per_s,
            "movement_threshold_m_per_s": movement_threshold_m_per_s if movement_threshold_m_per_s is not None else self.test_movement_threshold_m_per_s,
            "hold_deadband_m": hold_deadband_m if hold_deadband_m is not None else self.test_hold_deadband_m,
            "hold_gain": hold_gain if hold_gain is not None else self.test_hold_gain,
            "max_torque_nm": max_torque_nm if max_torque_nm is not None else self.test_max_torque_nm,
            "max_duration_s": max_duration_s if max_duration_s is not None else self.test_max_duration_s,
        }

        if new["torque_ramp_rate_nm_per_s"] <= 0:
            raise ValueError(f"torque_ramp_rate_nm_per_s must be positive, got {new['torque_ramp_rate_nm_per_s']!r}")
        if new["movement_threshold_m_per_s"] <= 0:
            raise ValueError(f"movement_threshold_m_per_s must be positive, got {new['movement_threshold_m_per_s']!r}")
        if new["hold_deadband_m"] <= 0:
            raise ValueError(f"hold_deadband_m must be positive, got {new['hold_deadband_m']!r}")
        if new["hold_gain"] < 0:
            raise ValueError(f"hold_gain must be non-negative, got {new['hold_gain']!r}")
        if new["max_torque_nm"] <= 0:
            raise ValueError(f"max_torque_nm must be positive, got {new['max_torque_nm']!r}")
        if new["max_duration_s"] <= 0:
            raise ValueError(f"max_duration_s must be positive, got {new['max_duration_s']!r}")
        if abs(new["initial_torque_nm"]) > new["max_torque_nm"]:
            raise ValueError(
                f"initial_torque_nm ({new['initial_torque_nm']!r}) must not exceed "
                f"max_torque_nm ({new['max_torque_nm']!r})."
            )

        self.test_initial_torque_nm = new["initial_torque_nm"]
        self.test_torque_ramp_rate_nm_per_s = new["torque_ramp_rate_nm_per_s"]
        self.test_movement_threshold_m_per_s = new["movement_threshold_m_per_s"]
        self.test_hold_deadband_m = new["hold_deadband_m"]
        self.test_hold_gain = new["hold_gain"]
        self.test_max_torque_nm = new["max_torque_nm"]
        self.test_max_duration_s = new["max_duration_s"]
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
        return {key: float(data[key]) if key in data else default() for key, default in _PERSISTED_DEFAULTS.items()}

    def _save_settings(self) -> None:
        self._sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: getattr(self, key) for key in _PERSISTED_DEFAULTS}
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
