"""Isokinetic velocity governor — Exercise tab Layer B, Session B1
(exercise_tab_build_spec_layerB.md §4.3, §6 item 5).

Pure function, zero project-specific imports, no internal state — the
caller (force_mode.py) owns the one piece of mutable state this needs (an
EWMA-filtered velocity estimate) and passes the already-filtered value in.
This is deliberately implemented entirely in the torque domain: there is NO
integrator anywhere in this function, which is the whole point of doing
isokinetic this way rather than as ODrive velocity-mode-with-a-cap (spec
§3 item 2) — velocity error above target does not accumulate across calls,
it is recomputed fresh from the current filtered velocity every time.
"""


def governed_force(
    velocity_turns_s: float,
    velocity_target_turns_s: float,
    force_base_n: float,
    force_max_n: float,
    governor_gain: float,
) -> float:
    """
        F_cmd = F_base                                          when v <= v_target
        F_cmd = F_base + governor_gain * (v - v_target)          above it, clamped to F_max

    `velocity_turns_s` is the CABLE_SIGN-corrected, already-filtered cable
    velocity (positive = paying out, i.e. the direction being governed
    against during concentric). Below the target speed, resistance is flat
    at `force_base_n` (which may be 0 for a pure isokinetic feel, or
    non-zero for a resistance floor plus a speed cap — spec §4.3). Above it,
    force rises linearly with the excess speed and is hard-clamped at
    `force_max_n` — this clamp is the FIRST of the three §6 item 6
    precedence layers (F_max, then the existing hardware torque-limit clamp,
    then the §5.3 power limiter)."""
    if velocity_turns_s <= velocity_target_turns_s:
        force_n = force_base_n
    else:
        force_n = force_base_n + governor_gain * (velocity_turns_s - velocity_target_turns_s)
    return min(force_n, force_max_n)
