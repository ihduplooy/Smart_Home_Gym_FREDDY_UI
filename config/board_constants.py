"""
Single source of truth for this project's board/motor/encoder constants.

Every value here is taken verbatim from config/odrive_config.py (the Phase 1B
ODrive setup script). This module is plain data with no dependency on the
`odrive` package or any hardware — it's imported by the backend (to pre-load the
config wizard and serve the /api/board-constants route) and, from Session 2
onward, by core/. Never duplicate these values into frontend code; the frontend
fetches them via that one backend route.

Board: MKS ODrive Mini V1.0 (ODrive v3.6 clone, also sold as "MKS XDrive Mini")
"""

# --------------------------------------------------------------------------
# Firmware
# --------------------------------------------------------------------------
# v0.5.1 ONLY — do not upgrade. v0.5.6 breaks motor activation on this board.
EXPECTED_FW_VERSION_MAJOR = 0
EXPECTED_FW_VERSION_MINOR = 5
EXPECTED_FW_VERSION_REVISION = 1
EXPECTED_FW_VERSION_STRING = "0.5.1"

# Must match firmware; see backend/requirements.txt.
ODRIVE_PYTHON_PACKAGE_VERSION = "0.5.1.post0"

# --------------------------------------------------------------------------
# Motor — hoverboard BLDC hub motor
# --------------------------------------------------------------------------
MOTOR_POLE_PAIRS = 15
MOTOR_TYPE_HIGH_CURRENT = 0  # odrive.enums.MOTOR_TYPE_HIGH_CURRENT

# Hoverboard hub motors have notably higher phase resistance/inductance than
# typical hobby aircraft/actuator motors. These values are conservative starting
# points confirmed against a reference config written specifically for hoverboard
# motors on ODrive v3.6 (see config/odrive_config.py for full annotations).
MOTOR_CURRENT_LIM = 15.0  # A — live-tuned at the bench 21 July 2026 (was 10.0 conservative
                          # first pass); still conservative/bench-safe. See docs/decisions.md
                          # ("Live gain tuning" entry). May need revisiting once real cable
                          # load (not a free-spinning wheel) is introduced in 2A.
MOTOR_REQUESTED_CURRENT_RANGE = 25.0
# NOTE: config/odrive_config.py's encoder offset calibration retry loop (open item
# #14) has a tier-2 diagnostic path that temporarily lowers the live board's
# calibration_current to 3.0 if 5 attempts at this default all fail. That's a
# runtime experiment scoped to that script's retry loop, not a change to this
# project-wide default — if a live board dump ever shows 3.0 here, that's why.
MOTOR_CALIBRATION_CURRENT = 5.0
MOTOR_RESISTANCE_CALIB_MAX_VOLTAGE = 4.0
MOTOR_CURRENT_CONTROL_BANDWIDTH = 100  # reduced from ODrive's default for stability
                                       # given this motor's higher inductance

# Fallback estimate carried over from Layer B WHAT planning (23 July 2026,
# exercise_tab_WHAT_plan.md §4.6): 8.27 / 16, using ODrive's published
# hoverboard-motor KV fallback of ~16. This replaces the old 0.06 placeholder,
# which was wrong by roughly an order of magnitude. Still a FALLBACK ESTIMATE,
# NOT a bench-measured value — the hand-spin KV measurement (open item #13) is
# the trustworthy path before this number is relied on for any reported
# result. Used by core/hardware to compute torque_est = MOTOR_TORQUE_CONSTANT
# * current_iq, and (Layer A, exercise_tab_build_spec_layerA.md §3.2) as the
# one force->torque conversion site alongside SPOOL_RADIUS_M for
# CALIB_HOLD_FORCE_N. NOTE: raising this also raises OdriveHardware's derived
# torque clamp ceiling (current_lim * torque_constant) on the Control/Profiles
# tabs' TorqueMode/ProfileMode — a real, visible, spec-mandated behavior
# change on those tabs, not just an Exercise-tab-local one (docs/decisions.md,
# "Exercise tab Layer A" entry).
MOTOR_TORQUE_CONSTANT = 0.516875  # Nm/A, fallback estimate (8.27 / 16)

