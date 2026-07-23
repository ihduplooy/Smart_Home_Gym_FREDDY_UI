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

# Measured phase resistance — consistent across every motor calibration run
# on this unit (Layer B §5.2, exercise_tab_build_spec_layerB.md). Distinct
# from MOTOR_TORQUE_CONSTANT: this one is NOT an estimate, it's what
# axis0.motor.config.phase_resistance reads after calibration, live-verified
# via config/odrive_config.py's check_motor_calibration_sane() (docs/
# decisions.md). Used by core/cable/power_limiter.py for the copper-loss
# term (P_copper = 1.5 * Iq^2 * R_phase) in the regen power estimate — the
# one thing standing between "most rep energy stays in the windings" and
# "most rep energy hits the bus," per §5.2's break-even analysis.
MOTOR_PHASE_RESISTANCE_OHM = 0.38  # ohm

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
CONTROLLER_VEL_LIMIT = 10.0  # turns/s
CONTROLLER_POS_GAIN = 6.0
CONTROLLER_VEL_GAIN = 0.05
CONTROLLER_VEL_INTEGRATOR_GAIN = 0.1

TRAP_TRAJ_VEL_LIMIT = 1.0  # turns/s
TRAP_TRAJ_ACCEL_LIMIT = 1.0  # turns/s^2
TRAP_TRAJ_DECEL_LIMIT = 1.0  # turns/s^2

# Open item #8, resolved (Layer B §3.1, exercise_tab_build_spec_layerB.md,
# 23 July 2026): ODrive's torque-mode velocity limiter reduces commanded
# torque based on velocity/vel_gain by default -- directly fights a
# constant-force profile (pull faster, get less force, the opposite of the
# intended behaviour). Decision: disable it and replace it with the
# software governor (core/cable/governor.py) instead of leaving it as an
# implicit consequence of some other write. This REMOVES ODrive's own
# last-resort protection against a torque command running away in an
# unloaded direction -- software now owns that entirely, which is why the
# let-go detector (core/cable/letgo.py) and the velocity ceiling it enforces
# are mandatory, not defensive extras. Property path (axis{n}.controller.
# config.enable_torque_mode_vel_limit, BoolProperty, rw) is corroborated by
# the bundled odriveApiReference05x.json but UNCONFIRMED against this live
# board -- see the "LIVE-BOARD PROPERTY VERIFICATION CHECKLIST" at the top
# of the Layer B Session B1 section below for the full status and the other
# three properties it belongs alongside. Written in core/hardware/
# odrive_hw.py's set_mode() TORQUE branch, applied every time torque mode
# is entered.
ENABLE_TORQUE_MODE_VEL_LIMIT = False

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
# (TRAP_TRAJ_VEL_LIMIT=1.0 turns/s, MOTOR_CURRENT_LIM=15.0A,
# SPOOL_RADIUS_M=0.05m at the time -- see the Layer B note above SPOOL_RADIUS_M
# for the later correction to 0.035m). None of the values below depend on
# CONTROLLER_VEL_LIMIT specifically, so its later live re-tune (2.0 -> 10.0
# turns/s, outside any session's own work) doesn't affect this block's
# reasoning. Full reasoning for each in
# docs/decisions.md ("Exercise tab Layer A" entry) — these are exactly the
# values the bench will end up re-tuning once a cable is actually attached.
# --------------------------------------------------------------------------

# Homing — slow current-limited reel-in until the cable goes taut.
HOMING_CURRENT_THRESHOLD_A = 2.0  # Raised from 0.8 (bench re-tune, 23 July
                                  # 2026) — expect-to-tune-at-the-bench value
                                  # (spec §5), moved up presumably against
                                  # real noise/stiction on the live board.
HOMING_CURRENT_LIMIT_A = 7.5  # Recomputed to track HOMING_CURRENT_THRESHOLD_A
                              # (raised alongside it, 23 July 2026) — kept at
                              # the same ~3.75x margin above threshold this
                              # constant has always used (was 3.0A at the old
                              # 0.8A threshold; left at 3.0A against the new
                              # 2.0A threshold, the margin would have dropped
                              # to only 1.5x, too tight against noise for a
                              # detection-threshold-relative safety limit).
                              # Still well below the 15A operating limit
                              # (2x, down from 5x before) — a snag during the
                              # blind reel-in phase still can't develop full
                              # torque, just with less headroom than before.
