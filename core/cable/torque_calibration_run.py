"""Turns a completed Testing-tab position-move telemetry run (see
core/telemetry/csv_logger.py) into torque_calibration.py points, sourced
from real up/down reps holding a known weight instead of a manual static
hold. Replaces the old "hang the weight, hold it, hit calibrate" workflow
(single live snapshot at rest) -- see torque_calibration.py's module
docstring for why a static hold can't represent the two regimes (lifting,
lowering) the model actually needs to be right for.

Workflow this supports: hang a known weight, run it up-and-down for several
reps (the Testing tab's Repetitive testing sub-tab, unrelated to and
unmodified by this module), then feed the run's telemetry through
extract_calibration_points_from_run() with that known weight. Repeat at a
few different known weights (e.g. 5/10/15 kg) before fitting -- this module
only extracts points from ONE run; accumulating points across weights and
re-fitting is CableState's job (add_torque_calibration_point in
core/cable/state.py), same as it already was.

Pure math, zero project-specific imports (same convention as geometry.py/
torque_calibration.py) -- the caller (backend/app/exercise_routes.py) reads
the CSV/live samples and resolves CABLE_SIGN/r_eff itself, and passes
RunSample triples in here already in the CABLE-frame velocity convention
this module needs.
"""

from dataclasses import dataclass
from statistics import mean
from typing import Dict, List, Optional, Tuple

from .torque_calibration import TorqueCalibrationPoint

# Below this |cable-frame velocity|, a sample isn't part of a deliberate rep
# leg -- it's sitting at a turnaround (top/bottom of a rep) or a static
# moment before/after the run. Deliberately stricter than torque_calibration
# .py's STATIC_VELOCITY_DEADBAND_TURNS_S (0.02): that constant governs which
# fitted line a live control decision falls back to when it has no better
# option, this one governs what's admitted into the data used to FIT those
# lines in the first place, so it's fine (better, even) for this one to be
# pickier.
DEFAULT_MIN_MOVING_VELOCITY_TURNS_S = 0.05

# A rep leg's steady-state ("cruise") portion is the samples within this
# fraction of that leg's own peak |velocity| -- the flat top of the
# trapezoidal velocity profile a position move commands (accel ramp / cruise
# / decel ramp), which is where the raw torque reading is representative of
# actually moving at speed rather than the accel/decel transients either
# side of it.
DEFAULT_PLATEAU_FRACTION_OF_PEAK = 0.9


@dataclass
class RunSample:
    """One telemetry row reduced to what this module needs.
    `cable_velocity_turns_s` MUST already be in the CABLE-frame sign
    convention used throughout this codebase (+ = paying out/lowering,
    i.e. CABLE_SIGN * sample.velocity, not the raw motor-frame velocity) --
    direction classification below depends on it."""

    cable_velocity_turns_s: float
    raw_torque_nm: float
    r_eff_m: float


@dataclass
class DirectionCalibrationResult:
    """One direction's ("up" or "down") result from a processed run -- the
    candidate point plus enough per-rep detail (Developer Visibility
    convention, same as TorqueCalibration.describe()) that a human can
    sanity-check it before it's inserted into CableState."""

    direction: str
    point: TorqueCalibrationPoint
    rep_count: int
    per_rep_raw_torque_nm: List[float]


def _split_into_runs(
    samples: List[RunSample], min_moving_velocity_turns_s: float
) -> List[Tuple[int, List[RunSample]]]:
    """Contiguous stretches of same-sign, above-threshold cable velocity --
    one entry per up/down leg of a rep, separated by the near-zero-velocity
    turnarounds between them. Returns (sign, samples) pairs, sign in
    {-1, +1}."""
    runs: List[Tuple[int, List[RunSample]]] = []
    current: List[RunSample] = []
    current_sign = 0
    for s in samples:
        sign = 0 if abs(s.cable_velocity_turns_s) < min_moving_velocity_turns_s else (1 if s.cable_velocity_turns_s > 0 else -1)
        if sign == 0 or sign != current_sign:
            if current:
                runs.append((current_sign, current))
            current = []
            current_sign = sign
        if sign != 0:
            current.append(s)
    if current:
        runs.append((current_sign, current))
    return runs


def _plateau(run_samples: List[RunSample], plateau_fraction_of_peak: float) -> List[RunSample]:
    peak = max(abs(s.cable_velocity_turns_s) for s in run_samples)
    if peak == 0.0:
        return []
    threshold = plateau_fraction_of_peak * peak
    return [s for s in run_samples if abs(s.cable_velocity_turns_s) >= threshold]


def extract_calibration_points_from_run(
    samples: List[RunSample],
    known_weight_kg: float,
    min_moving_velocity_turns_s: float = DEFAULT_MIN_MOVING_VELOCITY_TURNS_S,
    plateau_fraction_of_peak: float = DEFAULT_PLATEAU_FRACTION_OF_PEAK,
) -> Dict[str, Optional[DirectionCalibrationResult]]:
    """Extracts up to one calibration point per direction from `samples`
    (one run's telemetry, in order). Each rep leg contributes its OWN
    average (steady-state raw torque, steady-state r_eff) first, and those
    per-rep averages are then averaged again across every rep in that
    direction -- so a long or noisy leg can't outweigh a short one, matching
    "hang a known weight, run N reps, use the average of that" rather than
    pooling every sample equally.

    Returns {"up": result_or_None, "down": result_or_None} -- None for a
    direction with no qualifying rep legs in this run (e.g. a run that never
    actually reached cruise velocity either way)."""
    by_direction: Dict[str, List[List[RunSample]]] = {"up": [], "down": []}
    for sign, run_samples in _split_into_runs(samples, min_moving_velocity_turns_s):
        plateau_samples = _plateau(run_samples, plateau_fraction_of_peak)
        if not plateau_samples:
            continue
        direction = "down" if sign > 0 else "up"
        by_direction[direction].append(plateau_samples)

    results: Dict[str, Optional[DirectionCalibrationResult]] = {"up": None, "down": None}
    for direction, reps in by_direction.items():
        if not reps:
            continue
        per_rep_raw = [mean(s.raw_torque_nm for s in rep) for rep in reps]
        per_rep_r_eff = [mean(s.r_eff_m for s in rep) for rep in reps]
        point = TorqueCalibrationPoint(
            known_weight_kg=known_weight_kg,
            raw_torque_nm=mean(per_rep_raw),
            r_eff_m=mean(per_rep_r_eff),
            direction=direction,
        )
        results[direction] = DirectionCalibrationResult(
            direction=direction, point=point, rep_count=len(reps), per_rep_raw_torque_nm=per_rep_raw
        )
    return results
