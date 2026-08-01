"""Spool geometry — Exercise tab Layer A (exercise_tab_build_spec_layerA.md
§3.3, §3.4), extended with a multi-point experimental growth model
(train_tab_build_spec.md, "Train tab calibration overhaul").

Pure math, zero project-specific imports (not even config.board_constants —
callers pass r0/k explicitly, sourced from CableState). This is the ONE place
turns<->radians and angle<->length conversions happen; nothing else in the
codebase should compute cable length from position directly.

Model (spec §3.3) — effective radius growing linearly with angle from home:

    r_eff(theta) = r0 + k*theta
    L(theta)     = r0*theta + (k/2)*theta**2

Inverting for length -> angle:

    theta(L) = L / r0                              when k == 0
    theta(L) = (-r0 + sqrt(r0**2 + 2*k*L)) / k      when k != 0

`k = 0` is the fully-supported default (reduces to the naive fixed-radius
model) — every function here must behave sanely at k=0, not just k!=0.

Piecewise growth model (added for the calibration overhaul): a single global
k assumes the effective-radius growth rate is exactly constant across the
whole spool, which is only ever an assumption -- real strap/webbing spooling
can grow non-uniformly (layer transitions, uneven winding). `GrowthSegment` /
`build_growth_segments` generalize the single-k model into a piecewise-linear
spline of r_eff vs. theta, fit EXACTLY through a set of experimentally
measured (theta, length) points rather than assumed: each segment is solved
with the identical closed-form algebra `calibrate_k` already uses, just
localized to that segment's own starting radius instead of r0. With exactly
one calibration point this reduces to precisely the same model
`calibrate_k`/`length_from_turns_delta` produce today -- the single-k model is
the 1-point special case of this one, not a different thing.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

TURNS_TO_RADIANS = 2.0 * math.pi


def radians_from_turns(turns: float) -> float:
    """The one turns->radians conversion site (spec §3.3: "don't let a stray
    2*pi float around the codebase")."""
    return turns * TURNS_TO_RADIANS


def turns_from_radians(theta: float) -> float:
    return theta / TURNS_TO_RADIANS


def speed_m_s_from_turns_s(turns_per_s: float, r0: float) -> float:
    """Cable speed (m/s) from angular speed (turns/s) at a fixed radius --
    the "one conversion site" for velocity, mirroring force_to_torque()'s
    role for force (exercise_tab_build_spec_layerB.md §11). Deliberately
    uses the fixed r0, not the k/growth-model-corrected effective radius at
    the current position: velocity is informational display only, not a
    safety-relevant conversion, so it keeps the simpler fixed-r0
    approximation. NOTE: force<->torque conversion (core/profiles/units.py's
    force_to_torque()) used to make this same simplification, but no longer
    does for TrainMode (train_tab_build_spec.md "calibration overhaul" item
    3) -- torque now uses SpoolGeometry.r_eff_at_turns_delta() at the
    current position, since a static radius there let commanded force drift
    as cable pays in/out. Velocity's simplification was never load-bearing
    for that drift and is left as-is."""
    return turns_per_s * TURNS_TO_RADIANS * r0


def length_from_angle(theta: float, r0: float, k: float) -> float:
    """L(theta) = r0*theta + (k/2)*theta**2. theta may be negative (treated
    as a magnitude via abs()) since cable length is only ever meaningful as a
    non-negative distance from home; callers pass abs(turns_since_home)."""
    theta = abs(theta)
    return r0 * theta + (k / 2.0) * theta * theta


def angle_from_length(length_m: float, r0: float, k: float) -> float:
    """Inverse of length_from_angle. Raises ValueError for a length that has
    no real solution under the current (r0, k) (only possible for k < 0
    beyond the model's valid range — the discriminant going negative)."""
    if length_m < 0:
        raise ValueError(f"length_m must be non-negative, got {length_m!r}")
    if k == 0.0:
        return length_m / r0
    discriminant = r0 * r0 + 2.0 * k * length_m
    if discriminant < 0:
        raise ValueError(
            f"No real solution for length_m={length_m!r} under r0={r0!r}, k={k!r} "
            f"(discriminant={discriminant!r} < 0) — length is outside this model's "
            f"valid range."
        )
    return (-r0 + math.sqrt(discriminant)) / k


def length_from_turns_delta(turns_delta: float, r0: float, k: float) -> float:
    """Cable length (m) corresponding to `turns_delta` turns away from home
    (sign-independent; a negative delta from a wrong-direction read is still
    a length magnitude)."""
    return length_from_angle(radians_from_turns(turns_delta), r0, k)


def turns_delta_from_length(length_m: float, r0: float, k: float) -> float:
    """Inverse of length_from_turns_delta: how many turns away from home
    correspond to `length_m` of cable."""
    return turns_from_radians(angle_from_length(length_m, r0, k))


def calibrate_k(
    theta_m_turns: float,
    measured_length_m: float,
    r0: float,
    min_theta_m_rad: Optional[float] = None,
    k_bounds: Optional[Tuple[float, float]] = None,
) -> float:
    """Back-compute the correction factor k from one known-length
    measurement (spec §3.3): the user reels out to some position, physically
    measures the actual cable length, and enters it — never types a raw k.

        k = 2*(L_actual - r0*theta_m) / theta_m**2

    `theta_m_turns` is turns away from home at the moment of measurement
    (sign-independent, abs() applied). Guards (spec §3.3):
      - rejects a tiny theta_m (numerically unstable -- theta_m**2 in the
        denominator) if min_theta_m_rad is given.
      - rejects a computed k outside a plausible range, if k_bounds is given.
    """
    theta_m = abs(radians_from_turns(theta_m_turns))
    if min_theta_m_rad is not None and theta_m < min_theta_m_rad:
        raise ValueError(
            f"Calibration angle too small ({theta_m:.4f} rad < "
            f"{min_theta_m_rad:.4f} rad minimum) -- reel out further before "
            f"calibrating; theta_m**2 in the denominator makes this "
            f"numerically unstable at small angles."
        )
    if measured_length_m < 0:
        raise ValueError(f"measured_length_m must be non-negative, got {measured_length_m!r}")

    k = 2.0 * (measured_length_m - r0 * theta_m) / (theta_m * theta_m)

    if k_bounds is not None:
        k_min, k_max = k_bounds
        if not (k_min <= k <= k_max):
            raise ValueError(
                f"Computed correction factor k={k!r} is outside the plausible "
                f"range [{k_min!r}, {k_max!r}] -- check the measured length "
                f"(a bad k here corrupts every length calculation downstream)."
            )
    return k


@dataclass
class GrowthSegment:
    """One piece of the piecewise-linear r_eff(theta) spline, in radians.
    `theta_end`/`length_end` are None only for the final, open-ended segment,
    which extrapolates its slope indefinitely beyond the last calibration
    point (mirroring how the single-k model already behaves past any one
    reference measurement)."""

    theta_start: float
    theta_end: Optional[float]
    r_start: float
    slope: float
    length_start: float
    length_end: Optional[float]


def build_growth_segments(
    r0: float,
    points_rad_length: List[Tuple[float, float]],
    min_r_eff_m: float = 0.0,
) -> List[GrowthSegment]:
    """Fit a piecewise-linear r_eff(theta) spline through `points_rad_length`
    -- (theta_rad, length_m) pairs, anchored at the implicit (theta=0, r0)
    origin. Each segment i is solved for the slope that makes L(theta) land
    exactly on that segment's measured point, using the same closed-form
    algebra `calibrate_k` uses for the single-point case:

        slope_i = 2*(delta_L - r_start_i*delta_theta) / delta_theta**2

    just localized to segment i's own r_start (continuous from the previous
    segment's r_end) instead of a global r0. Raises ValueError if the points
    aren't strictly increasing in both theta and length (cable length must
    grow monotonically as more turns are paid out -- a data-entry slip, not a
    valid measurement set), or if any segment would take r_eff to/below
    `min_r_eff_m` (a non-physical/degenerate model), naming the offending
    segment so the caller can point at exactly which measurement to recheck.

    A single point reduces this to exactly one bounded segment plus one
    open-ended extrapolation segment sharing its slope -- mathematically
    identical to today's single-k model for a k derived from that same point.
    """
    if r0 <= 0:
        raise ValueError(f"r0 must be positive, got {r0!r}")
    if not points_rad_length:
        raise ValueError("points_rad_length must contain at least one (theta_rad, length_m) point")

    points = sorted(points_rad_length, key=lambda p: p[0])

    prev_theta, prev_length = 0.0, 0.0
    for theta, length in points:
        if theta <= prev_theta:
            raise ValueError(
                f"calibration points must have strictly increasing theta -- got "
                f"{theta!r} rad after {prev_theta!r} rad"
            )
        if length <= prev_length:
            raise ValueError(
                f"calibration points must have strictly increasing measured length -- "
                f"got {length!r} m after {prev_length!r} m (cable length must grow as "
                f"more turns are paid out)"
            )
        prev_theta, prev_length = theta, length

    segments: List[GrowthSegment] = []
    r_start, theta_start, length_start = r0, 0.0, 0.0
    for theta_end, length_end in points:
        d_theta = theta_end - theta_start
        d_length = length_end - length_start
        slope = 2.0 * (d_length - r_start * d_theta) / (d_theta * d_theta)
        r_end = r_start + slope * d_theta
        if r_start <= min_r_eff_m or r_end <= min_r_eff_m:
            raise ValueError(
                f"the segment from theta={theta_start!r} to theta={theta_end!r} rad "
                f"would take the effective radius to {min(r_start, r_end)!r} m, at or "
                f"below the {min_r_eff_m!r} m floor -- check the measured length at "
                f"theta={theta_end!r} rad."
            )
        segments.append(GrowthSegment(theta_start, theta_end, r_start, slope, length_start, length_end))
        r_start, theta_start, length_start = r_end, theta_end, length_end

    last = segments[-1]
    segments.append(GrowthSegment(last.theta_end, None, r_start, last.slope, last.length_end, None))
    return segments


def _find_segment_for_theta(theta: float, segments: List[GrowthSegment]) -> GrowthSegment:
    for seg in segments:
        if seg.theta_end is None or theta <= seg.theta_end:
            return seg
    return segments[-1]


def _find_segment_for_length(length_m: float, segments: List[GrowthSegment]) -> GrowthSegment:
    for seg in segments:
        if seg.length_end is None or length_m <= seg.length_end:
            return seg
    return segments[-1]


def length_from_angle_piecewise(theta: float, segments: List[GrowthSegment]) -> float:
    """Piecewise counterpart to `length_from_angle` -- theta may be negative
    (treated as a magnitude, same convention as the single-k model)."""
    theta = abs(theta)
    seg = _find_segment_for_theta(theta, segments)
    d_theta = theta - seg.theta_start
    return seg.length_start + seg.r_start * d_theta + (seg.slope / 2.0) * d_theta * d_theta


def angle_from_length_piecewise(length_m: float, segments: List[GrowthSegment]) -> float:
    """Inverse of `length_from_angle_piecewise`: find which segment
    `length_m` falls into, then invert within it using the same
    discriminant-based quadratic solve `angle_from_length` uses, shifted to
    that segment's local (theta_start, r_start, length_start)."""
    if length_m < 0:
        raise ValueError(f"length_m must be non-negative, got {length_m!r}")
    seg = _find_segment_for_length(length_m, segments)
    local_length = length_m - seg.length_start
    if seg.slope == 0.0:
        d_theta = local_length / seg.r_start
    else:
        discriminant = seg.r_start * seg.r_start + 2.0 * seg.slope * local_length
        if discriminant < 0:
            raise ValueError(
                f"No real solution for length_m={length_m!r} within the segment "
                f"starting at theta={seg.theta_start!r} rad -- length is outside this "
                f"model's valid range."
            )
        d_theta = (-seg.r_start + math.sqrt(discriminant)) / seg.slope
    return seg.theta_start + d_theta


def describe_model(r0: float, k: float, segments_summary: List[dict]) -> Dict[str, object]:
    """Plain-text (numbers substituted in, not symbolic) description of
    whichever model is currently active -- Developer Visibility (train tab
    calibration overhaul item 6): the point is to show exactly what equation
    is being evaluated, not just its name."""
    if segments_summary:
        segment_lines = []
        for i, seg in enumerate(segments_summary):
            end = f"{seg['theta_end_turns']:.3f}" if seg["theta_end_turns"] is not None else "∞"
            segment_lines.append(
                f"segment {i}: r_eff(θ) = {seg['r_start_m']:.6f} + "
                f"{seg['slope_m_per_rad']:.6f}·(θ − θ_{i}), "
                f"θ ∈ [{seg['theta_start_turns']:.3f}, {end}] turns"
            )
        return {
            "model": "piecewise-linear r_eff(θ), fit exactly through measured (turns, length) points",
            "length_equation": "L(θ) = L_i + r_i·(θ−θ_i) + (slope_i/2)·(θ−θ_i)², within each segment i",
            "segments": segment_lines,
        }
    return {
        "model": f"r_eff(θ) = {r0:.6f} + {k:.6f}·θ",
        "length_equation": f"L(θ) = {r0:.6f}·θ + ({k:.6f}/2)·θ²",
        "segments": [],
    }


class SpoolGeometry:
    """Thin, stateless-per-call wrapper bundling (r0, k) -- and, when given,
    a set of experimentally-measured growth-calibration points -- so callers
    don't have to thread the active model through every conversion. Still
    pure -- no config import, no hardware; everything is passed in by the
    caller (CableState).

    `growth_points`, when non-empty, is a list of (turns_from_home,
    length_m) pairs -- turns, not radians, matching how the rest of the
    codebase (CableState, ExerciseMode/TrainMode) already talks about
    position. When present, the piecewise model built from these points is
    used for every conversion below, superseding k (which is still tracked
    and still displayed, but no longer consulted) -- the piecewise fit is
    strictly more accurate since it's exact at every measured point, not just
    the one `calibrate_k` was given. With no growth points, behavior is
    completely unchanged from before this model existed."""

    def __init__(self, r0: float, k: float, growth_points: Optional[List[Tuple[float, float]]] = None):
        self.r0 = r0
        self.k = k
        self.growth_points = list(growth_points) if growth_points else []
        self._segments: Optional[List[GrowthSegment]] = None
        if self.growth_points:
            points_rad = [(radians_from_turns(t), length_m) for t, length_m in self.growth_points]
            self._segments = build_growth_segments(r0, points_rad)

    @property
    def active_model(self) -> str:
        if self._segments is not None:
            return "piecewise"
        return "linear" if self.k != 0.0 else "fixed_radius"

    def length_from_turns_delta(self, turns_delta: float) -> float:
        if self._segments is not None:
            return length_from_angle_piecewise(radians_from_turns(turns_delta), self._segments)
        return length_from_turns_delta(turns_delta, self.r0, self.k)

    def turns_delta_from_length(self, length_m: float) -> float:
        if self._segments is not None:
            return turns_from_radians(angle_from_length_piecewise(length_m, self._segments))
        return turns_delta_from_length(length_m, self.r0, self.k)

    def r_eff_at_turns_delta(self, turns_delta: float) -> float:
        """The effective spool radius at a given position -- Developer
        Visibility's "intermediate value" for the model currently active."""
        theta = abs(radians_from_turns(turns_delta))
        if self._segments is not None:
            seg = _find_segment_for_theta(theta, self._segments)
            return seg.r_start + seg.slope * (theta - seg.theta_start)
        return self.r0 + self.k * theta

    def segments_summary(self) -> List[dict]:
        """Turns/meters view of the piecewise segments, for display -- []
        when the piecewise model isn't active."""
        if self._segments is None:
            return []
        summary = []
        for seg in self._segments:
            r_end = seg.r_start + seg.slope * (seg.theta_end - seg.theta_start) if seg.theta_end is not None else None
            summary.append({
                "theta_start_turns": turns_from_radians(seg.theta_start),
                "theta_end_turns": turns_from_radians(seg.theta_end) if seg.theta_end is not None else None,
                "r_start_m": seg.r_start,
                "r_end_m": r_end,
                "slope_m_per_rad": seg.slope,
            })
        return summary

    def describe(self) -> Dict[str, object]:
        return describe_model(self.r0, self.k, self.segments_summary())
