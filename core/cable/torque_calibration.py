"""Torque/force calibration -- corrects the fixed-motor-constant torque
estimate (core/hardware/*.py's `torque_est = MOTOR_TORQUE_CONSTANT *
current_iq`) against experimentally measured points: hang a known mass, hold
it via a position move, record the torque_est it actually took. Friction and
other mechanical losses make the raw estimate systematically wrong in a way
`MOTOR_TORQUE_CONSTANT` alone can't capture; this fits a straight-line
correction on top of it instead -- same "make it explicit, don't guess,
verify at the bench" spirit as this package's spool-growth calibration
(geometry.py's `build_growth_segments`).

Pure math, zero project-specific imports, same convention as geometry.py:
callers (CableState) pass in whatever they already have.

Model: corrected_magnitude = scale * |raw_nm| + offset, with the sign of
`raw_nm` reapplied afterward -- i.e. this fits and corrects the MAGNITUDE of
the torque, never the sign.

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
still preserving direction for every caller that needs it for control.

Fit from N recorded (raw_torque_nm, expected_torque_nm) pairs --
`expected_torque_nm` is derived physics (known_weight_kg * g * r_eff_m at
the moment of recording), `raw_torque_nm` is whatever the hardware/software
estimated at that same moment (sign included, but only |raw_torque_nm| is
used for fitting):

    0 points  -> identity (scale=1, offset=0) -- no calibration recorded
                 yet, completely unchanged behavior.
    1 point   -> scale = expected / |raw| (offset fixed at 0) -- same
                 closed-form shape as geometry.py's calibrate_k single-point
                 case; one equation can't solve for two unknowns.
    2+ points -> ordinary least-squares line through every (|raw|, expected)
                 point (both scale and offset free) -- captures a constant,
                 load-independent offset (e.g. static friction) in addition
                 to a proportional error, which a single point alone can't
                 distinguish from scale.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

GRAVITY_M_S2 = 9.81


@dataclass
class TorqueCalibrationPoint:
    """One recorded calibration measurement. `raw_torque_nm` and `r_eff_m`
    are both snapshotted at the exact moment of recording -- r_eff_m in
    particular so the point stays meaningful even if the spool-growth model
    is recalibrated later."""

    known_weight_kg: float
    raw_torque_nm: float
    r_eff_m: float

    @property
    def expected_torque_nm(self) -> float:
        """The real torque physics says was needed to hold this known
        weight at this effective radius -- what `raw_torque_nm` SHOULD have
        read, absent any motor-constant/friction error."""
        return self.known_weight_kg * GRAVITY_M_S2 * self.r_eff_m


def fit_linear(points: List[TorqueCalibrationPoint]) -> Tuple[float, float]:
    """Fit `expected = scale*|raw| + offset` through `points`. See module
    docstring for why this fits against the magnitude of raw_torque_nm, not
    the signed value, and for the 0/1/2+ point cases."""
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


class TorqueCalibration:
    """Bundles recorded points + the fitted (scale, offset), the same role
    `SpoolGeometry` plays for spool-growth calibration -- callers don't have
    to re-fit on every use."""

    def __init__(self, points: Optional[List[TorqueCalibrationPoint]] = None):
        self.points: List[TorqueCalibrationPoint] = list(points) if points else []
        self.scale, self.offset = fit_linear(self.points)

    def corrected_torque_nm(self, raw_nm: float) -> float:
        """Raw (motor-constant-only) torque estimate -> calibrated real
        torque. Identity when uncalibrated (scale=1, offset=0). Corrects the
        MAGNITUDE of `raw_nm` (see module docstring) and reapplies its sign
        unchanged -- direction is never touched by calibration, only how big
        the torque really is."""
        sign = 0.0 if raw_nm == 0.0 else math.copysign(1.0, raw_nm)
        return sign * (self.scale * abs(raw_nm) + self.offset)

    def raw_torque_nm_for_corrected(self, corrected_nm: float) -> float:
        """Inverse of corrected_torque_nm() -- what raw Nm value to actually
        command so the real, physical torque delivered matches
        `corrected_nm` (the value the rest of the codebase reasons about in
        force/torque terms). Sign-preserving the same way corrected_torque_nm
        is; the resulting magnitude is floored at 0 (a raw torque magnitude
        can't be negative -- happens when `corrected_nm`'s magnitude is
        smaller than `offset`, i.e. below what the fitted model considers
        the threshold to overcome at all)."""
        if self.scale == 0.0:
            return 0.0
        sign = 0.0 if corrected_nm == 0.0 else math.copysign(1.0, corrected_nm)
        magnitude = max(0.0, (abs(corrected_nm) - self.offset) / self.scale)
        return sign * magnitude

    def describe(self) -> dict:
        """Plain-numbers-substituted-in description, for Developer
        Visibility (item 7) -- mirrors geometry.py's describe_model()."""
        return {
            "scale": self.scale,
            "offset": self.offset,
            "equation": (
                f"corrected_torque_nm = sign(raw_torque_nm) * "
                f"({self.scale:.6f} * |raw_torque_nm| + {self.offset:.6f})"
            ),
            "points": [
                {
                    "known_weight_kg": p.known_weight_kg,
                    "raw_torque_nm": p.raw_torque_nm,
                    "r_eff_m": p.r_eff_m,
                    "expected_torque_nm": p.expected_torque_nm,
                }
                for p in self.points
            ],
        }
