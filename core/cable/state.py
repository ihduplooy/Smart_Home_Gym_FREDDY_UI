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

This module is still hardware-free/Flask-free (only reads config.
board_constants and a local JSON file), but it is NOT pure/stateless like
geometry.py, homing.py, limits.py -- it is the one stateful piece in
core/cable/, by design.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from config import board_constants

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SIDECAR_PATH = _REPO_ROOT / "config" / "spool_calibration.json"

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
}


class CableState:
    def __init__(self, sidecar_path: Optional[Path] = None):
        self._sidecar_path = sidecar_path if sidecar_path is not None else _DEFAULT_SIDECAR_PATH
        settings = self._load_settings()
        self.k = settings["k"]
        self.r0 = settings["r0"]
        self.homing_current_threshold_a = settings["homing_current_threshold_a"]
        self.homing_velocity_turns_s = settings["homing_velocity_turns_s"]
        self.homing_current_limit_a = settings["homing_current_limit_a"]
        self.calib_hold_force_n = settings["calib_hold_force_n"]

        # In-memory only -- see module docstring.
        self.home_turns: Optional[float] = None
        self.max_turns: Optional[float] = None  # enforced (safety-margined)
        self.marked_max_turns: Optional[float] = None  # raw marked point, display-only

        self.homing_in_progress = False
        self.max_calibration_in_progress = False
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
        self._save_settings()

    def set_r0(self, r0: float) -> None:
        if r0 <= 0:
            raise ValueError(f"r0 (spool radius) must be positive, got {r0!r}")
        self.r0 = r0
        self._save_settings()

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
