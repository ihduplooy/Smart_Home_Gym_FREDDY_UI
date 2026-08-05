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
2. Brake resistor wattage rating is now confirmed at 100W (5 Aug 2026: two
   spare resistors wired in parallel, 2.35 ohm combined — resolves the
   wattage-unknown half of open item #4 in the project plan). Thermal
   margin under sustained real training load is still UNVERIFIED (the
   resistor ran uncomfortably hot within seconds on a short manual test) —
   regen limits below (dc_max_negative_current, max_regen_current) stay
   conservative until extended/hard sessions have actually been run.
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
import fibre.protocol
from odrive.enums import (
    MOTOR_TYPE_HIGH_CURRENT,
    ENCODER_MODE_SPI_ABS_AMS,
    CONTROL_MODE_POSITION_CONTROL,
    INPUT_MODE_TRAP_TRAJ,
    AXIS_STATE_MOTOR_CALIBRATION,
    AXIS_STATE_ENCODER_OFFSET_CALIBRATION,
    AXIS_STATE_CLOSED_LOOP_CONTROL,
    AXIS_STATE_IDLE,
    ENCODER_ERROR_NONE,
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


def motor_calibration_is_sane(axis):
    """True if phase resistance/inductance land within the expected range for a
    hoverboard hub motor. Boolean core of check_motor_calibration_sane(), factored
    out so a caller that wants to retry-and-continue (rather than exit) on a bad
    calibration can reuse the same check without duplicating it."""
    r = axis.motor.config.phase_resistance
    l = axis.motor.config.phase_inductance
    return (MIN_PHASE_RESISTANCE < r < MAX_PHASE_RESISTANCE) and (
        MIN_PHASE_INDUCTANCE < l < MAX_PHASE_INDUCTANCE
    )


def check_motor_calibration_sane(axis):
    """After motor calibration, confirm phase R/L land in the expected range for
    a hoverboard hub motor. Catches miswiring/bad connections early rather than
    silently trusting a bad calibration."""
    r = axis.motor.config.phase_resistance
    l = axis.motor.config.phase_inductance
    if not motor_calibration_is_sane(axis):
        if not (MIN_PHASE_RESISTANCE < r < MAX_PHASE_RESISTANCE):
            print(f"\n!!! Phase resistance {r} outside expected range "
                  f"({MIN_PHASE_RESISTANCE}-{MAX_PHASE_RESISTANCE}) — check wiring. !!!")
            sys.exit(1)
        if not (MIN_PHASE_INDUCTANCE < l < MAX_PHASE_INDUCTANCE):
            print(f"\n!!! Phase inductance {l} outside expected range "
                  f"({MIN_PHASE_INDUCTANCE}-{MAX_PHASE_INDUCTANCE}) — check wiring. !!!")
            sys.exit(1)
    print(f"Motor calibration sane: phase_resistance={r:.4f} ohm, phase_inductance={l:.6f} H")


def axis_has_errors(axis):
    """True if axis/motor/encoder error flags are non-zero. Boolean core of
    check_errors(), factored out so a caller that wants to retry-and-continue
    (rather than exit) on an error can reuse the same check without duplicating it."""
    return axis.error != 0 or axis.motor.error != 0 or axis.encoder.error != 0


def check_errors(axis, label):
    """Print any error flags and stop the script if calibration/motor errors are present."""
    if axis_has_errors(axis):
        print(f"\n!!! ERROR after {label} !!!")
        print(f"axis.error        = {axis.error}")
        print(f"axis.motor.error  = {axis.motor.error}")
        print(f"axis.encoder.error= {axis.encoder.error}")
        print("Stopping here. Check odrivetool docs for this error code before retrying.")
        sys.exit(1)
    print(f"{label}: OK, no errors.")


def clear_axis_errors(axis):
    """Clear axis/motor/encoder/controller error fields individually. clear_errors()
    does not exist on firmware v0.5.1 (confirmed live, 21 July 2026 — that convenience
    method was added in later ODrive releases)."""
    axis.error = 0
    axis.motor.error = 0
    axis.encoder.error = 0
    axis.controller.error = 0


REBOOT_RECONNECT_TIMEOUT = 15  # seconds to wait for the board to re-enumerate after a reboot


def call_and_reconnect(odrv, method_name, timeout=REBOOT_RECONNECT_TIMEOUT):
    """Call a no-arg ODrive RPC known to reboot the board (erase_configuration,
    save_configuration) and reconnect afterward.

    On this board those calls reboot mid-RPC, which severs the USB connection
    before the call returns — the SDK surfaces that as
    fibre.protocol.ChannelBrokenException. That exception is caught here as the
    *expected* outcome of a reboot-triggering call, not a failure. Any other
    exception from the call itself is a real error and is left to propagate.

    Fails loudly (prints a clear message and exits) rather than silently
    retrying if the board doesn't reappear within `timeout` seconds — a silent
    retry here could paper over a real problem (board didn't actually reboot,
    USB fault, isolator knocked loose) instead of surfacing it.
    """
    print(f"Calling {method_name}() (board will reboot)...")
    try:
        getattr(odrv, method_name)()
    except fibre.protocol.ChannelBrokenException:
        pass  # expected: reboot dropped the connection mid-call

    print(f"Waiting up to {timeout}s for ODrive to re-enumerate after {method_name}()...")
    new_odrv = odrive.find_any(timeout=timeout)
    if new_odrv is None:
        print(f"\n!!! ODrive did not reappear within {timeout}s after {method_name}(). !!!")
        print("Check that the board actually rebooted (power/USB still connected, "
              "isolator not disturbed) before re-running the script.")
        sys.exit(1)
    print(f"Reconnected. Serial: {new_odrv.serial_number}")
    return new_odrv


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

odrv0 = call_and_reconnect(odrv0, "erase_configuration")

# --- Bus-level limits ---
# No separate enable flag on this firmware (v0.5.1 has no odrv0.config.enable_brake_resistor —
# confirmed live via dir(odrv0.config)): setting brake_resistance non-zero is itself what
# enables the brake resistor. Set it to 0 to disable.
odrv0.config.brake_resistance = 2.35                # two spare resistors wired in parallel (5 Aug
                                                      # 2026), replacing the single 2ohm/50W unit —
                                                      # combined wattage confirmed 100W
odrv0.config.dc_bus_undervoltage_trip_level = 8.0    # safe default, fine for 12-15V testing
odrv0.config.dc_bus_overvoltage_trip_level = 27.0    # raised from the prior 25V bench-only value
                                                      # (5 Aug 2026, deliberate) —
                                                      # MUST be raised again before battery phase (~42V)
# DC bus overvoltage ramp: drives brake resistor duty directly off measured vbus, distinct from
# the current-based regen logic tied to max_regen_current below. Defaults to False on this
# firmware — left False, a hard/fast cable pull in Train mode could spike vbus toward the trip
# level and fault even with a correctly-valued brake resistor wired in (confirmed live 5 Aug 2026,
# see docs/decisions.md). Enabling it lets the resistor react to fast voltage transients, not only
# sustained regen current.
odrv0.config.enable_dc_bus_overvoltage_ramp = True
odrv0.config.dc_bus_overvoltage_ramp_start = 24.0
odrv0.config.dc_bus_overvoltage_ramp_end = 25.0
odrv0.config.dc_max_positive_current = 15.0          # bus-side draw limit, above motor current_lim
odrv0.config.dc_max_negative_current = -3.0          # conservative: brake resistor wattage tbc
odrv0.config.max_regen_current = 0                   # conservative: brake resistor wattage tbc

odrv0 = call_and_reconnect(odrv0, "save_configuration")

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

odrv0 = call_and_reconnect(odrv0, "save_configuration")
print("\nSection 1 complete: static configuration saved.")

# --------------------------------------------------------------------------
# SECTION 2 — Calibration (motor WILL spin briefly during motor calibration)
# --------------------------------------------------------------------------
# !!! IMPORTANT — READ THIS FIRST IF ENCODER OFFSET CALIBRATION FAILS (open item #14) !!!
#
# ROOT CAUSE FOUND (confirmed live, 21 July 2026): the onboard AS5047P can enter a
# latched fault state matching what the ODrive community forum calls "super-sulk"
# (see: https://discourse.odriverobotics.com/t/clarification-on-spi-encoders/6451/18,
# user "towen"). In this state the chip returns a FROZEN position value
# (shadow_count stuck at exactly 0 even while physically hand-rotating the shaft)
# while encoder.spi_error_rate misleadingly stays at 0.0 — no transaction-level SPI
# errors are flagged, so it looks superficially healthy. This is a different, deeper
# problem than anything the tiers below test for: it is NOT EMI, wiring, magnet
# alignment/type, the CS pin, calibration current, or encoder bandwidth (all ruled
# out earlier — tiers 1-3 below address none of the real cause).
#
# Confirmed live: this latch does NOT clear via clear_axis_errors()/odrv0.error
# fields, does NOT clear via odrv0.reboot(), and does NOT clear via
# save_configuration()'s implicit reboot. It ONLY clears via a FULL PHYSICAL POWER
# CYCLE of the DC bus (switch the bench PSU's output off, wait ~10s, switch back
# on — not just replugging USB). After a real power cycle, shadow_count immediately
# resumed live, correct tracking (both directions) and encoder offset calibration
# succeeded cleanly on the very next attempt.
#
# PRACTICAL TAKEAWAY: if ENCODER_ERROR_NO_RESPONSE or a frozen pos_estimate/
# shadow_count shows up again, do a full DC power cycle BEFORE re-attempting
# encoder offset calibration and BEFORE assuming hardware damage or re-running
# tiers 1-3 below — no amount of software retry/reboot fixes this state. Full
# writeup: docs/decisions.md, "AS5047P 'super-sulk' latched fault — root cause
# found" (21 July 2026).
#
# Tiers 1-3 below are left in place (harmless, and tier 3's motor-recalibration-
# before-encoder-attempt pattern may still have some value for other, unrelated
# transient failures) but are now known NOT to address this specific root cause.
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

# This step has proven intermittent on this board (open item #14, project plan):
# ENCODER_ERROR_NO_RESPONSE on a fraction of attempts despite the SPI link being
# confirmed alive at idle. Bounded auto-retry, saving immediately on the first
# clean success, rather than making the user manually re-invoke the whole script
# per attempt.
MAX_ENCODER_CALIBRATION_ATTEMPTS = 5

# Tier 2 diagnostic settings (open item #14): if all 5 tier-1 attempts fail at normal
# settings, retry at reduced motor calibration current + encoder bandwidth. Theory:
# the SPI link is confirmed alive at idle (shadow_count/pos_estimate update correctly
# when hand-spinning), and motor calibration itself always succeeds cleanly, so the
# fault is specific to this step, when phases are actively switching — likely EMI
# from motor drive current coupling into the SPI lines. Less phase current during the
# calibration move, and an encoder bandwidth less sensitive to noise-induced glitches
# in the SPI-derived estimate, may avoid triggering ENCODER_ERROR_NO_RESPONSE.
TIER2_CALIBRATION_CURRENT = 3.0
TIER2_ENCODER_BANDWIDTH = 1000


def run_encoder_calibration_attempts(odrv0, tier_label):
    """Run up to MAX_ENCODER_CALIBRATION_ATTEMPTS encoder offset calibration attempts
    at whatever settings are currently on the axis. Returns True on the first clean
    success, False if every attempt fails."""
    for attempt in range(1, MAX_ENCODER_CALIBRATION_ATTEMPTS + 1):
        print(f"\n[{tier_label}] Running encoder offset calibration (attempt {attempt}/"
              f"{MAX_ENCODER_CALIBRATION_ATTEMPTS})...")
        odrv0.axis0.requested_state = AXIS_STATE_ENCODER_OFFSET_CALIBRATION
        wait_for_idle(odrv0.axis0)

        if odrv0.axis0.encoder.is_ready and odrv0.axis0.encoder.error == ENCODER_ERROR_NONE:
            print(f"[{tier_label}] Encoder offset calibration succeeded on attempt {attempt}.")
            return True

        print(f"[{tier_label}] Attempt {attempt} failed: axis.error={odrv0.axis0.error}, "
              f"motor.error={odrv0.axis0.motor.error}, "
              f"encoder.error={odrv0.axis0.encoder.error}, "
              f"encoder.is_ready={odrv0.axis0.encoder.is_ready}")
        # NOTE: odrv0.clear_errors() does not exist on firmware v0.5.1 (confirmed live,
        # 21 July 2026 — that convenience method was added in later ODrive releases).
        # Clear the relevant error fields individually instead.
        odrv0.axis0.error = 0
        odrv0.axis0.motor.error = 0
        odrv0.axis0.encoder.error = 0
        odrv0.axis0.controller.error = 0
        time.sleep(0.5)

    return False


encoder_calibrated = run_encoder_calibration_attempts(odrv0, "tier 1: normal settings")
tier2_used = False

if not encoder_calibrated:
    print(f"\nTier 1 failed all {MAX_ENCODER_CALIBRATION_ATTEMPTS} attempts at normal "
          "settings. Trying tier 2: reduced calibration current + encoder bandwidth "
          "(open item #14, EMI-during-phase-switching theory).")

    orig_calibration_current = odrv0.axis0.motor.config.calibration_current
    orig_encoder_bandwidth = odrv0.axis0.encoder.config.bandwidth

    odrv0.axis0.motor.config.calibration_current = TIER2_CALIBRATION_CURRENT
    odrv0.axis0.encoder.config.bandwidth = TIER2_ENCODER_BANDWIDTH

    encoder_calibrated = run_encoder_calibration_attempts(odrv0, "tier 2: reduced settings")

    if encoder_calibrated:
        tier2_used = True
        print(f"\nTier 2 succeeded: calibration_current={TIER2_CALIBRATION_CURRENT}, "
              f"encoder.config.bandwidth={TIER2_ENCODER_BANDWIDTH}. Keeping these reduced "
              "values as the new working baseline (NOT reverting to the tier 1 defaults of "
              f"calibration_current={orig_calibration_current}, "
              f"encoder.config.bandwidth={orig_encoder_bandwidth}) — they will be persisted "
              "with the rest of the config below.")
    else:
        print(f"\nTier 2 also failed all {MAX_ENCODER_CALIBRATION_ATTEMPTS} attempts. "
              f"Restoring calibration_current={orig_calibration_current}, "
              f"encoder.config.bandwidth={orig_encoder_bandwidth} — those remain our best "
              "starting point for other diagnostics (e.g. physical inspection).")
        odrv0.axis0.motor.config.calibration_current = orig_calibration_current
        odrv0.axis0.encoder.config.bandwidth = orig_encoder_bandwidth

# Tier 3 diagnostic (open item #14): a live diagnostic session (21 July 2026, ~15
# manual attempts) found exactly one success, and it immediately followed a fresh
# AXIS_STATE_MOTOR_CALIBRATION run in the same session, with no reboot in between —
# every other attempt was encoder calibration alone, without re-running motor
# calibration first, and all of those failed. This is a new hypothesis, not yet
# confirmed (n=1): tier 3 tests it properly by re-running motor calibration
# immediately before each encoder offset calibration attempt, back to back, no
# reboot and no extra delay beyond what wait_for_idle already waits for.
tier3_used = False

if not encoder_calibrated:
    print(f"\nTier 2 failed all {MAX_ENCODER_CALIBRATION_ATTEMPTS} attempts as well. "
          "Trying tier 3: fresh motor calibration immediately followed by encoder "
          "offset calibration, no reboot in between (open item #14 — untested "
          "'motor calibration right before encoder calibration' hypothesis from a "
          "live diagnostic session, n=1).")

    for attempt in range(1, MAX_ENCODER_CALIBRATION_ATTEMPTS + 1):
        print(f"\n[tier 3: motor+encoder recalibration] Attempt {attempt}/"
              f"{MAX_ENCODER_CALIBRATION_ATTEMPTS}...")
        clear_axis_errors(odrv0.axis0)

        odrv0.axis0.requested_state = AXIS_STATE_MOTOR_CALIBRATION
        wait_for_idle(odrv0.axis0)

        if axis_has_errors(odrv0.axis0) or not motor_calibration_is_sane(odrv0.axis0):
            print(f"[tier 3] Attempt {attempt} failed at motor calibration: "
                  f"axis.error={odrv0.axis0.error}, motor.error={odrv0.axis0.motor.error}, "
                  f"encoder.error={odrv0.axis0.encoder.error}")
            time.sleep(0.5)
            continue

        # Immediately chain into encoder offset calibration — no reboot, no delay
        # beyond wait_for_idle's own polling.
        odrv0.axis0.requested_state = AXIS_STATE_ENCODER_OFFSET_CALIBRATION
        wait_for_idle(odrv0.axis0)

        # Live session observation: reading is_ready/error immediately after setting
        # requested_state showed a false-positive "no error" before the state machine
        # had actually run the attempt. Brief settle delay before checking.
        time.sleep(0.2)

        if odrv0.axis0.encoder.is_ready and odrv0.axis0.encoder.error == ENCODER_ERROR_NONE:
            print(f"[tier 3] Encoder offset calibration succeeded on attempt {attempt} "
                  "(immediately after a fresh motor calibration).")
            odrv0.axis0.motor.config.pre_calibrated = True
            odrv0.axis0.encoder.config.pre_calibrated = True
            encoder_calibrated = True
            tier3_used = True
            break

        print(f"[tier 3] Attempt {attempt} failed at encoder calibration: "
              f"axis.error={odrv0.axis0.error}, motor.error={odrv0.axis0.motor.error}, "
              f"encoder.error={odrv0.axis0.encoder.error}, "
              f"encoder.is_ready={odrv0.axis0.encoder.is_ready}")
        time.sleep(0.5)

    if encoder_calibrated:
        print(f"\nTier 3 succeeded on attempt {attempt}: fresh motor + encoder "
              "recalibration, no reboot in between.")
    else:
        # Tier 2's own failure branch above already restores these; this covers the
        # case where that branch is ever reached differently in the future, so tier 3
        # never leaves the board on the reduced tier-2 settings by accident.
        odrv0.axis0.motor.config.calibration_current = orig_calibration_current
        odrv0.axis0.encoder.config.bandwidth = orig_encoder_bandwidth

if not encoder_calibrated:
    print("\n!!! Encoder offset calibration failed all attempts across all 3 tiers "
          "(normal settings, reduced calibration current/encoder bandwidth, and fresh "
          "motor+encoder recalibration with no reboot in between). !!!")
    print("Not saving. See project plan open item #14 — next recommended step is a "
          "physical inspection of the onboard AS5047P chip (part markings, solder "
          "joint quality). Software-side retries are now exhausted: if physical "
          "inspection doesn't turn up anything, this likely needs direct measurement "
          "of the SPI lines during an active calibration attempt (oscilloscope or "
          "logic analyzer) to check for external noise/EMI — tooling not currently "
          "on hand.")
    sys.exit(1)

odrv0.axis0.encoder.config.pre_calibrated = True
odrv0 = call_and_reconnect(odrv0, "save_configuration")
if tier3_used:
    print(f"\nSection 2 complete: motor + encoder calibrated and saved — succeeded on "
          "TIER 3 (fresh motor + encoder recalibration, no reboot in between).")
elif tier2_used:
    print(f"\nSection 2 complete: motor + encoder calibrated and saved — succeeded on "
          f"TIER 2 (reduced settings: calibration_current={TIER2_CALIBRATION_CURRENT}, "
          f"encoder.config.bandwidth={TIER2_ENCODER_BANDWIDTH}).")
else:
    print("\nSection 2 complete: motor + encoder calibrated and saved (tier 1: normal "
          "settings).")

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
