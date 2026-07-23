"""Homing state machine — Exercise tab Layer A
(exercise_tab_build_spec_layerA.md §3.1, §4).

Pure logic: consumes (t, current_iq, position_turns) samples and emits a
velocity command + state, exactly the "state-read + target-write" shape
core/hardware/interface.py already uses. No hardware access, no Flask, no
ControlSession — driven entirely by synthetic sample sequences (spec §8),
same testing philosophy as core/profiles/detectors.py.

Direction follows the existing CABLE_SIGN convention (core/profiles/detectors
.py): positive velocity = cable paying out. Homing reels IN, so the commanded
velocity is the negative of HOMING_VELOCITY_TURNS_S under that sign.

A stale/false home reference is the single most dangerous failure mode in
this layer (spec §4) — this state machine is deliberately conservative:
  - Never starts on its own; the first update() call IS the explicit user
    "Home" action (constructing the instance does nothing).
  - Detection debounces on N *consecutive* over-threshold samples, reset to
    zero on any sample that drops back below threshold (spec: "a one-sample
    transient must not be able to define the machine's position reference").
  - No detection is evaluated at all during the startup grace window — the
    debounce counter stays at zero throughout, so a spike that starts in
    grace and straddles the grace/detecting boundary cannot carry a partial
    count across it.
  - Travel and time bounds are checked every tick regardless of phase, so a
    stalled/blocked spool (travel bound) or a slipping cable that never tautens
    (time bound) both terminate in a fault, never an indefinite reel-in.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from config import board_constants
from core.profiles.detectors import CABLE_SIGN


class HomingState(Enum):
    IDLE = "idle"  # not yet started
    STARTUP_GRACE = "startup_grace"
    DETECTING = "detecting"
    HOMED = "homed"
    FAULT_TRAVEL_EXCEEDED = "fault_travel_exceeded"
    FAULT_TIMEOUT = "fault_timeout"
    ABORTED = "aborted"


_TERMINAL_STATES = frozenset({
    HomingState.HOMED,
    HomingState.FAULT_TRAVEL_EXCEEDED,
    HomingState.FAULT_TIMEOUT,
    HomingState.ABORTED,
})


@dataclass
class HomingUpdate:
    state: HomingState
    velocity_command_turns_s: float
    home_position_turns: Optional[float] = None  # set only on the tick HOMED latches
    fault_reason: Optional[str] = None


class HomingStateMachine:
    """One instance per homing attempt. Construction alone must not move
    anything (spec §4 item 1) — motion begins only once update() is first
    called, which callers must gate behind an explicit user action.

    `velocity_turns_s`/`current_threshold_a` accept live overrides (None ->
    board_constants default) -- these two are user-adjustable per-session
    bench-tuning values (exposed on the Exercise tab, held in CableState),
    requested live against real hardware 23 July 2026: the live board's
    homing current draw didn't match the 0.8A starting placeholder closely
    enough to be useful as a fixed default. The other four (debounce/grace/
    travel-bound/timeout) stay board_constants-only -- they're safety
    margins, not calibration values, and weren't asked to be exposed."""

    def __init__(self, velocity_turns_s: Optional[float] = None, current_threshold_a: Optional[float] = None):
        self._state = HomingState.IDLE
        self._start_t: Optional[float] = None
        self._start_position: Optional[float] = None
        self._consecutive_over_threshold = 0

        self._velocity_turns_s = velocity_turns_s if velocity_turns_s is not None else board_constants.HOMING_VELOCITY_TURNS_S
        self._current_threshold_a = (
            current_threshold_a if current_threshold_a is not None else board_constants.HOMING_CURRENT_THRESHOLD_A
        )
        self._debounce_samples = board_constants.HOMING_DEBOUNCE_SAMPLES
        self._grace_s = board_constants.HOMING_STARTUP_GRACE_S
        self._max_travel_turns = board_constants.HOMING_MAX_TRAVEL_TURNS
        self._timeout_s = board_constants.HOMING_TIMEOUT_S

        self._reel_in_velocity = -CABLE_SIGN * self._velocity_turns_s

    @property
    def state(self) -> HomingState:
        return self._state

    def abort(self) -> HomingUpdate:
        """Explicit user abort, available at any time while homing runs
        (spec §3.1, §4 item 7). No-op (returns the current terminal state)
        if already terminal."""
        if self._state not in _TERMINAL_STATES:
            self._state = HomingState.ABORTED
        return HomingUpdate(state=self._state, velocity_command_turns_s=0.0)

    def update(self, t: float, current_iq: float, position_turns: float) -> HomingUpdate:
        if self._state in _TERMINAL_STATES:
            return HomingUpdate(state=self._state, velocity_command_turns_s=0.0)

        if self._start_t is None:
            # First call: this IS the explicit "start homing" action.
            self._start_t = t
            self._start_position = position_turns
            self._state = HomingState.STARTUP_GRACE

        elapsed_s = t - self._start_t
        travel_turns = abs(position_turns - self._start_position)

        if travel_turns > self._max_travel_turns:
            self._state = HomingState.FAULT_TRAVEL_EXCEEDED
            return HomingUpdate(
                state=self._state,
                velocity_command_turns_s=0.0,
                fault_reason=(
                    f"Travel bound exceeded ({travel_turns:.2f} > "
                    f"{self._max_travel_turns:.2f} turns) without detecting "
                    f"cable tension — spool may be stalled/blocked."
                ),
            )

        if elapsed_s > self._timeout_s:
            self._state = HomingState.FAULT_TIMEOUT
            return HomingUpdate(
                state=self._state,
                velocity_command_turns_s=0.0,
                fault_reason=(
                    f"Timeout exceeded ({elapsed_s:.1f} > {self._timeout_s:.1f}s) "
                    f"without detecting cable tension — cable may be slipping "
                    f"or not attached."
                ),
            )

        if self._state == HomingState.STARTUP_GRACE:
            if elapsed_s >= self._grace_s:
                self._state = HomingState.DETECTING
            else:
                # No detection evaluated during grace; debounce counter stays
                # at zero so a spike here can never carry into DETECTING.
                self._consecutive_over_threshold = 0
                return HomingUpdate(state=self._state, velocity_command_turns_s=self._reel_in_velocity)

        # DETECTING (freshly entered above, or already here).
        if abs(current_iq) >= self._current_threshold_a:
            self._consecutive_over_threshold += 1
        else:
            self._consecutive_over_threshold = 0

        if self._consecutive_over_threshold >= self._debounce_samples:
            self._state = HomingState.HOMED
            return HomingUpdate(
                state=self._state,
                velocity_command_turns_s=0.0,
                home_position_turns=position_turns,
            )

        return HomingUpdate(state=self._state, velocity_command_turns_s=self._reel_in_velocity)
