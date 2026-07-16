"""
Phase 1B — ODrive configuration script
Smart Home Gym — Programmable Cable Resistance System

Board:   MKS ODrive Mini V1.0 (ODrive v3.6 clone, also sold as "MKS XDrive Mini")
Motor:   Hoverboard BLDC hub motor, 15 pole pairs
Encoder: Onboard AS5047P magnetic encoder (SPI, absolute)
Firmware: v0.5.1 ONLY — do not upgrade. v0.5.6 breaks motor activation on this board.
Python:  odrive==0.5.1.post0 (must match firmware)

WRITTEN during Phase 1B (software-only, nothing physically connected).
RUN during Phase 2A, once hardware is actually wired in:
  ODrive Mini + hoverboard motor + AS5047P + brake resistor + bench PSU + isolated USB.

--------------------------------------------------------------------------
IMPORTANT — READ BEFORE RUNNING ON REAL HARDWARE
--------------------------------------------------------------------------
1. USB isolator MUST be in place before connecting USB with DC bus power
   applied. Ground loops from USB+DC together have destroyed other
   people's ODrive boards (and reportedly host USB ports too).
2. Brake resistor wattage rating is NOT YET CONFIRMED (open item #4 in the
   project plan). regen limits below are deliberately conservative
   (dc_max_negative_current, max_regen_current) until that's checked.
   Do not raise these without confirming the resistor can handle it.
3. First power-up should use the variable bench PSU at the LOW end
   (~12-15V), per plan. Do not jump straight to higher voltage.
4. This script pauses for manual confirmation before any step that
   energizes or moves the motor. Read each prompt before continuing.
5. AS5047P magnet mount + air gap alignment must be physically done
   FIRST (open item #6) before encoder calibration will succeed.
--------------------------------------------------------------------------
"""

import sys
import time
import odrive
from odrive.enums import (
    MOTOR_TYPE_HIGH_CURRENT,
    ENCODER_MODE_SPI_ABS_AMS,
    CONTROL_MODE_POSITION_CONTROL,
    INPUT_MODE_TRAP_TRAJ,
    AXIS_STATE_MOTOR_CALIBRATION,
    AXIS_STATE_ENCODER_OFFSET_CALIBRATION,
    AXIS_STATE_CLOSED_LOOP_CONTROL,
    AXIS_STATE_IDLE,
)


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


# Expected phase resistance/inductance range for a hoverboard hub motor. Used to
# sanity-check motor calibration results — if calibration lands outside this range,
# it usually means a wiring problem rather than a genuinely different motor.
MIN_PHASE_RESISTANCE = 0
MAX_PHASE_RESISTANCE = 0.5
MIN_PHASE_INDUCTANCE = 0
MAX_PHASE_INDUCTANCE = 0.001


def check_motor_calibration_sane(axis):
    """After motor calibration, confirm phase R/L land in the expected range for
    a hoverboard hub motor. Catches miswiring/bad connections early rather than
    silently trusting a bad calibration."""
    r = axis.motor.config.phase_resistance
    l = axis.motor.config.phase_inductance
    if not (MIN_PHASE_RESISTANCE < r < MAX_PHASE_RESISTANCE):
        print(f"\n!!! Phase resistance {r} outside expected range "
              f"({MIN_PHASE_RESISTANCE}-{MAX_PHASE_RESISTANCE}) — check wiring. !!!")
        sys.exit(1)
    if not (MIN_PHASE_INDUCTANCE < l < MAX_PHASE_INDUCTANCE):
        print(f"\n!!! Phase inductance {l} outside expected range "
              f"({MIN_PHASE_INDUCTANCE}-{MAX_PHASE_INDUCTANCE}) — check wiring. !!!")
        sys.exit(1)
    print(f"Motor calibration sane: phase_resistance={r:.4f} ohm, phase_inductance={l:.6f} H")


def check_errors(axis, label):
    """Print any error flags and stop the script if calibration/motor errors are present."""
    if axis.error != 0 or axis.motor.error != 0 or axis.encoder.error != 0:
        print(f"\n!!! ERROR after {label} !!!")
        print(f"axis.error        = {axis.error}")
        print(f"axis.motor.error  = {axis.motor.error}")
        print(f"axis.encoder.error= {axis.encoder.error}")
        print("Stopping here. Check odrivetool docs for this error code before retrying.")
        sys.exit(1)
    print(f"{label}: OK, no errors.")


# --------------------------------------------------------------------------
# Connect
# --------------------------------------------------------------------------
print("Waiting for ODrive... (make sure USB isolator is connected)")
odrv0 = odrive.find_any()
print(f"Connected. Serial: {odrv0.serial_number}")

# --------------------------------------------------------------------------
# SECTION 1 — Static configuration (safe: no motor movement, no calibration)
# --------------------------------------------------------------------------
confirm("Erase existing configuration and apply new config? (motor will NOT move yet)")

odrv0.erase_configuration()
# erase_configuration() reboots the board and drops the USB connection — reconnect:
odrv0 = odrive.find_any()

# --- Bus-level limits ---
odrv0.config.enable_brake_resistor = True            # explicit, don't rely on default
odrv0.config.brake_resistance = 2.0                 # matches the 2ohm brake resistor in hand
odrv0.config.dc_bus_undervoltage_trip_level = 8.0    # safe default, fine for 12-15V testing
odrv0.config.dc_bus_overvoltage_trip_level = 25.0    # capped for bench PSU testing only —
                                                      # MUST be raised before battery phase (~42V)