HOMING_VELOCITY_TURNS_S = 0.5  # Raised from 0.15 (bench re-tune, 23 July
                               # 2026). At the measured SPOOL_RADIUS_M=0.035m
                               # this is ~11.0 cm/s cable speed (was ~3.3
                               # cm/s) — faster than the original "slow
                               # enough to watch and abort by hand" framing
                               # (spec §10) assumed; still watchable, but
                               # re-attend the first live run at this speed
                               # rather than assuming the original caution
                               # still fully applies.
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
HOMING_TIMEOUT_S = 130.0  # Originally recomputed for the measured
                          # SPOOL_RADIUS_M=0.035m (Layer B §2.3): at the
                          # HOMING_VELOCITY_TURNS_S then in force (0.15
                          # turns/s, ~3.3 cm/s), a generous 3m real-world
                          # worst-case reel-in took ~91s, and 130s gave that
                          # ~41% margin. HOMING_VELOCITY_TURNS_S was since
                          # raised to 0.5 turns/s (~11.0 cm/s, 23 July 2026),
                          # dropping the same worst-case reel-in to ~27s —
                          # 130s is now ~4.8x that, not a tight budget
                          # anymore. Left unchanged deliberately: a looser
                          # timeout is still safe (never blocks a legitimate
                          # homing run), just no longer tightly matched to
                          # the current speed — tighten later if a faster
                          # fault-on-genuinely-stuck response is wanted.

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
# Exercise tab, Layer B Session B1 (concentric force feedback) — tuning
# values. Chosen against this board's live config plus the measured
# SPOOL_RADIUS_M=0.035m, MOTOR_PHASE_RESISTANCE_OHM=0.38ohm, and the still-
# estimated MOTOR_TORQUE_CONSTANT=0.516875 (open item #13, unresolved).
# Full reasoning for each in docs/decisions.md ("Exercise tab Layer B"
# entry), including the §5.2 break-even power analysis these numbers feed.
# Two rows from the spec's own §9 table are intentionally NOT added as new
# constants here — see the comments at PHASE_VEL_THRESHOLD_TURNS_S (hold
# detection) and FORCE_MIN_N (isokinetic force floor default) above/below.
#
# LIVE-BOARD PROPERTY VERIFICATION CHECKLIST — required before the first
# live force test (spec §2.4, §15). Four ODrive property writes this layer
# depends on; the bundled API reference has already been wrong once on
# exactly this family of settings (docs/decisions.md, enable_brake_resistor).
# Status as of this session (23 July 2026), no live hardware access:
#   [confirmed]     odrv0.config.brake_resistance          -- via
#                    config/odrive_config.py's own live-run comments
#   [confirmed]     odrv0.config.dc_max_negative_current    -- ditto
#   [confirmed]     odrv0.config.max_regen_current          -- ditto
#   [UNCONFIRMED]   axis0.controller.config.enable_torque_mode_vel_limit
#                    -- path corroborated only by odriveApiReference05x.json
#                    (labeled v0.5.6, not this board's exact v0.5.1); no
#                    live dir() cross-check exists for it anywhere in this
#                    codebase yet. Written in core/hardware/odrive_hw.py's
#                    set_mode() TORQUE branch -- if the property name is
#                    wrong on this firmware, it will raise loudly on the
#                    very first torque-mode entry (Control tab's Torque
#                    mode, Profiles, or Layer B force test alike), not
#                    silently no-op. Confirm against dir(axis0.controller.
#                    config) before relying on the first three being enough.
# --------------------------------------------------------------------------

# Force ceiling/floor.
FORCE_MAX_N = 150.0  # Hard ceiling on commanded cable force. Bound by two
                     # independent things: (1) _TORQUE_LIMIT_NM (core/
                     # hardware/odrive_hw.py) = MOTOR_CURRENT_LIM *
                     # MOTOR_TORQUE_CONSTANT = 15A * 0.516875 = 7.753 Nm ->
                     # F = torque/SPOOL_RADIUS_M ~= 221.5 N is the absolute
                     # structural ceiling; (2) thermal -- at 150N, Iq~=10.16A,
                     # P_copper~=58.8W continuously REGARDLESS of velocity
                     # (heating the motor, not the bus -- see the
                     # MOTOR_PHASE_RESISTANCE_OHM comment above), and this
                     # board has no thermal sensing (open item #1). 150N sits
                     # well below the structural ceiling (spec §9: "start
                     # well below what the hardware can do") while still
                     # being a meaningful heavy-pull force for early testing.
                     # The §14 first-live-run protocol starts at the LOWEST
                     # force and escalates by hand while checking motor
                     # temperature -- this constant is the software ceiling
                     # that testing approaches gradually, not a recommended
                     # starting point.
