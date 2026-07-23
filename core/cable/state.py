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
  - k: persisted to a small JSON sidecar (config/spool_calibration.json,
    gitignored -- it's bench/physical-spool-specific state, not source),
    loaded at construction, written back only on an explicit, successful
    calibration.

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


class CableState:
    def __init__(self, sidecar_path: Optional[Path] = None):
        self._sidecar_path = sidecar_path if sidecar_path is not None else _DEFAULT_SIDECAR_PATH
        self.r0 = board_constants.SPOOL_RADIUS_M
        self.k = self._load_k()

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
        touch k (a physical property of the spool, not a session
        artifact)."""
        self.home_turns = None
        self.max_turns = None
        self.marked_max_turns = None

    def set_k(self, k: float) -> None:
        self.k = k
        self._save_k()

    def _load_k(self) -> float:
        try:
            with open(self._sidecar_path) as f:
                data = json.load(f)
            return float(data["k"])
        except FileNotFoundError:
            return board_constants.SPOOL_CORRECTION_K_DEFAULT
        except Exception:
            log.exception("Failed to load %s; using default k", self._sidecar_path)
            return board_constants.SPOOL_CORRECTION_K_DEFAULT

    def _save_k(self) -> None:
        self._sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._sidecar_path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump({"k": self.k}, f)
        tmp.replace(self._sidecar_path)
