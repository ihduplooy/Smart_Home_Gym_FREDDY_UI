"""CSV telemetry logger. Plain stdlib csv — no pandas dependency in core/.

One row per telemetry tick while a session runs. Auto-started on
ControlSession.start(), closed on stop(). Flushes at least once a second so a
crash doesn't lose the run.
"""

import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.hardware.interface import TelemetrySample

COLUMNS = [
    "timestamp_iso",
    "t_rel_s",
    "mode",
    "target",
    "position_turns",
    "velocity_turns_s",
    "current_iq_a",
    "torque_est_nm",
]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FLUSH_INTERVAL_S = 1.0


def _default_logs_dir() -> Path:
    return _REPO_ROOT / "logs"


class CsvLogger:
    def __init__(self, mode: str, hardware_source: str, logs_dir: Optional[Path] = None):
        self.mode = mode
        self.hardware_source = hardware_source
        self._logs_dir = logs_dir if logs_dir is not None else _default_logs_dir()
        self._file = None
        self._writer = None
        self._t0: Optional[float] = None
        self._last_flush = 0.0
        self.path: Optional[Path] = None

    def open(self) -> Path:
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"telemetry_{ts}_{self.mode}_{self.hardware_source}.csv"
        self.path = self._logs_dir / filename
        self._file = open(self.path, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(COLUMNS)
        self._file.flush()
        self._t0 = time.monotonic()
        self._last_flush = time.monotonic()
        return self.path

    def log_sample(self, sample: TelemetrySample, mode: str, target: float) -> None:
        if self._writer is None or self._t0 is None:
            raise RuntimeError("CsvLogger.log_sample() called before open()")
        self._writer.writerow([
            datetime.now().isoformat(),
            sample.t - self._t0,
            mode,
            target,
            sample.position,
            sample.velocity,
            sample.current_iq,
            sample.torque_est,
        ])
        now = time.monotonic()
        if now - self._last_flush >= _FLUSH_INTERVAL_S:
            self._file.flush()
            self._last_flush = now

    def close(self) -> None:
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None
            self._writer = None