# --------------------------------------------------------------------------
# Encoder — onboard AS5047P magnetic encoder (SPI, absolute)
# --------------------------------------------------------------------------
ENCODER_MODE_SPI_ABS_AMS = 257  # odrive.enums.ENCODER_MODE_SPI_ABS_AMS
# Specific to this MKS clone board (confirmed via community reports) — differs
# from genuine ODrive Pro/S1 pin numbers.
ENCODER_ABS_SPI_CS_GPIO_PIN = 7
ENCODER_CPR = 16384  # AS5047P is 14-bit -> 2^14
# NOTE: same tier-2 diagnostic path as MOTOR_CALIBRATION_CURRENT above (open item
# #14) temporarily lowers encoder.config.bandwidth to 1000 on the live board if the
# tier-1 retry loop exhausts all 5 attempts at this default. If a live board dump
# ever shows 1000 here, see the retry loop in config/odrive_config.py, not this file.
ENCODER_BANDWIDTH = 3000
ENCODER_CALIB_RANGE = 10

# --------------------------------------------------------------------------
# Controller — live-tuned at the bench, 21 July 2026 (open item #7, resolved)
# --------------------------------------------------------------------------
# These are no longer generic placeholders — they were tuned live at the bench
# with a working saved encoder calibration, starting conservative and stepping
# up gain-by-gain only once each step was confirmed smooth (no oscillation, no
# overshoot). Full session writeup: docs/decisions.md ("Live gain tuning" entry,
# 21 July 2026). Caveat: tuned against a free-spinning wheel with no cable load —
# may still need re-tuning once real cable load is introduced in later 2A work.
CONTROL_MODE_POSITION_CONTROL = 3  # odrive.enums.CONTROL_MODE_POSITION_CONTROL
INPUT_MODE_TRAP_TRAJ = 5  # odrive.enums.INPUT_MODE_TRAP_TRAJ
CONTROLLER_VEL_LIMIT = 2.0  # turns/s
CONTROLLER_POS_GAIN = 6.0
CONTROLLER_VEL_GAIN = 0.05
CONTROLLER_VEL_INTEGRATOR_GAIN = 0.1

TRAP_TRAJ_VEL_LIMIT = 1.0  # turns/s
TRAP_TRAJ_ACCEL_LIMIT = 1.0  # turns/s^2
TRAP_TRAJ_DECEL_LIMIT = 1.0  # turns/s^2

# TODO(2A): enable_torque_mode_vel_limit — ODrive's torque mode velocity limiter
# may fight a profile layer (Session 3's core/profiles/) doing its own
# velocity-dependent control. Decision waits for real hardware in Phase 2A.

# --------------------------------------------------------------------------
# Resistance profile layer (Session 3) — tuning placeholders
# --------------------------------------------------------------------------
# Cable spool/drum radius: the one number that converts cable-force Newtons
# (the profiles' public parameter surface, spec §4) into motor torque Nm.
# Used by exactly one function, core/profiles/units.py::force_to_torque().
# Measured with a ruler against the physical spool, 23 July 2026 (Layer B
# §2.3) — no longer a placeholder. Was 0.05 (placeholder) through Layer A;
# several Layer A comments below still show numbers computed against the old
# value where only the comment (not the enforced behaviour) is stale — see
# docs/decisions.md ("Exercise tab Layer B" entry) for which ones needed a
# real recompute (HOMING_TIMEOUT_S, SPOOL_CORRECTION_K_BOUNDS) vs. just a
# comment update.
SPOOL_RADIUS_M = 0.035

# Eccentric-overload multiplier default. Charter target band is 1.2-1.5x.
# TODO(2A): tune against real cable motion / user feedback.
ECCENTRIC_OVERLOAD_RATIO_DEFAULT = 1.35

# Phase detector / rep counter tuning. All placeholders chosen only to work
# against the sim's smooth motion — every one of these needs re-tuning
# against real cable motion in Phase 2A.
# TODO(2A): tune against real cable motion.
PHASE_VEL_THRESHOLD_TURNS_S = 0.05  # |v| below this counts as "at rest" (a hold)
PHASE_HYSTERESIS_TURNS_S = 0.02  # extra margin required to leave a hold/reverse
REP_EWMA_ALPHA = 0.05  # position EWMA smoothing factor, applied once per 50 Hz tick
REP_PROXIMITY_TURNS = 0.1  # how close position must return to the EWMA to count a rep

# --------------------------------------------------------------------------
# Exercise tab, Layer A (cable-attached positioning & safety) — tuning values.
# All chosen against this board's live config/gains as of 23 July 2026
# (CONTROLLER_VEL_LIMIT=2.0 turns/s, TRAP_TRAJ_VEL_LIMIT=1.0 turns/s,
# MOTOR_CURRENT_LIM=15.0A, SPOOL_RADIUS_M=0.05m). Full reasoning for each in
# docs/decisions.md ("Exercise tab Layer A" entry) — these are exactly the
# values the bench will end up re-tuning once a cable is actually attached.
# --------------------------------------------------------------------------

