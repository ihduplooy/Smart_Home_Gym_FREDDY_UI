"""Software power limiter — Exercise tab Layer B, Session B1
(exercise_tab_build_spec_layerB.md §5.2, §5.3, §6 item 6).

Pure math, zero project-specific imports (callers pass torque_constant/
r_phase_ohm/spool_radius_m explicitly, sourced from board_constants) — same
character as geometry.py.

    P_mech   = F_cable * v_cable
    Iq       = (F_cable * r_spool) / Kt
    P_copper = 1.5 * Iq^2 * R_phase          (independent of velocity)
    P_regen  = P_mech - P_copper              (the estimate this module clamps)

P_regen(F) is a downward-opening parabola in F (P_copper grows with F^2,
P_mech only linearly) — meaning for a FIXED velocity, regen power rises with
commanded force only up to a peak, then *falls* as copper losses start to
dominate. apply_power_limit() clamps to the smaller of the two forces where
P_regen(F) == budget (the one on the rising branch, below the peak) rather
than the larger one — the smaller root is always <= the originally
requested force whenever limiting is needed at all (P_regen(F_requested) >
budget only happens for F strictly between the two roots), so clamping down
to it is always a genuine reduction, never a paradoxical increase.
"""

import math
from typing import Tuple


def estimate_regen_power_w(
    force_n: float,
    cable_velocity_m_s: float,
    torque_constant: float,
    r_phase_ohm: float,
    spool_radius_m: float,
) -> float:
    """P_mech - P_copper. Can be negative (net consumption, not regen) --
    that's the point of the copper-loss offset (spec §5.2): at low speed and/
    or high force, more power is burned in the windings than ever reaches
    the bus."""
    p_mech = force_n * cable_velocity_m_s
    iq = (force_n * spool_radius_m) / torque_constant
    p_copper = 1.5 * iq * iq * r_phase_ohm
    return p_mech - p_copper


def apply_power_limit(
    force_n: float,
    cable_velocity_m_s: float,
    budget_w: float,
    torque_constant: float,
    r_phase_ohm: float,
    spool_radius_m: float,
) -> Tuple[float, bool]:
    """Clamp `force_n` so the estimated regen power stays <= budget_w.
    Returns (limited_force_n, limiter_active). No motion (v<=0) or no
    commanded force (F<=0) is never limited -- no mechanical power is being
    extracted from the user in either case, regardless of force."""
    if cable_velocity_m_s <= 0 or force_n <= 0:
        return force_n, False

    p = estimate_regen_power_w(force_n, cable_velocity_m_s, torque_constant, r_phase_ohm, spool_radius_m)
    if p <= budget_w:
        return force_n, False

    a = 1.5 * (spool_radius_m / torque_constant) ** 2 * r_phase_ohm  # coefficient of F^2
    v = cable_velocity_m_s

    if a == 0:
        # Degenerate (only reachable with a pathological torque_constant/
        # r_phase_ohm/spool_radius_m input, not real hardware): P(F) is
        # linear, solve v*F = budget_w directly.
        limited = budget_w / v
        return max(0.0, min(limited, force_n)), True

    # Solve a*F^2 - v*F + budget_w = 0; take the smaller (rising-branch) root.
    discriminant = max(0.0, v * v - 4 * a * budget_w)
    limited = (v - math.sqrt(discriminant)) / (2 * a)
    return max(0.0, min(limited, force_n)), True
