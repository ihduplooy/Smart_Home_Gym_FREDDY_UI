"""train_profiles.py — Train tab resistance profiles. Pure math,
hardware-free (train_tab_build_spec.md §2/§4): no config/board_constants
import, no hardware, no CableState. A profile is an ordered list of segments,
each `(start_pos_m, end_pos_m, shape, params)`; given a cable position (m
from home), `TrainProfile.force_at()` returns a target force (N).

`preview()` evaluates the whole profile across a position range and is the
one function that feeds both the profile editor's live graph and the live
torque-vs-position overlay (spec §4: "one source of truth for the curve
shape") — build once, use twice, never duplicated per caller.

Force values here are never negative (validated at construction) but are
otherwise unbounded — the hard FORCE_MAX_N safety ceiling is a hardware
concern applied by the caller (TrainMode), not by this module, to keep this
file importable and testable with zero project config dependencies.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

CONSTANT = "constant"
LINEAR = "linear"
BELL = "bell"
_VALID_SHAPES = frozenset({CONSTANT, LINEAR, BELL})

# Shape name -> required numeric parameter keys. Presence/type checked here;
# shape-specific relationships (e.g. bell's peak must sit strictly inside the
# segment) are checked in TrainSegment.__post_init__, where start/end are
# available.
_SHAPE_PARAM_KEYS = {
    CONSTANT: ("force_n",),
    LINEAR: ("start_force_n", "end_force_n"),
    BELL: ("peak_pos_m", "peak_force_n"),
}

# Optional numeric params per shape, with the default applied when the caller
# omits them. Currently only bell's edge floors (added 25 July 2026 so a bell
# can ramp between nonzero start/end forces -- e.g. 3 -> 10 -> 4 -- instead of
# always returning to 0 at both edges); every other shape's params are fully
# required above.
_SHAPE_OPTIONAL_PARAM_DEFAULTS = {
    BELL: {"start_force_n": 0.0, "end_force_n": 0.0},
}


def _require_numeric(params: Dict[str, Any], key: str) -> float:
    if key not in params:
        raise ValueError(f"Missing required parameter '{key}' for this shape")
    value = params[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Parameter '{key}' must be numeric, got {value!r}")
    return float(value)


def _optional_numeric(params: Dict[str, Any], key: str, default: float) -> float:
    if key not in params:
        return default
    value = params[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Parameter '{key}' must be numeric, got {value!r}")
    return float(value)


@dataclass
class TrainSegment:
    start_pos_m: float
    end_pos_m: float
    shape: str
    params: Dict[str, float]

    def __post_init__(self):
        if self.shape not in _VALID_SHAPES:
            raise ValueError(f"Unknown segment shape {self.shape!r} (expected one of {sorted(_VALID_SHAPES)})")
        if self.start_pos_m < 0 or self.end_pos_m < 0:
            raise ValueError("Segment positions must be non-negative (cable length from home)")
        if self.end_pos_m <= self.start_pos_m:
            raise ValueError(
                f"Segment end_pos_m ({self.end_pos_m!r}) must be greater than "
                f"start_pos_m ({self.start_pos_m!r})"
            )

        parsed: Dict[str, float] = {}
        for key in _SHAPE_PARAM_KEYS[self.shape]:
            parsed[key] = _require_numeric(self.params, key)
        for key, default in _SHAPE_OPTIONAL_PARAM_DEFAULTS.get(self.shape, {}).items():
            parsed[key] = _optional_numeric(self.params, key, default)

        if self.shape == CONSTANT:
            if parsed["force_n"] < 0:
                raise ValueError(f"force_n must be non-negative, got {parsed['force_n']!r}")
        elif self.shape == LINEAR:
            if parsed["start_force_n"] < 0 or parsed["end_force_n"] < 0:
                raise ValueError("start_force_n/end_force_n must be non-negative")
        elif self.shape == BELL:
            if parsed["peak_force_n"] < 0:
                raise ValueError(f"peak_force_n must be non-negative, got {parsed['peak_force_n']!r}")
            if parsed["start_force_n"] < 0 or parsed["end_force_n"] < 0:
                raise ValueError("start_force_n/end_force_n must be non-negative")
            if not (self.start_pos_m < parsed["peak_pos_m"] < self.end_pos_m):
                raise ValueError(
                    f"bell peak_pos_m ({parsed['peak_pos_m']!r}) must sit strictly inside "
                    f"the segment ({self.start_pos_m!r}, {self.end_pos_m!r})"
                )

        # Store back the coerced-to-float, validated params only.
        self.params = parsed

    def contains(self, position_m: float) -> bool:
        return self.start_pos_m <= position_m <= self.end_pos_m

    def force_at(self, position_m: float) -> float:
        if self.shape == CONSTANT:
            return self.params["force_n"]

        if self.shape == LINEAR:
            span = self.end_pos_m - self.start_pos_m
            frac = (position_m - self.start_pos_m) / span
            frac = min(1.0, max(0.0, frac))
            start_f, end_f = self.params["start_force_n"], self.params["end_force_n"]
            return start_f + frac * (end_f - start_f)

        # BELL: raised-half-cosine ramp, from start_force_n/end_force_n at
        # their respective edges up to peak_force_n at peak_pos_m (edge
        # floors default to 0, the original "always returns to zero" shape).
        # Independent half-widths either side of the peak so an off-centre
        # peak_pos_m is still handled without chasing a true Gaussian (spec
        # §4: "keep the bell math reasonably simple").
        peak_pos = self.params["peak_pos_m"]
        peak_force = self.params["peak_force_n"]
        if position_m <= peak_pos:
            edge_force = self.params["start_force_n"]
            half_span = max(peak_pos - self.start_pos_m, 1e-9)
            frac = (position_m - self.start_pos_m) / half_span
        else:
            edge_force = self.params["end_force_n"]
            half_span = max(self.end_pos_m - peak_pos, 1e-9)
            frac = (self.end_pos_m - position_m) / half_span
        frac = min(1.0, max(0.0, frac))
        bump = 0.5 * (1.0 - math.cos(math.pi * frac))  # 0 at edge, 1 at peak
        return edge_force + (peak_force - edge_force) * bump


@dataclass
class TrainProfile:
    name: str = "unnamed"
    segments: List[TrainSegment] = field(default_factory=list)

    def __post_init__(self):
        # Reject overlapping segments up front: which segment "wins" at an
        # overlapping position is otherwise ambiguous, and there's no
        # legitimate use case for Train (unlike core/profiles' composable
        # wrappers) that needs two active segments at once.
        ordered = sorted(self.segments, key=lambda s: s.start_pos_m)
        for prev, nxt in zip(ordered, ordered[1:]):
            if nxt.start_pos_m < prev.end_pos_m:
                raise ValueError(
                    f"Overlapping segments: [{prev.start_pos_m}, {prev.end_pos_m}] and "
                    f"[{nxt.start_pos_m}, {nxt.end_pos_m}]"
                )
        self.segments = ordered

    def force_at(self, position_m: float) -> float:
        """Target force (N, always >= 0) at `position_m`. 0.0 outside every
        segment — wherever the profile doesn't define a segment, there's no
        resistance, rather than raising or extrapolating the nearest one."""
        for segment in self.segments:
            if segment.contains(position_m):
                return max(0.0, segment.force_at(position_m))
        return 0.0

    def preview(self, position_range_m: Tuple[float, float], n_points: int = 200) -> List[Tuple[float, float]]:
        """Evaluate force_at() across `n_points` samples spanning
        `position_range_m` (lo, hi). The one evaluator both the profile
        editor's preview graph and the live torque-vs-position overlay read
        from (spec §4) — never re-derive the curve shape a second way."""
        lo, hi = position_range_m
        n_points = max(2, n_points)
        if hi <= lo:
            return [(lo, self.force_at(lo))]
        step = (hi - lo) / (n_points - 1)
        return [(lo + i * step, self.force_at(lo + i * step)) for i in range(n_points)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "segments": [
                {
                    "start_pos_m": s.start_pos_m,
                    "end_pos_m": s.end_pos_m,
                    "shape": s.shape,
                    "params": dict(s.params),
                }
                for s in self.segments
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainProfile":
        if not isinstance(data, dict):
            raise TypeError(f"Profile must be a dict, got {data!r}")
        segments_data = data.get("segments") or []
        if not isinstance(segments_data, list):
            raise TypeError(f"'segments' must be a list, got {segments_data!r}")
        segments = [
            TrainSegment(
                start_pos_m=seg.get("start_pos_m"),
                end_pos_m=seg.get("end_pos_m"),
                shape=seg.get("shape"),
                params=seg.get("params") or {},
            )
            for seg in segments_data
        ]
        return cls(name=data.get("name", "unnamed"), segments=segments)