FORCE_MIN_N = 5.0  # Hold-state floor (spec §4.1: HOLDING drops to a low hold
                   # force, never a hard zero -- that would drop the load).
                   # Also reused, per spec §9's "F_base may be non-zero"
                   # note, as ISOKINETIC's default force-floor constant --
                   # no separate ISOKINETIC_FORCE_BASE_N added, since both
                   # describe the identical physical concept: "enough tension
                   # to not drop/slacken the load, low enough to be
                   # harmless." Same order of magnitude as Layer A's
                   # CALIB_HOLD_FORCE_N=3.0N, slightly higher since this hold
                   # happens under a real workout load, not just a bare
                   # cable during calibration.

# Ramps (spec §4.2, §6 item 2: force ramps, never steps). Implemented as a
# fixed slew RATE (FORCE_MAX_N / *_S), not a fixed duration re-normalized per
# target -- deviation from the spec's literal "ramps ... over
# FORCE_RAMP_IN_S" wording, logged in decisions.md. A rate-based ramp handles
# engage, disengage, AND a live mid-ENGAGED retarget with one mechanism (no
# ramp-start timestamp to track, no special-casing a target that changes
# mid-ramp), and a smaller target than FORCE_MAX_N always ramps in *faster*
# than FORCE_RAMP_IN_S seconds, never slower -- strictly safer than the
# literal reading, never less safe.
FORCE_RAMP_IN_S = 0.5  # Time a full 0->FORCE_MAX_N ramp would take.
FORCE_RAMP_OUT_S = 0.5  # Symmetric with ramp-in -- ramping resistance out
                        # too fast on disengage is a lesser hazard than
                        # ramping it in too fast (it doesn't push/pull the
                        # user unexpectedly), but there's no reason for it to
                        # be faster; kept equal for a predictable feel.

# Hold detection (spec §4.1, §9). HOLD_VELOCITY_THRESHOLD_TURNS_S is
# intentionally NOT a new constant -- reuses PHASE_VEL_THRESHOLD_TURNS_S
# directly, per the spec's own suggestion ("reuse the existing phase
# detector's threshold if it fits rather than adding a parallel one"; see
# core/profiles/detectors.py). ForceMode watches PhaseDetector's existing
# TOP_HOLD/BOTTOM_HOLD classification (already hysteresis-tuned) and adds
# only the duration gate below on top of it, rather than re-implementing
# threshold/hysteresis logic a second time.
HOLD_DURATION_S = 0.75  # How long continuously in a phase-detector hold
                        # phase before Layer B's own HOLDING state is
                        # entered -- long enough to distinguish a deliberate
                        # pause from a quick rep turnaround, short enough not
                        # to feel laggy.

# Isokinetic governor (spec §4.3) — torque-domain velocity cap, no
# integrator anywhere in this path (spec §6 item 5).
ISOKINETIC_VELOCITY_TARGET_TURNS_S = 1.0  # Default speed cap. At
                                          # SPOOL_RADIUS_M=0.035m this is
                                          # ~22 cm/s, a moderate controlled
                                          # training speed. NOT chosen as a
                                          # fraction of CONTROLLER_VEL_LIMIT
                                          # (spec §9's suggested relation) --
                                          # that constant governs ODrive's
                                          # position/velocity control loops,
                                          # but Layer B runs in torque mode
                                          # with ENABLE_TORQUE_MODE_VEL_LIMIT
                                          # =False (spec §3.1), so it does
                                          # not bound velocity here at all.
                                          # This is exactly why the governor
                                          # itself (this gain + target) is
                                          # the only thing capping speed in
                                          # isokinetic mode, and why constant-
                                          # force mode has NO software speed
                                          # cap at all (see decisions.md).
ISOKINETIC_GOVERNOR_GAIN = 150.0  # N per (turn/s) above target -- a firm,
                                  # quickly-felt "wall": at FORCE_MIN_N=5.0
                                  # base, exceeding the target by ~1 turn/s
                                  # already reaches FORCE_MAX_N.
