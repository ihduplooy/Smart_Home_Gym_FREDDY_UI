"""CSV telemetry logger. Plain stdlib csv — no pandas dependency in core/.

One row per telemetry tick while a session runs. Auto-started on
ControlSession.start(), closed on stop(). Flushes at least once a second so a
crash doesn't lose the run.

Session 3 amendment (spec §6): two columns appended after `torque_est_nm` —
`phase`, `rep_count` — populated during profile runs, empty strings for
velocity/torque runs (this amends Session 2's "exact columns" clause; see
docs/decisions.md).

Exercise tab Layer A amendment (exercise_tab_build_spec_layerA.md §7): one
more column appended, `cable_length_m` — populated during Exercise runs once
homed, empty string otherwise (un-homed Exercise runs, and every other
mode). Same additive pattern as phase/rep_count above; existing logs and the
CSV reference tables in the manuals stay readable (columns only ever
appended, never reordered/removed).

Exercise tab Layer B amendment (exercise_tab_build_spec_layerB.md §11): six
more columns appended -- `commanded_force_n`, `estimated_force_n`,
`cable_velocity_m_s`, `regen_power_w`, `force_state`, `power_limiter_active`
-- populated during Force runs, empty strings for every other mode. The
spec explicitly calls for capturing commanded-vs-estimated force together,
not just one, since this CSV is the primary record for anything the project
eventually reports.

Testing tab amendment (Testing tab Build Spec §3): seven more columns
appended -- `experiment_state`, `position_m`, `velocity_m_s`,
`commanded_torque_nm`, `bus_voltage_v`, `estimated_power_w`,
`target_position_m` -- populated during Testing-tab experiment runs, empty
strings for every other mode. No separate `measured_current_a` column: the
spec's "motor phase current if available" channel is already served by the
existing `current_iq_a` column (this project only ever reads phase current,
never bus current -- see core/hardware/interface.py's TelemetrySample
docstring), so it isn't duplicated here.

GYM dashboard amendment (resistance-modes sub-phase 5): one more column
appended -- `total_work_j` -- populated during Train/GYM runs (the running
mechanical-work accumulator core/cable/train_mode.py's tick() now keeps),
empty string for every other mode. `rep_count` above, reserved since the
original session-3 spec but never populated by TrainMode until this same
sub-phase, now gets real values too -- no new column needed for that one,
same additive pattern either way.
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
    "phase",
    "rep_count",
    "cable_length_m",
    "commanded_force_n",
    "estimated_force_n",
    "cable_velocity_m_s",
    "regen_power_w",
    "force_state",
    "power_limiter_active",
    "experiment_state",
    "position_m",
    "velocity_m_s",
    "commanded_torque_nm",
    "bus_voltage_v",
    "estimated_power_w",
    "target_position_m",
    "total_work_j",
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

    def log_sample(
        self,
        sample: TelemetrySample,
        mode: str,
        target: float,
        phase: str = "",
        rep_count="",
        cable_length_m="",
        commanded_force_n="",
        estimated_force_n="",
        cable_velocity_m_s="",
        regen_power_w="",
        force_state="",
        power_limiter_active="",
        experiment_state="",
        position_m="",
        velocity_m_s="",
        commanded_torque_nm="",
        bus_voltage_v="",
        estimated_power_w="",
        target_position_m="",
        total_work_j="",
    ) -> None:
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
            phase,
            rep_count,
            cable_length_m,
            commanded_force_n,
            estimated_force_n,
            cable_velocity_m_s,
            regen_power_w,
            force_state,
            power_limiter_active,
            experiment_state,
            position_m,
            velocity_m_s,
            commanded_torque_nm,
            bus_voltage_v,
            estimated_power_w,
            target_position_m,
            total_work_j,
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
