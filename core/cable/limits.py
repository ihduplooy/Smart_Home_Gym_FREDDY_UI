"""Position-limit model and enforcement — Exercise tab Layer A
(exercise_tab_build_spec_layerA.md §3.4, §4).

Pure decision logic: given plain floats (absolute encoder turns, both in the
raw ODrive frame -- home_turns and max_turns are wherever pos_estimate read
when they were set/marked, not "turns since home"), decide what to do. No
hardware, no ControlSession.

Two distinct mechanisms, both required (spec §3.4) -- clamping alone
protects against bad commands, not against the cable actually ending up
somewhere it shouldn't:
  1. clamp_target_turns() -- target clamping, applied before a command
     reaches the motor.
  2. check_runtime_guard() -- runtime guard, applied every tick against
     *measured* position.
"""

from core.profiles.detectors import CABLE_SIGN


def validate_homed(is_homed: bool) -> None:
    """All length-based operations are rejected when un-homed (spec §4 item
    5) -- not silently interpreted against a stale or zero reference."""
    if not is_homed:
        raise RuntimeError(
            "Cable is not homed -- length-based control is unavailable until "
            "homing succeeds."
        )


def clamp_target_turns(target_turns: float, home_turns: float, max_turns: float) -> float:
    """Clamp a commanded absolute position (turns) into [home_turns,
    max_turns] (order-independent -- callers may pass either bound first)."""
    lo, hi = min(home_turns, max_turns), max(home_turns, max_turns)
    return max(lo, min(hi, target_turns))


def check_runtime_guard(
    position_turns: float,
    home_turns: float,
    max_turns: float,
    tolerance_turns: float,
) -> bool:
    """True if `position_turns` has left [home_turns, max_turns] by more
    than `tolerance_turns` -- the runtime (not just command-time) guard.
    Callers should stop the session when this returns True."""
    lo, hi = min(home_turns, max_turns), max(home_turns, max_turns)
    return position_turns < (lo - tolerance_turns) or position_turns > (hi + tolerance_turns)


def validate_max_extension_candidate(
    marked_turns: float,
    home_turns: float,
    min_travel_turns: float,
) -> None:
    """Sanity-check a marked max-extension point before it's accepted (spec
    §3.2: "a marked max that is at, below, or implausibly close to home
    should be rejected"). Raises ValueError on a degenerate/inverted range;
    the caller applies MAX_EXTENSION_SAFETY_MARGIN_M separately, after this
    check, on the raw marked point.

    "Below home" is direction-aware, not just magnitude: under this
    project's CABLE_SIGN convention, paying out (extending) increases
    position, so a marked point on the wrong side of home is rejected
    outright regardless of how far away it is -- a large-magnitude but
    wrong-direction travel is not a large, safe range, it's inverted."""
    signed_travel = (marked_turns - home_turns) * CABLE_SIGN
    if signed_travel <= 0:
        raise ValueError(
            f"Marked max-extension point ({marked_turns:.4f} turns) is at or "
            f"below home ({home_turns:.4f} turns) in the extension direction "
            f"-- would produce an inverted travel range."
        )
    if signed_travel < min_travel_turns:
        raise ValueError(
            f"Marked max-extension point is too close to home "
            f"({signed_travel:.4f} turns < {min_travel_turns:.4f} minimum) -- "
            f"would produce a degenerate travel range."
        )
