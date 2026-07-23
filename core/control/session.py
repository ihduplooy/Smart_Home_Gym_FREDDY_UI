"""ControlSession — the one stateful orchestrator. Owns the active
HardwareInterface, the active mode, a background telemetry thread, a ring
buffer of recent samples (for the GUI's live readout), and the CSV logger
lifecycle.

Safety behaviours (non-negotiable, see core/tests/):
  - stop() always reaches the hardware stop() even if the telemetry thread is
    wedged: it reads the hardware reference directly and calls stop() on it
    before touching the session lock, so a hung get_state() call never blocks
    the emergency path.
  - Any exception in the telemetry loop stops the hardware and marks the
    session errored, never a silent dead loop. This also covers Session 3's
    ProfileMode: mode_handler.tick() (which calls the active profile's
    compute_torque()) runs inside the same try/except, so a profile that
    raises is indistinguishable from a hardware read failure here — same
    auto-stop path, no special-casing needed.
  - get_errors() returning non-empty during a run triggers an automatic stop,
    surfaced in status().
  - Starting a new session while one is running is refused.
  - Backend process exit (atexit) attempts a final stop().

Session 3 adds resistance profiles as a third mode (core.control.modes.ProfileMode)
that runs an outer loop *inside* this same tick via BaseMode.tick() — no second
thread, no second rate (spec §3). See modes.py for the extension-point hooks
(tick/csv_log_name/status_target) that make this generic across all three modes.
"""

import atexit
import logging
import threading
from collections import deque
from dataclasses import asdict
from typing import Callable, Dict, List, Optional

from core.hardware.interface import HardwareInterface, TelemetrySample
from core.hardware.odrive_hw import OdriveHardware
from core.hardware.sim_hw import SimHardware
from core.telemetry.csv_logger import CsvLogger

from .modes import MODES_BY_NAME, BaseMode

log = logging.getLogger(__name__)

# Single place for the telemetry sampling rate (spec: 50 Hz target).
TELEMETRY_HZ = 50.0
TELEMETRY_INTERVAL_S = 1.0 / TELEMETRY_HZ

# ~10s of history at 50 Hz — enough for the GUI's live chart window.
RING_BUFFER_SIZE = 500

HARDWARE_SOURCES = ("sim", "real")

DEFAULT_HARDWARE_FACTORIES: Dict[str, Callable[[], HardwareInterface]] = {
    "sim": SimHardware,
    "real": OdriveHardware,
}