# Homing — slow current-limited reel-in until the cable goes taut.
HOMING_CURRENT_THRESHOLD_A = 0.8  # user-specified starting point (spec §5)
HOMING_CURRENT_LIMIT_A = 3.0  # ~3.75x margin above threshold, 5x below the
                              # 15A operating limit — a snag during the blind
                              # reel-in phase can't develop full torque.
HOMING_VELOCITY_TURNS_S = 0.15  # ~15% of TRAP_TRAJ_VEL_LIMIT; at the measured
                                # SPOOL_RADIUS_M=0.035m this is ~3.3 cm/s cable
                                # speed (was ~4.7 cm/s against the old 0.05m
                                # placeholder) — slow enough to watch and abort
                                # by hand on the first live run (spec §10).
HOMING_DEBOUNCE_SAMPLES = 5  # 100ms at 50Hz — filters single-sample
                             # transients without meaningfully delaying
                             # detection at HOMING_VELOCITY_TURNS_S.
HOMING_STARTUP_GRACE_S = 0.3  # 15 ticks at 50Hz; generous margin over typical
                              # BLDC current inrush settling time.
HOMING_MAX_TRAVEL_TURNS = 50.0  # ~11.0m of cable at the measured
                                # SPOOL_RADIUS_M=0.035m (was ~15.7m against the
                                # old 0.05m placeholder) — still a generous
                                # backstop bound (real cable machines run
                                # <3m), not a tight one; the time bound below
                                # is the practically-relevant one.
HOMING_TIMEOUT_S = 130.0  # Recomputed for the measured SPOOL_RADIUS_M=0.035m
                          # (Layer B §2.3) — this is a real value change, not
                          # just a comment update. At HOMING_VELOCITY_TURNS_S,
                          # cable speed dropped from ~4.7 to ~3.3 cm/s with the
                          # radius correction, so the old 90s budget (~64s
                          # worst-case reel-in from a generous 3m real-world
                          # max extension, plus ~41% margin) would now cover
                          # only ~91s of worst-case reel-in with the *new*
                          # cable speed — essentially zero margin, or an
                          # outright false timeout fault on a legitimate slow
                          # homing run. Recomputed: ~91s worst-case at the new
                          # speed, same ~41% margin factor as before -> ~129s,
                          # rounded to 130s.

# Max-extension calibration — light constant tension while the user pulls.
CALIB_HOLD_FORCE_N = 3.0  # single-digit N, trivially overcome by hand; enough
                          # to keep a lightweight cable/webbing taut.
MAX_EXTENSION_SAFETY_MARGIN_M = 0.05  # 5cm inside the physically marked point.
MAX_EXTENSION_MIN_TRAVEL_TURNS = 0.5  # ~11.0cm of cable at the measured
                                      # SPOOL_RADIUS_M=0.035m (was ~15.7cm
                                      # against the old 0.05m placeholder) --
                                      # below this, a marked max is rejected
                                      # as implausibly close to home (spec
                                      # §3.2) rather than stored as a
                                      # degenerate/inverted travel range.

# Length-based control — runtime out-of-range guard (spec §3.4 mechanism 2).
POSITION_GUARD_TOLERANCE_TURNS = 0.05  # ~1.1cm of cable at the measured
                                       # SPOOL_RADIUS_M=0.035m (was ~1.57cm
                                       # against the old 0.05m placeholder) —
                                       # small enough to catch real problems
                                       # quickly, larger than ordinary
                                       # position-control settling/overshoot.

# Spool geometry correction factor k (r_eff(theta) = r0 + k*theta).
SPOOL_CORRECTION_K_DEFAULT = 0.0  # un-calibrated default = fixed-radius model
SPOOL_CORRECTION_K_BOUNDS = (-0.00035, 0.00035)  # m/rad. Recomputed for the
                                                 # measured SPOOL_RADIUS_M=
                                                 # 0.035m (Layer B §2.3) — a
                                                 # real value change, not just
                                                 # a comment update. Two
                                                 # constraints set this: (1)
                                                 # physical plausibility -- a
                                                 # several-mm cable/webbing
                                                 # thickness spread over a
                                                 # full wrap (2*pi rad)
                                                 # implies |k| on the order of
                                                 # 1e-4-1e-3 m/rad, still true
                                                 # at the corrected radius; (2)
                                                 # the r_eff=r0+k*theta model
                                                 # must stay non-degenerate
                                                 # (r_eff > 0) across the whole
                                                 # plausible operating range --
                                                 # at the OLD r0=0.05m and the
                                                 # old +-0.0005 bound, that
                                                 # margin was theta =
                                                 # r0/0.0005 ~= 100 rad; left
                                                 # unchanged, the new, smaller
                                                 # r0=0.035m would only reach
                                                 # ~70 rad (~2.4m of cable) at
                                                 # the same bound -- tightened
                                                 # to +-0.00035 to restore the
                                                 # same ~100 rad (~3.5m)
                                                 # margin. (A looser bound
                                                 # originally, +-0.01, let a
                                                 # legitimately-in-range k
                                                 # break the model within a
                                                 # single turn of travel --
                                                 # caught by core/tests/
                                                 # test_geometry.py's
                                                 # round-trip property test,
                                                 # not by inspection; same
                                                 # class of error this
                                                 # recompute avoids repeating.)