ISOKINETIC_VELOCITY_FILTER_ALPHA = 0.3  # EWMA smoothing applied to the
                                        # velocity estimate before it reaches
                                        # the governor (spec §4.3: "filtering
                                        # ... is likely necessary; check").
                                        # Much lighter than REP_EWMA_ALPHA=
                                        # 0.05 (core/profiles/detectors.py,
                                        # time constant ~20 ticks/0.4s,
                                        # tuned for rep-boundary detection,
                                        # not live force control) -- alpha=
                                        # 0.3 (~3 ticks/60ms time constant)
                                        # smooths single-sample encoder noise
                                        # (16384 CPR is "reasonably clean"
                                        # per spec §4.3) without making the
                                        # governor feel laggy against a real
                                        # velocity change.

# Let-go detector (spec §4.4, §6 items 3/4) — active in concentric only,
# gated by ForceMode's state, tested explicitly for that gating.
LETGO_VELOCITY_TURNS_S = 0.1  # Reel-in speed indicating nothing is holding
                              # the cable during concentric. 2x
                              # PHASE_VEL_THRESHOLD_TURNS_S=0.05 (the "at
                              # rest" threshold) -- a clear, unambiguous
                              # reel-in signal, not a noise-floor value that
                              # would false-trigger on ordinary settling.
LETGO_DEBOUNCE_SAMPLES = 5  # Matches HOMING_DEBOUNCE_SAMPLES exactly, per
                            # spec §9's explicit suggestion (~100ms at 50Hz).

# Power limiter (spec §5.3) — derived from §5.1/§5.2, not guessed.
REGEN_POWER_BUDGET_W = 30.0  # Brake resistor is 2ohm/50W rated (Layer B
                             # §2.4), no forced cooling (open item #1 -- a
                             # fan is "later"). Derated to 60% of rated
                             # dissipation for sustained continuous duty in
                             # still air (a common no-forced-cooling
                             # derating factor) -> 30W. This bounds the
                             # ESTIMATED REGEN power (post-copper-loss, what
                             # core/cable/power_limiter.py computes as
                             # P_mech - P_copper) actually reaching the brake
                             # resistor/bus -- not raw mechanical power, and
                             # not the separate, unsensored thermal
                             # (copper-heating-the-motor) concern flagged in
                             # §5.2, which this limiter does not and cannot
                             # protect against.

# Max-extension force taper (spec §4.5) — distance-based, not time-based:
# force eases off as the cable approaches the physical limit under load,
# rather than holding full force until Layer A's runtime guard trips.
MAX_EXTENSION_FORCE_TAPER_M = 0.15  # 3x MAX_EXTENSION_SAFETY_MARGIN_M
                                    # (0.05m) -- starts well before the
                                    # enforced limit itself (which already
                                    # sits inside the physically marked
                                    # point by that margin), giving a
                                    # gentle, perceptible ease-off rather
                                    # than a last-moment flinch.

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
            "enable_torque_mode_vel_limit": ENABLE_TORQUE_MODE_VEL_LIMIT,
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
        "force": {
            "force_max_n": FORCE_MAX_N,
            "force_min_n": FORCE_MIN_N,
            "force_ramp_in_s": FORCE_RAMP_IN_S,
            "force_ramp_out_s": FORCE_RAMP_OUT_S,
            "hold_duration_s": HOLD_DURATION_S,
            "isokinetic_velocity_target_turns_s": ISOKINETIC_VELOCITY_TARGET_TURNS_S,
            "isokinetic_governor_gain": ISOKINETIC_GOVERNOR_GAIN,
            "isokinetic_velocity_filter_alpha": ISOKINETIC_VELOCITY_FILTER_ALPHA,
            "letgo_velocity_turns_s": LETGO_VELOCITY_TURNS_S,
            "letgo_debounce_samples": LETGO_DEBOUNCE_SAMPLES,
            "regen_power_budget_w": REGEN_POWER_BUDGET_W,
            "max_extension_force_taper_m": MAX_EXTENSION_FORCE_TAPER_M,
            "motor_phase_resistance_ohm": MOTOR_PHASE_RESISTANCE_OHM,
            "torque_constant_is_estimate": True,  # spec §10.3: UI honesty label
                                                   # gate. Flip to False only
                                                   # once open item #13 (KV
                                                   # hand-spin measurement)
                                                   # lands.
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