class ControlSession:
    def __init__(
        self,
        hardware_source: str = "sim",
        hardware_factories: Optional[Dict[str, Callable[[], HardwareInterface]]] = None,
        mode_factories: Optional[Dict[str, Callable[[], BaseMode]]] = None,
        register_atexit: bool = True,
    ):
        if hardware_source not in HARDWARE_SOURCES:
            raise ValueError(f"Unknown hardware source: {hardware_source}")
        self._hardware_factories = hardware_factories or DEFAULT_HARDWARE_FACTORIES
        self._hardware_source = hardware_source
        # Overridable the same way hardware_factories is (Exercise tab, spec
        # exercise_tab_build_spec_layerA.md §2.2/§6): ExerciseMode needs a
        # CableState injected at construction to hold home/max across a
        # start()/stop() cycle (this session destroys _mode_handler on
        # stop(), but the spec requires "Reset Position" to work on a still-
        # valid home while idle) -- mode_cls() alone can't do that. See
        # docs/decisions.md.
        self._mode_factories = mode_factories or MODES_BY_NAME

        self._lock = threading.RLock()
        self._hardware: Optional[HardwareInterface] = None
        self._mode_handler: Optional[BaseMode] = None
        self._mode_name: Optional[str] = None
        self._target: Optional[float] = None
        self._running = False
        self._errored = False
        self._error_message: Optional[str] = None
        self._last_errors: List[str] = []

        self._ring: deque = deque(maxlen=RING_BUFFER_SIZE)
        self._logger: Optional[CsvLogger] = None
        self._last_extra: Dict = {}

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        if register_atexit:
            atexit.register(self._atexit_stop)

    # ---- hardware source selection ----

    def get_hardware_source(self) -> str:
        return self._hardware_source

    def set_hardware_source(self, source: str) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("Cannot change hardware source while a session is running")
            if source not in HARDWARE_SOURCES:
                raise ValueError(f"Unknown hardware source: {source}")
            self._hardware_source = source

    # ---- lifecycle ----

    def start(self, mode: str, target) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("A control session is already running")

            mode_factory = self._mode_factories.get(mode)
            if mode_factory is None:
                raise ValueError(f"Unknown mode: {mode!r} (expected one of {list(self._mode_factories)})")
            mode_handler = mode_factory()
            target_value = mode_handler.validate_target(target)

            factory = self._hardware_factories[self._hardware_source]
            hardware = factory()
            hardware.connect()  # may raise (e.g. "No ODrive device found") — propagates to caller
            try:
                hardware.set_mode(mode_handler.hardware_mode)
                mode_handler.apply_target(hardware, target_value)
            except Exception:
                hardware.stop()
                hardware.disconnect()
                raise

            logger = CsvLogger(mode=mode_handler.csv_log_name(mode), hardware_source=self._hardware_source)
            logger.open()

            self._hardware = hardware
            self._mode_handler = mode_handler
            self._mode_name = mode
            self._target = mode_handler.status_target(target_value)
            self._errored = False
            self._error_message = None
            self._last_errors = []
            self._last_extra = {}
            self._ring.clear()
            self._logger = logger

            self._stop_event.clear()
            self._running = True
            thread = threading.Thread(target=self._telemetry_loop, name="control-telemetry", daemon=True)
            self._thread = thread
            thread.start()

    def set_target(self, value) -> None:
        with self._lock:
            if not self._running or self._mode_handler is None or self._hardware is None:
                raise RuntimeError("No control session running")
            target_value = self._mode_handler.validate_target(value)
            self._mode_handler.apply_target(self._hardware, target_value)
            self._target = self._mode_handler.status_target(target_value)

    def stop(self) -> None:
        """Safe to call at any time, from any thread, repeatedly. Reaches the
        hardware stop() first and without the lock, so a wedged telemetry
        thread (stuck inside hardware.get_state()) can never block it."""
        hardware = self._hardware
        if hardware is not None:
            try:
                hardware.stop()
            except Exception:
                log.exception("hardware.stop() raised during ControlSession.stop()")

        self._stop_event.set()

        current = threading.current_thread()
        acquired = self._lock.acquire(timeout=2.0)
        try:
            self._running = False
            thread = self._thread
            if self._logger is not None:
                try:
                    self._logger.close()
                except Exception:
                    log.exception("Failed to close CSV logger")
                self._logger = None
            if hardware is not None:
                try:
                    hardware.disconnect()
                except Exception:
                    log.exception("hardware.disconnect() raised during stop()")
            self._hardware = None
            self._mode_handler = None
        finally:
            if acquired:
                self._lock.release()

        if thread is not None and thread is not current:
            thread.join(timeout=2.0)
        if self._thread is thread:
            self._thread = None

    def _atexit_stop(self) -> None:
        try:
            self.stop()
        except Exception:
            log.exception("stop() during atexit raised")

    # ---- telemetry loop ----

    def _telemetry_loop(self) -> None:
        while not self._stop_event.is_set():
            hardware = self._hardware
            mode_handler = self._mode_handler
            if hardware is None or mode_handler is None:
                return
            try:
                sample = hardware.get_state()
                extra = mode_handler.tick(hardware, sample)
                errors = hardware.get_errors()
            except Exception as e:
                log.exception("Telemetry loop crashed; auto-stopping")
                self._errored = True
                self._error_message = f"Telemetry loop error: {e}"
                self.stop()
                return

            with self._lock:
                self._ring.append(sample)
                self._last_errors = errors
                self._last_extra = extra
                mode_name = self._mode_name
                target = self._target

            if self._logger is not None:
                try:
                    # cable_length_m is None (not absent) while un-homed
                    # (ExerciseMode.tick()) -- distinct from "" (every other
                    # mode, key absent), both written as an empty CSV cell.
                    cable_length_m = extra.get("cable_length_m")
                    self._logger.log_sample(
                        sample,
                        mode=mode_name,
                        target=target,
                        phase=extra.get("phase", ""),
                        rep_count=extra.get("rep_count", ""),
                        cable_length_m="" if cable_length_m is None else cable_length_m,
                    )
                except Exception:
                    log.exception("CSV logger write failed")

            if errors:
                log.warning("Hardware errors detected, auto-stopping: %s", errors)
                self._errored = True
                self._error_message = "; ".join(errors)
                self.stop()
                return

            self._stop_event.wait(TELEMETRY_INTERVAL_S)

    # ---- status / telemetry read-out ----

    def status(self) -> dict:
        with self._lock:
            latest = self._ring[-1] if self._ring else None
            return {
                "running": self._running,
                "mode": self._mode_name,
                "target": self._target,
                "hardware_source": self._hardware_source,
                "errored": self._errored,
                "error_message": self._error_message,
                "errors": list(self._last_errors),
                "log_path": str(self._logger.path) if self._logger and self._logger.path else None,
                "latest_sample": asdict(latest) if latest is not None else None,
                "phase": self._last_extra.get("phase"),
                "rep_count": self._last_extra.get("rep_count"),
                # Generic passthrough of whatever the active mode's tick()
                # returned (spec exercise_tab_build_spec_layerA.md §7 wants
                # e.g. homing_state/is_homed/cable_length_m surfaced here for
                # the Exercise tab, without ControlSession needing to know
                # what those fields mean -- same mechanism phase/rep_count
                # above already use, generalised rather than duplicated
                # per new mode).
                "extra": dict(self._last_extra),
            }

    def samples_since(self, since: Optional[float] = None) -> List[TelemetrySample]:
        with self._lock:
            if since is None:
                return list(self._ring)
            return [s for s in self._ring if s.t > since]
