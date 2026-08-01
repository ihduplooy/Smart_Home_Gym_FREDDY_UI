"""
Encoder SPI diagnostic — open item #14 (ENCODER_ERROR_NO_RESPONSE during
AXIS_STATE_ENCODER_OFFSET_CALIBRATION on the onboard AS5047P, SPI mode).

Purpose: stop iterating on the calibration state machine directly and instead
isolate WHERE the fault actually is, using ODrive's own diagnostic states/tools.
Two independent tests, run in order, each gated behind its own confirm() prompt
(the motor moves/energizes in both):

  STEP 0 — connect, dump axis0 state + any existing errors as a clean reference.
  STEP 1 — AXIS_STATE_LOCKIN_SPIN: drive the motor open-loop, entirely bypassing
           the encoder-offset-calibration algorithm, while polling
           encoder.spi_error_rate / pos_estimate / shadow_count / vel_estimate at
           ~10 Hz. Isolates whether the SPI link itself is healthy under drive.
  STEP 2 — "slow lockin": one AXIS_STATE_ENCODER_OFFSET_CALIBRATION attempt with
           axis0.config.calibration_lockin's vel/accel temporarily slowed and
           ramp_time lengthened (in-memory only — restored afterward regardless
           of outcome). Tests whether the fault is a timing-budget issue (SPI
           read competing with the control loop for cycles during calibration).

This script is read-only with respect to saved configuration: it never calls
erase_configuration() or save_configuration(), and never sets pre_calibrated on
anything. Run manually at the bench, present for every confirm() prompt:

    python3 config/diagnose_encoder_spi.py
"""

import sys
import time

import odrive
import odrive.enums as enums
from odrive.utils import dump_errors

from odrive_diag_common import clear_axis_errors, confirm, wait_for_idle

STEP1_SPIN_DURATION_S = 4.0
STEP1_POLL_HZ = 10.0

# Heuristics for classifying the Step 1 poll data, applied on top of the raw
# printed table (which is the real evidence — these just flag what to look at).
STEP1_FREEZE_RUN_LENGTH = 5  # consecutive identical pos_estimate samples = "frozen"
STEP1_JUMP_TURNS = 2.0  # |delta pos_estimate| between consecutive polls = "glitch"

# calibration_lockin slowdown for Step 2, as ratios of whatever is currently
# configured (ODrive's stock defaults are vel=40, accel=20, ramp_time=0.4, which
# is where the "40->10 / 20->5 / 0.4->1.5" example in the project notes comes
# from) rather than hardcoded absolute values, so this still makes sense if the
# board's calibration_lockin has already been touched by something else.
STEP2_VEL_ACCEL_FACTOR = 0.25  # e.g. 40 -> 10, 20 -> 5
STEP2_RAMP_TIME_FACTOR = 3.75  # e.g. 0.4 -> 1.5
STEP2_WAIT_FOR_IDLE_TIMEOUT_S = 60  # longer than the default 30s: ramp_time is ~4x


def dump_axis_reference_state(odrv0):
    axis0 = odrv0.axis0
    print(f"\naxis0.current_state       = {axis0.current_state}")
    print(f"axis0.error               = {axis0.error}")
    print(f"axis0.motor.error         = {axis0.motor.error}")
    print(f"axis0.motor.is_calibrated = {axis0.motor.is_calibrated}")
    print(f"axis0.encoder.error       = {axis0.encoder.error}")
    print(f"axis0.encoder.is_ready    = {axis0.encoder.is_ready}")
    print(f"axis0.controller.error    = {axis0.controller.error}")
    print("\nFull dump_errors() (per-submodule error decode):")
    dump_errors(odrv0)


