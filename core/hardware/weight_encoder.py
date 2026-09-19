"""Rotary encoder -> GYM tab Constant-mode Weight field.

Wraps a single gpiozero.RotaryEncoder wired directly to the Pi:

    C (middle) -> GND
    A          -> GPIO17 (pin 11)
    B          -> GPIO27 (pin 13)

Completely independent of ODrive/device connection state -- weight_kg reads
and updates correctly whether or not a board is connected or scanned.
"""

import logging
import threading

from gpiozero import RotaryEncoder

from config.board_constants import STEP_KG, WEIGHT_KG_MIN, WEIGHT_KG_MAX

log = logging.getLogger(__name__)

ENCODER_GPIO_PIN_A = 17
ENCODER_GPIO_PIN_B = 27

# Matches GymProfileEditor.jsx's own `useState('10')` default -- never
# persisted across backend restarts, so both sides start from the same
# number.
DEFAULT_WEIGHT_KG = 10.0


def _clamp(value: float) -> float:
    return max(WEIGHT_KG_MIN, min(WEIGHT_KG_MAX, value))


class WeightEncoder:
    def __init__(self):
        self._lock = threading.Lock()
        self._weight_kg = DEFAULT_WEIGHT_KG
        self._last_steps = 0
        # Off-Pi (e.g. a developer's own machine, no /proc/cpuinfo -> gpiozero
        # has no pin factory to fall back to), gpiozero raises constructing
        # this at all -- caught here so the rest of the backend still starts
        # for everything unrelated to the encoder, same "hardware absence is
        # a warning, never a startup crash" spirit as ODRIVE_MOCK/
        # device_manager's own dead-handle handling elsewhere in this
        # project. weight_kg still reads/writes purely in software in that
        # case; only the physical knob itself does nothing.
        try:
            self._encoder = RotaryEncoder(ENCODER_GPIO_PIN_A, ENCODER_GPIO_PIN_B, max_steps=0)
            self._encoder.when_rotated = self._on_rotated
        except Exception as e:
            log.warning("Rotary encoder unavailable (%s) -- Weight only settable via the API/UI", e)
            self._encoder = None

    def _on_rotated(self):
        # Fires on gpiozero's own thread, not Flask's request thread -- every
        # read/write of weight_kg (and _last_steps) must go through _lock.
        with self._lock:
            steps = self._encoder.steps
            direction = 1 if steps > self._last_steps else -1
            self._last_steps = steps
            self._weight_kg = _clamp(self._weight_kg + direction * STEP_KG)

    def get_weight_kg(self) -> float:
        with self._lock:
            return self._weight_kg

    def set_weight_kg(self, value: float) -> None:
        """Re-syncs the tracked weight to a manually-typed frontend value --
        turning the knob afterward continues from here, not from wherever
        the knob last was."""
        with self._lock:
            self._weight_kg = _clamp(float(value))


# One instance for the whole backend process, same singleton pattern as
# backend/app/control_routes.py's cable_state/control_session.
weight_encoder = WeightEncoder()