SPOOL_CALIBRATION_MIN_THETA_M_RAD = 1.0  # below this, L ~= r0*theta dominates
                                         # and k's contribution is too small
                                         # relative to measurement error to
                                         # reliably back out (spec §3.3 guard).

# --------------------------------------------------------------------------
# Axis — axis0 only; axis1 is a ghost node
# --------------------------------------------------------------------------
# This board only ever drives axis0. Axis1's CAN node ID must be set to 63 to
# silence it (a Phase 2B concern — CAN HAT wiring — recorded here per plan).
ACTIVE_AXIS = 0
AXIS0_CAN_NODE_ID = 0
AXIS1_CAN_NODE_ID = 63
CAN_BAUD_RATE = 500000

# --------------------------------------------------------------------------
# Bus-level limits
# --------------------------------------------------------------------------
BRAKE_RESISTANCE = 2.0  # ohm — confirmed against the physical resistor, 50W
                        # rated (Layer B §2.4, 23 July 2026). No longer a
                        # placeholder value that happened to match; this is
                        # the actual, measured/rated component.
DC_BUS_UNDERVOLTAGE_TRIP_LEVEL = 8.0
DC_BUS_OVERVOLTAGE_TRIP_LEVEL = 25.0  # capped for bench PSU testing; raise before
                                      # battery phase (~42V)
DC_MAX_POSITIVE_CURRENT = 15.0
# Tightened from -3.0 (Layer B §2.4, 23 July 2026) — the old value was an
# unjustified placeholder ("brake resistor wattage tbc"), not derived from
# what the supply can actually absorb. The Manson HCS-3202 bench PSU is a
# switching supply, treated as unable to sink any reverse current at all.
# This property is the ODrive-side backstop (faults with
# DC_BUS_OVER_REGEN_CURRENT before real current reaches the supply) — it is
# NOT the primary defense; MAX_REGEN_CURRENT=0 below is, by routing regen
# through the brake resistor before it ever reaches the bus. Chosen at the
# tight/conservative end of a justified -0.5 to -1.0A range: at this bench's
# ~13-15V bus, -0.5A bounds any reverse-current excursion to <=7.5W before
# faulting — small enough to be a real backstop (not a formality), wide
# enough above typical current-sense noise/quantization on this hardware to
# avoid nuisance faults during normal, correctly-braked operation. If this
# proves too tight in practice (nuisance faults with the brake resistor
# genuinely absorbing regen correctly), loosen toward -1.0A, not the reverse
# — the philosophy here is "assume the PSU can't sink current," so any
# widening should stay inside the originally-justified range.
DC_MAX_NEGATIVE_CURRENT = -0.5
MAX_REGEN_CURRENT = 0  # Confirmed correct as-is (Layer B §2.4): this is the
                       # primary defense — the brake resistor is configured
                       # to shunt regen before it reaches the bus at all, so
                       # zero bus-side regen current is the intended, correct
                       # value, not an unresolved placeholder.


def check_firmware(fw_major, fw_minor, fw_revision):
    """Return a human-readable warning if a connected board's firmware doesn't
    match what this project targets, else None. Callers should warn, never
    raise — per spec, a firmware mismatch is not a reason to refuse a
    connection, only to flag it."""
    if (fw_major, fw_minor, fw_revision) == (
        EXPECTED_FW_VERSION_MAJOR,
        EXPECTED_FW_VERSION_MINOR,
        EXPECTED_FW_VERSION_REVISION,
    ):
        return None
    return (
        f"Connected board reports firmware {fw_major}.{fw_minor}.{fw_revision}, "
        f"but this project targets v{EXPECTED_FW_VERSION_STRING} only "
        f"(v0.5.6 breaks motor activation on this board's clone — do not upgrade)."
    )