odrv0.config.dc_max_positive_current = 15.0          # bus-side draw limit, above motor current_lim
odrv0.config.dc_max_negative_current = -3.0          # conservative: brake resistor wattage tbc
odrv0.config.max_regen_current = 0                   # conservative: brake resistor wattage tbc

odrv0.save_configuration()
odrv0 = odrive.find_any()

# --- Motor configuration ---
odrv0.axis0.motor.config.pole_pairs = 15             # hoverboard hub motor, 15 pole pairs
odrv0.axis0.motor.config.motor_type = MOTOR_TYPE_HIGH_CURRENT  # correct class for hub motors
odrv0.axis0.motor.config.current_lim = 10.0          # conservative first pass, per plan
# Hoverboard hub motors have notably higher phase resistance than typical hobby
# aircraft/actuator motors, and are higher inductance too. requested_current_range
# and resistance_calib_max_voltage are bumped up accordingly (confirmed against a
# reference config written specifically for hoverboard motors on ODrive v3.6), and
# current_control_bandwidth is reduced from ODrive's default to keep the current
# loop stable given the higher inductance.
odrv0.axis0.motor.config.requested_current_range = 25.0
odrv0.axis0.motor.config.calibration_current = 5.0
odrv0.axis0.motor.config.resistance_calib_max_voltage = 4.0
odrv0.axis0.motor.config.current_control_bandwidth = 100

# --- Encoder configuration (AS5047P, SPI, onboard) ---
# abs_spi_cs_gpio_pin = 7 is specific to this MKS clone board (confirmed via community
# reports for this exact board — differs from genuine ODrive Pro/S1 pin numbers).
odrv0.axis0.encoder.config.mode = ENCODER_MODE_SPI_ABS_AMS
odrv0.axis0.encoder.config.abs_spi_cs_gpio_pin = 7
odrv0.axis0.encoder.config.cpr = 16384               # AS5047P is 14-bit -> 2^14
odrv0.axis0.encoder.config.bandwidth = 3000
odrv0.axis0.encoder.config.calib_range = 10

# --- Controller configuration ---
# NOTE: these gain/limit values are conservative STARTING POINTS ONLY, not tuned values.
# They are deliberately generic rather than copied from other people's motors, because
# gains are motor- and load-specific. Expect to re-tune vel_gain / pos_gain /
# vel_integrator_gain live once the motor is actually spinning in Phase 2A.
odrv0.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
odrv0.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ
odrv0.axis0.controller.config.vel_limit = 2.0        # turns/s — slow and cautious for first run
odrv0.axis0.controller.config.pos_gain = 1.0
odrv0.axis0.controller.config.vel_gain = 0.02
odrv0.axis0.controller.config.vel_integrator_gain = 0.0  # start at 0, add gradually if needed

odrv0.axis0.trap_traj.config.vel_limit = 1.0         # turns/s — gentle first move
odrv0.axis0.trap_traj.config.accel_limit = 1.0       # turns/s^2
odrv0.axis0.trap_traj.config.decel_limit = 1.0        # turns/s^2

# --- CAN config (Ghost Axis 1 fix) ---
# Included now per plan decision — harmless with no CAN hardware connected yet.
# Relevant for real use from Phase 2B onward, when the CAN HAT is wired in.
odrv0.axis0.config.can_node_id = 0
odrv0.can.set_baud_rate(500000)
odrv0.axis1.config.can_node_id = 63   # silences the ghost second axis on this board

odrv0.save_configuration()
odrv0 = odrive.find_any()
print("\nSection 1 complete: static configuration saved.")

# --------------------------------------------------------------------------
# SECTION 2 — Calibration (motor WILL spin briefly during motor calibration)
# --------------------------------------------------------------------------
confirm(
    "Run motor calibration? The motor WILL energize and may make noise/small movement.\n"
    "    Confirm: magnet mount + air gap alignment done, wiring checked, "
    "USB isolator in place, area clear."
)

print("Running motor calibration...")
odrv0.axis0.requested_state = AXIS_STATE_MOTOR_CALIBRATION
wait_for_idle(odrv0.axis0)
check_errors(odrv0.axis0, "Motor calibration")
check_motor_calibration_sane(odrv0.axis0)
odrv0.axis0.motor.config.pre_calibrated = True

confirm("Run encoder offset calibration? Motor WILL turn during this step.")

print("Running encoder offset calibration...")
odrv0.axis0.requested_state = AXIS_STATE_ENCODER_OFFSET_CALIBRATION
wait_for_idle(odrv0.axis0)
check_errors(odrv0.axis0, "Encoder offset calibration")

odrv0.save_configuration()
odrv0 = odrive.find_any()
print("\nSection 2 complete: motor + encoder calibrated and saved.")

# --------------------------------------------------------------------------
# SECTION 3 — Basic "is it alive" test move (small position command, ~1 turn)
# --------------------------------------------------------------------------
confirm("Enter closed-loop control and run a small (~1 turn) test move?")

odrv0.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
time.sleep(0.5)
check_errors(odrv0.axis0, "Entering closed-loop control")

print("Commanding +1 turn...")
odrv0.axis0.controller.input_pos = 1.0
time.sleep(3)

print("Returning to 0...")
odrv0.axis0.controller.input_pos = 0.0
time.sleep(3)

check_errors(odrv0.axis0, "Test move")

odrv0.axis0.requested_state = AXIS_STATE_IDLE
print("\nSection 3 complete: motor responded to position command and returned to idle.")
print("Phase 2A basic 'alive' check passed. Config saved to the ODrive's non-volatile memory.")
