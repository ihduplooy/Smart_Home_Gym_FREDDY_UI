"""Torque/force calibration -- corrects the fixed-motor-constant torque
estimate (core/hardware/*.py's `torque_est = MOTOR_TORQUE_CONSTANT *
current_iq`) against experimentally measured points: hang a known mass, run
it through real reps, record what torque_est actually read while lifting and
while lowering. Friction and other mechanical losses make the raw estimate
systematically wrong in a way `MOTOR_TORQUE_CONSTANT` alone can't capture;
this fits a straight-line correction on top of it instead -- same "make it
explicit, don't guess, verify at the bench" spirit as this package's
spool-growth calibration (geometry.py's `build_growth_segments`).

Pure math, zero project-specific imports, same convention as geometry.py:
callers (CableState, core/cable/torque_calibration_run.py) pass in whatever
they already have.

Direction-aware model (superseded a single static-hold-sourced line 21 Aug
2026): bench data showed the raw torque estimate is NOT just a fixed
scale+offset away from the truth -- it's systematically different depending
on which way the motor is actually turning. Holding a known weight still,
lifting it, and lowering it are three different friction regimes (friction
opposes whichever way the motor is turning, so it adds to the torque needed
going up and subtracts from it going down), and a single static hold only
ever samples the "not moving" one -- neither of the two regimes that matter
during an actual rep. So this fits TWO lines, one from steady-state
"lifting"/concentric samples (cable retracting) and one from steady-state
"lowering"/eccentric samples (cable paying out), each still against the
MAGNITUDE of raw_torque_nm for the same sign-vs-magnitude reason as before
(see below). See core/cable/torque_calibration_run.py for how those
steady-state samples get extracted from a real repeated-lift run instead of
a manual static hold.

Model: corrected_magnitude = scale_dir * |raw_nm| + offset_dir, with the
sign of `raw_nm` reapplied afterward, where `dir` is "up" (lifting,
retracting) or "down" (lowering, paying out) -- i.e. this fits and corrects
the MAGNITUDE of the torque, never the sign, and picks which of the two
fitted lines to use from the CABLE-frame velocity at the moment of
correction (+ = paying out/lowering = "down", matching the `CABLE_SIGN *
sample.velocity` convention used elsewhere in this codebase -- see
core/cable/train_mode.py, core/cable/exercise_mode.py).

Near-zero velocity (STATIC_VELOCITY_DEADBAND_TURNS_S) can't be classified as
either direction -- there's no rep in progress to sample from, and Coulomb
friction is direction-indeterminate exactly at zero velocity anyway (a real
static hold could break either way). Rather than guess a sign for the
friction offset, corrected_torque_nm/raw_torque_nm_for_corrected fall back
to a STATIC blend for these cases: the average of both directions' fitted
scale (the proportional, direction-independent part of the error), with
offset forced to 0 (no friction compensation applied while not actually
moving -- see corrected_torque_nm's docstring for why).

Why magnitude, not the signed value directly: `raw_torque_nm` is a *signed*
motor-constant estimate (current_iq's sign encodes which way the motor is
turning/pushing -- meaningful for control, e.g. concentric vs eccentric or
which side of a hold), but `expected_torque_nm` (known_weight_kg * g *
r_eff_m) is always a positive magnitude -- there's no such thing as a
negative amount of weight. Fitting a line directly between a signed x and an
unsigned y bakes the sign of whatever raw values happened to be recorded
(e.g. always negative, holding against gravity in this rig's current
convention) into `scale` itself -- the fit comes out looking fine for points
sharing that sign, but is physically meaningless (and, with `scale`
negative, silently flips the sign of anything it's later applied to) for a
raw reading of the opposite sign, e.g. the other side of a hold or a
different exercise direction. Splitting sign from magnitude keeps the fit
itself physically sane (scale/offset are properties of the motor+friction,
not of which way the cable happened to be moving during calibration) while
still preserving direction for every caller that needs it for control. Note
this "sign" splitting is orthogonal to the "up"/"down" direction splitting
above -- direction picks WHICH fitted line to use, sign-vs-magnitude governs
HOW that line gets fit and re-applied.

Fit from N recorded (raw_torque_nm, expected_torque_nm, direction) points
per direction -- `expected_torque_nm` is derived physics (known_weight_kg *
g * r_eff_m at the moment of recording), `raw_torque_nm` is whatever the
hardware/software estimated at that same moment (sign included, but only
|raw_torque_nm| is used for fitting):

    0 points  -> identity (scale=1, offset=0) -- no calibration recorded
                 yet for this direction, completely unchanged behavior.
    1 point   -> scale = expected / |raw| (offset fixed at 0) -- same
                 closed-form shape as geometry.py's calibrate_k single-point
                 case; one equation can't solve for two unknowns.
    2+ points -> ordinary least-squares line through every (|raw|, expected)
                 point (both scale and offset free) -- captures a constant,
                 load-independent offset (e.g. kinetic friction) in addition
                 to a proportional error, which a single point alone can't
                 distinguish from scale.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

GRAVITY_M_S2 = 9.81

DIRECTIONS: Tuple[str, str] = ("up", "down")

# Below this |cable-frame velocity|, a sample can't be attributed to either
# direction with confidence -- see module docstring's "Near-zero velocity"
# section for why this falls back to a blended static correction rather than
# guessing a direction.
STATIC_VELOCITY_DEADBAND_TURNS_S = 0.02


@dataclass
class TorqueCalibrationPoint:
    """One recorded calibration measurement, sourced from the steady-state
    (constant-velocity) portion of a real rep -- see
    core/cable/torque_calibration_run.py. `raw_torque_nm` and `r_eff_m` are
    both effectively snapshotted at the moment of recording -- r_eff_m in
    particular so the point stays meaningful even if the spool-growth model
    is recalibrated later. `direction` says which fitted line ("up" =
    lifting/concentric/retracting, "down" = lowering/eccentric/paying out)
    this point belongs to."""

    known_weight_kg: float
    raw_torque_nm: float
    r_eff_m: float
    direction: str

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}, got {self.direction!r}")

    @property
    def expected_torque_nm(self) -> float:
        """The real torque physics says was needed to hold this known
        weight at this effective radius -- what `raw_torque_nm` SHOULD have
        read, absent any motor-constant/friction error."""
        return self.known_weight_kg * GRAVITY_M_S2 * self.r_eff_m


def fit_linear(points: List[TorqueCalibrationPoint]) -> Tuple[float, float]:
    """Fit `expected = scale*|raw| + offset` through `points` (all assumed
    to already share one direction -- callers filter by `.direction` before
    calling this). See module docstring for why this fits against the
    magnitude of raw_torque_nm, not the signed value, and for the 0/1/2+
    point cases."""
    if not points:
        return 1.0, 0.0

    if len(points) == 1:
        raw = abs(points[0].raw_torque_nm)
        if raw == 0.0:
            return 1.0, 0.0  # degenerate -- nothing to scale against
        return points[0].expected_torque_nm / raw, 0.0

    n = len(points)
    xs = [abs(p.raw_torque_nm) for p in points]
    ys = [p.expected_torque_nm for p in points]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0.0:
        # Every point at the same raw torque -- no spread to fit a slope
        # against, fall back to a scale-only fit through the mean.
        scale = mean_y / mean_x if mean_x != 0.0 else 1.0
        return scale, 0.0

    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    scale = numerator / denominator
    offset = mean_y - scale * mean_x
    return scale, offset


def _direction_for_velocity(cable_velocity_turns_s: float) -> Optional[str]:
    """None means "static" -- see STATIC_VELOCITY_DEADBAND_TURNS_S."""
    if abs(cable_velocity_turns_s) < STATIC_VELOCITY_DEADBAND_TURNS_S:
        return None
    return "down" if cable_velocity_turns_s > 0 else "up"


class TorqueCalibration:
    """Bundles recorded points + the fitted (scale, offset) PER DIRECTION,
    the same role `SpoolGeometry` plays for spool-growth calibration --
    callers don't have to re-fit on every use."""

    def __init__(self, points: Optional[List[TorqueCalibrationPoint]] = None):
        self.points: List[TorqueCalibrationPoint] = list(points) if points else []
        self.points_by_direction: Dict[str, List[TorqueCalibrationPoint]] = {
            d: [p for p in self.points if p.direction == d] for d in DIRECTIONS
        }
        self.scale: Dict[str, float] = {}
        self.offset: Dict[str, float] = {}
        for d in DIRECTIONS:
            self.scale[d], self.offset[d] = fit_linear(self.points_by_direction[d])

    def _scale_offset_for(self, cable_velocity_turns_s: float) -> Tuple[float, float]:
        direction = _direction_for_velocity(cable_velocity_turns_s)
        if direction is not None:
            return self.scale[direction], self.offset[direction]
        # Static blend: average the direction-independent (proportional)
        # part of both fits, drop the friction offset entirely -- see module
        # docstring's "Near-zero velocity" section.
        blended_scale = sum(self.scale[d] for d in DIRECTIONS) / len(DIRECTIONS)
        return blended_scale, 0.0

    def corrected_torque_nm(self, raw_nm: float, cable_velocity_turns_s: float = 0.0) -> float:
        """Raw (motor-constant-only) torque estimate -> calibrated real
        torque. Identity when uncalibrated (scale=1, offset=0) in every
        direction. Corrects the MAGNITUDE of `raw_nm` (see module docstring)
        and reapplies its sign unchanged -- direction of the TORQUE is never
        touched by calibration, only how big it really is. `cable_velocity_
        turns_s` (CABLE-frame, + = paying out/lowering -- CABLE_SIGN *
        sample.velocity, not the raw motor-frame velocity) picks which
        fitted line to use; omit it (or pass near-zero) for a static/no-
        motion-info context, which uses the blended fallback."""
        sign = 0.0 if raw_nm == 0.0 else math.copysign(1.0, raw_nm)
        scale, offset = self._scale_offset_for(cable_velocity_turns_s)
        return sign * (scale * abs(raw_nm) + offset)

    def raw_torque_nm_for_corrected(self, corrected_nm: float, cable_velocity_turns_s: float = 0.0) -> float:
        """Inverse of corrected_torque_nm() -- what raw Nm value to actually
        command so the real, physical torque delivered matches
        `corrected_nm` (the value the rest of the codebase reasons about in
        force/torque terms). Same direction selection as corrected_torque_nm
        (see its docstring for `cable_velocity_turns_s`'s sign convention).
        Sign-preserving the same way corrected_torque_nm is; the resulting
        magnitude is floored at 0 (a raw torque magnitude can't be negative
        -- happens when `corrected_nm`'s magnitude is smaller than the
        selected line's offset, i.e. below what the fitted model considers
        the threshold to overcome at all)."""
        scale, offset = self._scale_offset_for(cable_velocity_turns_s)
        if scale == 0.0:
            return 0.0
        sign = 0.0 if corrected_nm == 0.0 else math.copysign(1.0, corrected_nm)
        magnitude = max(0.0, (abs(corrected_nm) - offset) / scale)
        return sign * magnitude

    def describe(self) -> dict:
        """Plain-numbers-substituted-in description, for Developer
        Visibility (item 7) -- mirrors geometry.py's describe_model(). One
        entry per direction, plus the static-blend numbers actually in
        effect right now (they're derived, not independently fitted, but
        worth showing since they're what a hold/near-zero-velocity moment
        actually uses).

        Also mirrors the static-blend scale/offset/equation/points at the
        TOP level (`scale`/`offset`/`equation`/`points`, no `directions`
        nesting) -- kept for every caller that only ever wants a single
        no-direction-context conversion (e.g. converting an entered torque
        limit before a move has even started, when there's no live velocity
        to pick a direction from -- frontend/src/components/tabs/control/
        ControlTab.jsx, useControlTelemetry.js, useTestingTelemetry.js,
        RepetitiveTesting.jsx). Same convention the static blend itself
        already uses for live control (see corrected_torque_nm's docstring)."""
        blended_scale = sum(self.scale[d] for d in DIRECTIONS) / len(DIRECTIONS)
        return {
            "scale": blended_scale,
            "offset": 0.0,
            "equation": (
                f"corrected_torque_nm = sign(raw_torque_nm) * ({blended_scale:.6f} * |raw_torque_nm| + 0) "
                f"[static blend -- see 'directions' for the up/down lines this is derived from]"
            ),
            "points": [
                {
                    "known_weight_kg": p.known_weight_kg,
                    "raw_torque_nm": p.raw_torque_nm,
                    "r_eff_m": p.r_eff_m,
                    "direction": p.direction,
                    "expected_torque_nm": p.expected_torque_nm,
                }
                for p in self.points
            ],
            "directions": {
                d: {
                    "scale": self.scale[d],
                    "offset": self.offset[d],
                    "equation": (
                        f"corrected_torque_nm = sign(raw_torque_nm) * "
                        f"({self.scale[d]:.6f} * |raw_torque_nm| + {self.offset[d]:.6f})"
                    ),
                    "points": [
                        {
                            "known_weight_kg": p.known_weight_kg,
                            "raw_torque_nm": p.raw_torque_nm,
                            "r_eff_m": p.r_eff_m,
                            "expected_torque_nm": p.expected_torque_nm,
                        }
                        for p in self.points_by_direction[d]
                    ],
                }
                for d in DIRECTIONS
            },
            "static_blend": {
                "scale": blended_scale,
                "offset": 0.0,
                "deadband_turns_s": STATIC_VELOCITY_DEADBAND_TURNS_S,
            },
        }
