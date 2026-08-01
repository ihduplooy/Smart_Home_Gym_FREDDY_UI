"""
Small helpers shared between standalone bench-diagnostic scripts under config/.

config/odrive_config.py is a top-level script that calls odrive.find_any() and
confirm() at import time (see docs/decisions.md — "never import that module, only
run it"), so its own copies of these helpers can't be imported without also
running the whole Phase 1B bring-up flow. This module holds the same small
patterns (confirmation gate, idle-wait poll, individual-field error clearing —
clear_errors() doesn't exist on firmware v0.5.1) so new diagnostic scripts reuse
them instead of re-copying them inline.
"""

import sys
import time

from odrive.enums import AXIS_STATE_IDLE


def confirm(prompt):
    """Pause and require explicit 'y' before continuing past a motor-energizing step."""
    resp = input(f"\n>>> {prompt} [y/N]: ").strip().lower()
    if resp != "y":
        print("Aborted by user.")
        sys.exit(0)


def wait_for_idle(axis, timeout=30):
    """Poll until the axis returns to IDLE (calibration/step complete) or timeout."""
    start = time.time()
    while axis.current_state != AXIS_STATE_IDLE:
        if time.time() - start > timeout:
            print("Timed out waiting for axis to return to idle.")
            return False
        time.sleep(0.1)
    return True


def clear_axis_errors(axis):
    """Clear axis/motor/encoder/controller error fields individually. clear_errors()
    does not exist on firmware v0.5.1 (confirmed live, 21 July 2026)."""
    axis.error = 0
    axis.motor.error = 0
    axis.encoder.error = 0
    axis.controller.error = 0
