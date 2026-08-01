"""Small derived-metric helper for the Testing tab's telemetry (Testing tab
Build Spec §3). The CSV schema itself stays centralized in
core/telemetry/csv_logger.py (extended, not forked) -- this module only owns
the one piece of math that's genuinely experiment-specific: converting a
TelemetrySample into an estimated power draw.
"""

import math

from core.hardware.interface import TelemetrySample


def estimated_power_w(sample: TelemetrySample) -> float:
    """Mechanical power estimate: torque (Nm) * angular velocity (rad/s).
    Chosen over current * voltage (electrical bus power) because that would
    double-count against the phase-current channel already logged
    separately, and because torque_est/velocity are already both per-sample
    fields with no extra read path needed -- documented choice, not the only
    valid one (spec §3 explicitly allows either)."""
    angular_velocity_rad_s = sample.velocity * 2.0 * math.pi
    return sample.torque_est * angular_velocity_rad_s
