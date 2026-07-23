"""Spool geometry — Exercise tab Layer A (exercise_tab_build_spec_layerA.md
§3.3, §3.4).

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
"""

import math
from typing import Optional, Tuple

TURNS_TO_RADIANS = 2.0 * math.pi


def radians_from_turns(turns: float) -> float:
    """The one turns->radians conversion site (spec §3.3: "don't let a stray
    2*pi float around the codebase")."""
    return turns * TURNS_TO_RADIANS


def turns_from_radians(theta: float) -> float:
    return theta / TURNS_TO_RADIANS


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


class SpoolGeometry:
    """Thin, stateless-per-call wrapper bundling (r0, k) so callers don't
    have to thread both through every conversion. Still pure -- no config
    import, no hardware; r0/k are passed in by the caller (CableState)."""

    def __init__(self, r0: float, k: float):
        self.r0 = r0
        self.k = k

    def length_from_turns_delta(self, turns_delta: float) -> float:
        return length_from_turns_delta(turns_delta, self.r0, self.k)

    def turns_delta_from_length(self, length_m: float) -> float:
        return turns_delta_from_length(length_m, self.r0, self.k)
