# Testing tab — how it works, for planning the bench experiments

This isn't a user manual. It's written to brief another Claude session (or
a reader) on exactly what the Testing tab can and can't do, so the two
planned experiments — an endurance/repetition test and a brake-resistor
thermal test — can be planned concretely against what actually exists in
the software today (17 August 2026).

## The Testing tab has two sub-tabs

Both drive the same underlying thing: the Control tab's own `mode:
"position"` session (a trapezoidal position move — distance, velocity,
accel/decel, optional torque limit). Only one control session can be
active at a time app-wide (Control/Train/Testing all share it) — starting
one from Testing will take over from whatever else was running.

### Configure move (unchanged, existing)

One move at a time: Known Weight (kg, for the torque/force calibration
workflow below it), Move Distance (relative to current position, metres or
turns), Move Velocity, Torque Limit (Nm / N / kg). Start begins the move;
while running, the same button becomes Update — change a field, click it,
the move retargets live without stopping. Below it: a torque/force
calibration workflow (see "Torque/force calibration workflow" below) and a
live telemetry chart.

### Repetitive testing (new, 17 August 2026)

Runs a *sequence* of moves, a chosen number of times, without touching
anything mid-run. This is the tool for the endurance test below, and also
the intended way to collect torque/force calibration data (see below) —
Known Weight lives in Configure move above, decoupled from which sub-tab
actually ran the reps, since calibration analysis reads back the
completed run's CSV log after the fact rather than needing a live session.

- **Move list**: add/remove rows, each with its own Move Distance
  (m/turns), Move Velocity, and Torque Limit (Nm/N/kg). No Known Weight
  field here — set it in Configure move before analyzing the run instead.
- **Repetitions**: how many times the whole move list repeats. Example:
  two moves (+0.2 m, then −0.2 m) at 5 repetitions runs 10 individual
  moves total (up-down, up-down, ×5).
- **Settle tolerance** (turns, default 0.02): how close the live position
  has to get to each move's commanded target — and how low velocity has
  to drop — before the sequence advances to the next move. Loosen this if
  moves seem to sit "arrived but waiting" for a while; tighten it for
  more precise per-rep positioning at the cost of slower cycling.
- **Start / Pause / Resume / Stop**: Pause stops the motor immediately and
  remembers exactly where the sequence was; Resume re-issues that same
  move and continues from there. Stop resets the whole sequence back to
  the beginning.
- **Live readout**: "Repetition X/Y — Move A/B", plus the same
  Position/Measured torque/Phase current/Measured force stats Configure
  Move shows.

**Important caveat for planning**: settle detection is inferred
client-side from live telemetry (position within tolerance of the
target, velocity near zero) — there's no "move finished" signal from the
hardware/firmware itself. This works correctly on real hardware. It does
**not** work against the mock backend (`ODRIVE_MOCK=1`) — the mock's
simulated position never actually tracks a commanded move, so a sequence
run against the mock will time out per move (20s) rather than advance.
**Any real testing session must run against real hardware**, not
`npm run mock_dev`.

## Torque/force calibration workflow (rewritten 21 August 2026)

Replaces the old "hang a known weight, hold it still, hit record" workflow.
That approach only ever sampled a static hold, but the raw torque estimate
turned out to be systematically different depending on whether the motor
was actually lifting or lowering (friction opposes whichever way it's
turning) — a static point can't represent either regime, which is why a
calibration built from one could look right at rest and still be
noticeably off once the weight was actually moving.

The new workflow instead reads back a REAL run's telemetry after the fact:

1. Set **Known Weight** (Configure move) to the mass you've hung on the
   cable.
2. Run it through several reps — either Repetitive testing (recommended:
   e.g. two moves, +X/−X, for 5–10 repetitions) or a few manual moves via
   Configure move. Either way this is real hardware only, same caveat as
   above.
3. **Stop** the run.
4. In the "Torque/Force calibration" card, click **Analyze last run**. This
   reads back the CSV log the run just wrote, finds the steady-state
   (constant-velocity, not accelerating/decelerating) portion of every rep
   leg, and shows one candidate point for "up" (lifting) and one for "down"
   (lowering) — each with its rep count and the per-rep raw torque values
   that went into the average, so a run with too few clean reps or an
   implausible spread is visible before it's used.
5. Click **Insert** on whichever direction(s) look right. This is the only
   step that actually saves anything — Analyze is read-only, so a bad run
   can just be discarded by not inserting it.
6. Repeat at a few different known weights (e.g. 5/10/15 kg) — each
   Analyze/Insert pass adds points to whichever direction(s) you inserted,
   and the fit improves as points accumulate, same as before.

Recorded points are now tagged "up" or "down" and fitted as two separate
lines (see `core/cable/torque_calibration.py`'s module docstring for the
full model, including what happens near zero velocity, e.g. an isometric
hold). **Existing calibration points recorded under the old static-hold
workflow have no direction and are not migrated** — `core/cable/state.py`
skips them (with a log warning) on load, so a rig with old points reverts
to the uncalibrated identity model until it's recalibrated under this new
workflow.

## Test 1 — Endurance / repeated-repetition test

Use Repetitive testing directly: hang a real weight on the cable, set up
two moves (e.g. +X m and −X m, so the weight goes up then down — pick X
and the velocity/torque limit to match a realistic rep), set Repetitions
to however many reps you want (e.g. 50), and Start. It runs unattended.

**What to watch, and where:**

- **Testing tab itself**: Position, Measured torque, Phase current,
  Measured force update live throughout, and the same fields are on the
  telemetry chart below (position/torque/force/current/bus
  voltage/estimated power — pick which lines to show).
- **Motor/inverter temperature is NOT shown in the Testing tab.** It's
  only surfaced in the **Inspector tab**, and it's off by default there
  (Inspector's telemetry graphs are opt-in per graph, only `vbus` is on
  by default) — open Inspector and enable the motor/FET temperature
  graphs *before* starting the run if you want that data captured live.
- **CSV log**: every run auto-writes a CSV to `logs/` at the project root
  (`telemetry_<timestamp>_position_real.csv`), closing when the sequence
  stops. Useful for a full post-run plot rather than reading live values
  off the screen — columns include position/velocity/current/torque plus
  `regen_power_w` (see Test 2).

## Test 2 — Brake resistor thermal dissipation

**Short answer to "does the brake resistor only engage when a human yanks
the cable faster than commanded": no.** The brake resistor on this rig is
driven by two independent, separately-tuned mechanisms in the ODrive
firmware:

1. A **current-based path** (`max_regen_current`) that reacts to
   *sustained* regenerative current flowing back into the DC bus.
2. A **voltage-ramp path**, added specifically because a fast/hard human
   pull could spike bus voltage faster than the current-based path alone
   could react to.

Repeated automated lifting/lowering of a hung weight — exactly what Test
1's Repetitive testing sequence already does, no human involved — makes
the motor act as a generator during the lowering phase (gravity is doing
positive work; the motor has to resist/brake to control descent speed,
same as controlled eccentric resistance anywhere else in this system).
That's ordinary sustained regenerative current, and it exercises
mechanism 1 on its own. **You don't need to add a manual yank to generate
brake-resistor activity — Test 1's endurance run already does it, for
free, during every downward rep.**

A manual hard yank is a *separate, additional* test if you specifically
want to stress mechanism 2 (the fast-transient path) — worth doing once
if you want that covered, but it's not required to see the resistor
engage at all, and it's a worse test of *sustained* thermal load than 50
automated reps back-to-back would be.

**How to actually observe this in the software:**

- **Inspector tab → `ibus` graph** (bus current — **off by default**,
  enable it before the run): negative values indicate regenerative/
  braking current flowing back — this is the direct, hardware-measured
  signal for "is the brake resistor path active right now."
- **Inspector tab → `vbus` graph** (on by default): watch for it
  approaching the overvoltage ramp band (24–25 V) — that's the firmware
  actively managing bus voltage via the resistor, distinct from a genuine
  overvoltage fault (27 V trip).
- **CSV log's `regen_power_w` column**: an estimate computed from the
  commanded force/velocity (not a direct hardware measurement of resistor
  power), logged every sample for every position-mode run including
  Repetitive testing sequences. Useful for a post-run "how much regen
  power over the whole session" plot even though it's not shown live in
  the Testing tab chart.
- **What the software can't tell you**: the resistor's actual
  temperature. There's no thermistor on it, and nothing in this app reads
  one. Actual thermal state needs an external measurement — IR
  thermometer, thermal camera, or a hands-on touch-check, the same way
  the initial "runs uncomfortably hot within seconds" observation was
  made during earlier bench testing. Software tells you *when* and
  *roughly how much* regen current is flowing; it doesn't tell you how
  hot the resistor actually gets.

## Practical notes

- Both sub-tabs are gated by the same "another mode running" guard — if
  Train or Control has an active session, Testing won't let you start
  one until that's stopped.
- The "not homed" badge/warning only affects the r_eff/force unit
  conversions (N/kg Torque Limit entry, expected-force display) — it does
  **not** block a move from running. Moves work in raw turns either way;
  homing just makes the metres/force conversions meaningful.
- A repetition sequence can be paused and resumed without losing its
  place — useful if you need to pause an endurance run to check the
  resistor by hand partway through, then continue exactly where it left
  off.