def run_step1_lockin_spin(odrv0):
    """AXIS_STATE_LOCKIN_SPIN open-loop drive test. Returns a verdict string, or
    None if this firmware/package doesn't expose an equivalent state."""
    lockin_state = getattr(enums, "AXIS_STATE_LOCKIN_SPIN", None)
    if lockin_state is None:
        print("\nAXIS_STATE_LOCKIN_SPIN not found in odrive.enums on this odrive "
              "package version. Available AXIS_STATE_* names:")
        for name in sorted(n for n in dir(enums) if n.startswith("AXIS_STATE_")):
            print(f"  {name} = {getattr(enums, name)}")
        print("Skipping Step 1 (open-loop drive test) — no equivalent state identified.")
        return None

    axis0 = odrv0.axis0
    print(f"\nRequesting AXIS_STATE_LOCKIN_SPIN ({lockin_state})...")
    axis0.requested_state = lockin_state
    time.sleep(0.3)  # let the state transition actually land before checking it

    if axis0.current_state != lockin_state:
        print(f"Axis did not enter LOCKIN_SPIN — current_state={axis0.current_state}, "
              f"axis.error={axis0.error}, motor.error={axis0.motor.error}, "
              f"encoder.error={axis0.encoder.error}.")
        print("Treating as inconclusive for Step 1 (couldn't even start the open-loop "
              "drive test) rather than guessing which failure mode this is.")
        axis0.requested_state = enums.AXIS_STATE_IDLE
        wait_for_idle(axis0)
        return "STEP 1 INCONCLUSIVE — axis failed to enter LOCKIN_SPIN at all."

    print("In LOCKIN_SPIN. Polling encoder.spi_error_rate/pos_estimate/shadow_count/"
          f"vel_estimate at ~{STEP1_POLL_HZ:.0f} Hz for {STEP1_SPIN_DURATION_S:.1f}s...\n")
    interval = 1.0 / STEP1_POLL_HZ
    n_polls = int(STEP1_SPIN_DURATION_S * STEP1_POLL_HZ)
    samples = []  # (t, spi_error_rate, pos_estimate, shadow_count, vel_estimate)

    print(f"{'t (s)':>8} {'spi_error_rate':>15} {'pos_estimate':>13} "
          f"{'shadow_count':>13} {'vel_estimate':>13}")
    try:
        t0 = time.time()
        for _ in range(n_polls):
            t = time.time() - t0
            ser = odrv0.axis0.encoder.spi_error_rate
            pos = odrv0.axis0.encoder.pos_estimate
            shadow = odrv0.axis0.encoder.shadow_count
            vel = odrv0.axis0.encoder.vel_estimate
            samples.append((t, ser, pos, shadow, vel))
            print(f"{t:8.2f} {ser:15.4f} {pos:13.4f} {shadow:13d} {vel:13.4f}")
            time.sleep(interval)
    finally:
        print("\nReturning axis0 to idle...")
        odrv0.axis0.requested_state = enums.AXIS_STATE_IDLE
        wait_for_idle(odrv0.axis0)

    return classify_step1(samples)


def classify_step1(samples):
    if not samples:
        return "STEP 1 INCONCLUSIVE — no samples collected."

    max_spi_error_rate = max(s[1] for s in samples)
    spi_errors_seen = max_spi_error_rate > 0.0

    positions = [s[2] for s in samples]
    freeze_detected = False
    run_len = 1
    for i in range(1, len(positions)):
        if positions[i] == positions[i - 1]:
            run_len += 1
            if run_len >= STEP1_FREEZE_RUN_LENGTH:
                freeze_detected = True
        else:
            run_len = 1

    jump_detected = any(
        abs(positions[i] - positions[i - 1]) > STEP1_JUMP_TURNS
        for i in range(1, len(positions))
    )

    print(f"\nStep 1 summary: max spi_error_rate={max_spi_error_rate:.4f}, "
          f"freeze_detected={freeze_detected}, jump_detected={jump_detected}")

    if not spi_errors_seen and not freeze_detected and not jump_detected:
        return ("SPI LINK HEALTHY UNDER DRIVE — fault is likely in the calibration "
                "state machine/logic, not raw SPI communication.")
    return ("SPI COMMUNICATION FAILURE UNDER DRIVE CONFIRMED — likely EMI/timing/"
            "wiring issue, not calibration-specific.")


def run_step2_slow_lockin(odrv0):
    axis0 = odrv0.axis0
    cl = axis0.config.calibration_lockin

    orig_current = cl.current
    orig_ramp_time = cl.ramp_time
    orig_ramp_distance = cl.ramp_distance
    orig_accel = cl.accel
    orig_vel = cl.vel

    print(f"\nCurrent calibration_lockin: current={orig_current}, "
          f"ramp_time={orig_ramp_time}, ramp_distance={orig_ramp_distance}, "
          f"accel={orig_accel}, vel={orig_vel}")

    new_vel = orig_vel * STEP2_VEL_ACCEL_FACTOR
    new_accel = orig_accel * STEP2_VEL_ACCEL_FACTOR
    new_ramp_time = orig_ramp_time * STEP2_RAMP_TIME_FACTOR
    print(f"Slowing (in-memory only, not saved): vel {orig_vel} -> {new_vel}, "
          f"accel {orig_accel} -> {new_accel}, ramp_time {orig_ramp_time} -> "
          f"{new_ramp_time}")

    try:
        cl.vel = new_vel
        cl.accel = new_accel
        cl.ramp_time = new_ramp_time

        clear_axis_errors(axis0)

        print("\nRunning one AXIS_STATE_ENCODER_OFFSET_CALIBRATION attempt at the "
              "slowed settings...")
        axis0.requested_state = enums.AXIS_STATE_ENCODER_OFFSET_CALIBRATION
        wait_for_idle(axis0, timeout=STEP2_WAIT_FOR_IDLE_TIMEOUT_S)
        time.sleep(0.2)  # settle — a fast read right after the transition can lag

        is_ready = axis0.encoder.is_ready
        enc_error = axis0.encoder.error
        axis_error = axis0.error
        print(f"\nResult: encoder.is_ready={is_ready}, encoder.error={enc_error}, "
              f"axis0.error={axis_error}")

        if is_ready and enc_error == enums.ENCODER_ERROR_NONE:
            return ("SLOW LOCKIN SUCCEEDED — suggests a timing-budget issue (SPI read "
                    "competing with the control loop for cycles at normal calibration "
                    "speed).")
        if enc_error == enums.ENCODER_ERROR_NO_RESPONSE:
            return ("SLOW LOCKIN FAILED WITH THE SAME ENCODER_ERROR_NO_RESPONSE — "
                    "suggests the slowdown isn't the relevant variable.")
        return (f"SLOW LOCKIN FAILED WITH A DIFFERENT ERROR (encoder.error={enc_error}, "
                f"axis0.error={axis_error}) — inconclusive for the timing-budget "
                "hypothesis specifically; note the different failure mode.")
    finally:
        cl.vel = orig_vel
        cl.accel = orig_accel
        cl.ramp_time = orig_ramp_time
        cl.current = orig_current
        cl.ramp_distance = orig_ramp_distance
        print(f"\nRestored calibration_lockin: current={orig_current}, "
              f"ramp_time={orig_ramp_time}, ramp_distance={orig_ramp_distance}, "
              f"accel={orig_accel}, vel={orig_vel} (nothing saved — in-memory only, "
              "matches whatever was already saved on the board before this script ran).")


