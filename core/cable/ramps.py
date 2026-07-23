"""Slew-rate ramps and the max-extension force taper — Exercise tab Layer B,
Session B1 (exercise_tab_build_spec_layerB.md §4.2, §4.5, §6 item 2).

Pure math, zero project-specific imports — same character as geometry.py.

`slew_toward()` implements ramp-in/ramp-out as a fixed RATE (N/s), not a
fixed duration re-normalized per target the way the spec's prose literally
reads ("force ramps from zero to target over FORCE_RAMP_IN_S"). This is a
deliberate deviation, logged in docs/decisions.md: a rate-based ramp handles
engage, disengage, and a live mid-ENGAGED retarget with ONE mechanism (no
ramp-start timestamp to track, no special-casing a target that changes
mid-ramp), and a target smaller than the full-scale rate reference always
ramps in *faster* than the nominal duration, never slower — strictly safer
than the literal reading, never less safe. The rate itself is still derived
from the spec's constants: rate = FORCE_MAX_N / FORCE_RAMP_IN_S.
"""


def slew_toward(current: float, target: float, max_step: float) -> float:
    """One rate-limited step from `current` toward `target`, bounded by
    `max_step` (always non-negative — the direction is inferred). Callers
    call this once per tick to make force approach a target without ever
    stepping there directly (spec §6 item 2)."""
    if max_step < 0:
        raise ValueError(f"max_step must be non-negative, got {max_step!r}")
    delta = target - current
    if delta > max_step:
        return current + max_step
    if delta < -max_step:
        return current - max_step
    return target


def taper_factor(distance_to_limit_m: float, taper_distance_m: float) -> float:
    """1.0 when at or beyond `taper_distance_m` from the limit, decreasing
    linearly to 0.0 exactly at the limit (distance_to_limit_m <= 0), never
    negative (a cable already past the limit -- Layer A's runtime guard
    should already have stopped the session by then, but this must not
    produce a nonsensical negative multiplier if it's ever called with a
    negative distance). `taper_distance_m` must be positive; a distance
    input is otherwise unbounded above (far from the limit is simply 1.0)."""
    if taper_distance_m <= 0:
        raise ValueError(f"taper_distance_m must be positive, got {taper_distance_m!r}")
    if distance_to_limit_m <= 0:
        return 0.0
    if distance_to_limit_m >= taper_distance_m:
        return 1.0
    return distance_to_limit_m / taper_distance_m