def as_dict():
    """JSON-serializable view of these constants, for the /api/board-constants route."""
    return {
        "firmware": {
            "expected_version": EXPECTED_FW_VERSION_STRING,
            "expected_major": EXPECTED_FW_VERSION_MAJOR,
            "expected_minor": EXPECTED_FW_VERSION_MINOR,
            "expected_revision": EXPECTED_FW_VERSION_REVISION,
            "odrive_python_package_version": ODRIVE_PYTHON_PACKAGE_VERSION,
        },
        "motor": {
            "pole_pairs": MOTOR_POLE_PAIRS,
            "motor_type": MOTOR_TYPE_HIGH_CURRENT,
            "current_lim": MOTOR_CURRENT_LIM,
            "requested_current_range": MOTOR_REQUESTED_CURRENT_RANGE,
            "calibration_current": MOTOR_CALIBRATION_CURRENT,
            "resistance_calib_max_voltage": MOTOR_RESISTANCE_CALIB_MAX_VOLTAGE,
            "current_control_bandwidth": MOTOR_CURRENT_CONTROL_BANDWIDTH,
            "torque_constant": MOTOR_TORQUE_CONSTANT,
        },
        "encoder": {
            "mode": ENCODER_MODE_SPI_ABS_AMS,
            "abs_spi_cs_gpio_pin": ENCODER_ABS_SPI_CS_GPIO_PIN,
            "cpr": ENCODER_CPR,
            "bandwidth": ENCODER_BANDWIDTH,
            "calib_range": ENCODER_CALIB_RANGE,
        },
        "controller": {
            "control_mode": CONTROL_MODE_POSITION_CONTROL,
            "input_mode": INPUT_MODE_TRAP_TRAJ,
            "vel_limit": CONTROLLER_VEL_LIMIT,
            "pos_gain": CONTROLLER_POS_GAIN,
            "vel_gain": CONTROLLER_VEL_GAIN,
            "vel_integrator_gain": CONTROLLER_VEL_INTEGRATOR_GAIN,
            "trap_traj_vel_limit": TRAP_TRAJ_VEL_LIMIT,
            "trap_traj_accel_limit": TRAP_TRAJ_ACCEL_LIMIT,
            "trap_traj_decel_limit": TRAP_TRAJ_DECEL_LIMIT,
        },
        "exercise": {
            "homing_current_threshold_a": HOMING_CURRENT_THRESHOLD_A,
            "homing_current_limit_a": HOMING_CURRENT_LIMIT_A,
            "homing_velocity_turns_s": HOMING_VELOCITY_TURNS_S,
            "homing_debounce_samples": HOMING_DEBOUNCE_SAMPLES,
            "homing_startup_grace_s": HOMING_STARTUP_GRACE_S,
            "homing_max_travel_turns": HOMING_MAX_TRAVEL_TURNS,
            "homing_timeout_s": HOMING_TIMEOUT_S,
            "calib_hold_force_n": CALIB_HOLD_FORCE_N,
            "max_extension_safety_margin_m": MAX_EXTENSION_SAFETY_MARGIN_M,
            "max_extension_min_travel_turns": MAX_EXTENSION_MIN_TRAVEL_TURNS,
            "position_guard_tolerance_turns": POSITION_GUARD_TOLERANCE_TURNS,
            "spool_correction_k_default": SPOOL_CORRECTION_K_DEFAULT,
            "spool_correction_k_bounds": list(SPOOL_CORRECTION_K_BOUNDS),
            "spool_calibration_min_theta_m_rad": SPOOL_CALIBRATION_MIN_THETA_M_RAD,
            "spool_radius_m": SPOOL_RADIUS_M,
        },
        "axis": {
            "active_axis": ACTIVE_AXIS,
            "axis0_can_node_id": AXIS0_CAN_NODE_ID,
            "axis1_can_node_id": AXIS1_CAN_NODE_ID,
            "can_baud_rate": CAN_BAUD_RATE,
        },
        "bus": {
            "brake_resistance": BRAKE_RESISTANCE,
            "dc_bus_undervoltage_trip_level": DC_BUS_UNDERVOLTAGE_TRIP_LEVEL,
            "dc_bus_overvoltage_trip_level": DC_BUS_OVERVOLTAGE_TRIP_LEVEL,
            "dc_max_positive_current": DC_MAX_POSITIVE_CURRENT,
            "dc_max_negative_current": DC_MAX_NEGATIVE_CURRENT,
            "max_regen_current": MAX_REGEN_CURRENT,
        },
    }