def print_final_summary(step1_verdict, step2_verdict):
    print("\n" + "=" * 78)
    print("FINAL SUMMARY")
    print("=" * 78)
    print(f"Step 1 (open-loop SPI health under drive): {step1_verdict}")
    print(f"Step 2 (slow lockin calibration attempt):   {step2_verdict}")
    print()

    step1_healthy = step1_verdict is not None and step1_verdict.startswith("SPI LINK HEALTHY")
    step1_failed = step1_verdict is not None and step1_verdict.startswith("SPI COMMUNICATION FAILURE")
    step2_success = step2_verdict.startswith("SLOW LOCKIN SUCCEEDED")
    step2_same_failure = step2_verdict.startswith("SLOW LOCKIN FAILED WITH THE SAME")

    if step1_verdict is None:
        print("Step 1 didn't run (no LOCKIN_SPIN-equivalent state found on this "
              "package/firmware). Only Step 2's result is usable evidence here.")
    elif step1_healthy and step2_success:
        print("Next diagnostic direction: SPI is healthy under generic open-loop drive, "
              "and slowing calibration's own lockin fixed it — points at a timing-budget "
              "issue specific to AXIS_STATE_ENCODER_OFFSET_CALIBRATION's normal speed. "
              "Consider whether calibration_lockin's default vel/accel are simply too "
              "fast for this board's SPI read cadence, rather than a wiring/EMI problem.")
    elif step1_healthy and step2_same_failure:
        print("Next diagnostic direction: SPI is healthy under generic open-loop drive, "
              "and slowing calibration didn't help — points at something specific to the "
              "calibration state machine/logic itself (not raw SPI communication, and not "
              "simply speed). Worth comparing calibration_lockin's behavior/config against "
              "general_lockin's (used by LOCKIN_SPIN) more closely, since Step 1 used the "
              "latter successfully.")
    elif step1_failed and step2_success:
        print("Next diagnostic direction: mixed/inconclusive — Step 1 showed SPI errors "
              "under generic open-loop drive, but the slow calibration attempt succeeded "
              "anyway. Could be intermittent EMI that the slower calibration speed happened "
              "to dodge this run. Re-run both steps a few more times before trusting this "
              "combination; don't treat one slow-lockin success as a fix yet.")
    elif step1_failed and step2_same_failure:
        print("Next diagnostic direction: both point at hardware — SPI communication "
              "failure confirmed under open-loop drive (not calibration-specific), and "
              "slowing calibration's lockin didn't help either. Strongest signal so far to "
              "prioritize physical inspection / oscilloscope-on-the-SPI-lines-during-drive "
              "over further software-side calibration changes.")
    else:
        print("Mixed/inconclusive combination — re-read both raw result lines above "
              "before deciding on a next step.")


def main():
    print("Waiting for ODrive... (make sure USB isolator is connected)")
    odrv0 = odrive.find_any()
    print(f"Connected. Serial: {odrv0.serial_number}")

    # STEP 0 — clean reference dump before anything moves.
    dump_axis_reference_state(odrv0)

    # STEP 1 — open-loop drive test (bypasses the calibration algorithm entirely).
    confirm(
        "Run Step 1: AXIS_STATE_LOCKIN_SPIN open-loop drive test? Motor WILL turn.\n"
        "    Confirm: wiring checked, USB isolator in place, area clear."
    )
    step1_verdict = run_step1_lockin_spin(odrv0)
    print(f"\nStep 1 verdict: {step1_verdict}")

    # STEP 2 — only if the user confirms after seeing Step 1's verdict.
    confirm(
        f"Step 1 verdict was:\n    {step1_verdict}\n"
        "Run Step 2: one slow-lockin AXIS_STATE_ENCODER_OFFSET_CALIBRATION attempt? "
        "Motor WILL turn."
    )
    step2_verdict = run_step2_slow_lockin(odrv0)
    print(f"\nStep 2 verdict: {step2_verdict}")

    print_final_summary(step1_verdict, step2_verdict)


if __name__ == "__main__":
    main()
