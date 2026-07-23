# Smart Gym Control — User Manual

A practical guide to running and using the GUI. For *why* things were built this
way, see `decisions.md`; for what's been verified done, see `progress.md`. This
file is just: how do I use it.

Current state: real hardware is wired up and this is now the primary way the
project runs (Phase 2A bring-up, ongoing). Everything below also still works
with no ODrive attached via the built-in **mock device** (`npm run mock_dev`)
— useful for UI development or a demo away from the bench.

The Control and Profiles tabs' own internal software simulator (a separate,
simpler dynamics model, distinct from the mock device above) has been
**removed** — those tabs always drive whatever's actually connected now (a
real board, or the mock device if you're running `mock_dev`). See §2.4/§2.5.

---

## 1. Starting the app

From the project root, with the Python venv active:

```bash
# Real hardware (once an ODrive is actually connected)
npm run dev

# No hardware — simulated ODrive device, recommended for now
npm run mock_dev
```

Run either from `frontend/` if the root script isn't set up to proxy — check
`README.md` if a command isn't found. Once running:

- UI: `http://localhost:3000`
- Backend: `http://127.0.0.1:5050` (the frontend talks to this automatically —
  you never need to open it directly)

Leave the terminal running; `Ctrl+C` stops both servers together. There's no
separate "quit" button in the app itself (that was upstream's standalone-app
packaging, removed — see `decisions.md`).

If you see `No ODrive device found` in the sidebar, that's expected with no
hardware and no mock — either wire up a device or restart with `mock_dev`.

---

## 2. The eight tabs

The sidebar switches between eight tabs. They fall into two groups:

- **Setup/inspection tabs** (Configuration, Presets, Dashboard, Inspector,
  Command Console) — for reading/writing raw ODrive properties and getting a
  device calibrated and configured. Carried over from upstream, largely
  unchanged.
- **Control tabs** (Control, Profiles, Exercise) — new in this project, for
  actually driving the motor once it's configured: pick a mode or a
  resistance profile, hit Start, watch live telemetry, hit Stop. Exercise is
  the odd one out here — it's for once a cable is physically attached to the
  spool, and adds homing/end-stops on top rather than raw turns-based control
  (see §2.6).

### 2.1 Configuration — the config wizard

Guided, multi-step wizard for writing this board's known-good settings
(motor, encoder, controller, bus limits) to a connected device.

- Opens **pre-loaded** with this project's values (pole pairs 15, AS5047P on
  SPI CS pin 7, encoder mode 257, cpr 16384, position control, the tuned
  bus-current limits, axis0-only with axis1's CAN node silenced) — these come
  from `config/board_constants.py`, not typed in by hand.
- Step through the wizard normally; the "Apply" step shows a **command
  preview** before anything is written — review it before confirming.
- Toggle **"Only changed parameters"** to limit writes to fields that differ
  from the device's current values, or turn it off to see/write the full set.
- Use this tab first, on a freshly-connected or freshly-erased board, before
  touching Control or Profiles.

### 2.2 Presets

Save, load, import, and export named configuration snapshots (JSON).

- A factory preset **"Smart Gym Cable — Hoverboard + AS5047P"** ships
  pre-loaded — it's the exact config wizard defaults, saved as a preset for
  quick reapplication.
- Loading a preset does not write to the device by itself; it feeds values
  into the wizard/apply flow the same way manual edits would.

### 2.3 Dashboard

Live overview / at-a-glance telemetry for the connected device (or mock).
Good first stop after connecting to confirm the device is alive and
reporting sane values before diving into Inspector or Control.

### 2.4 Control — velocity/torque motor control

Direct, low-level motor control in three modes: **Velocity**, **Torque**, and
**Position**. This is where you actually spin the motor — always the real
connected device now (or the mock device under `mock_dev`); there's no
sim/real switcher here anymore.

1. Pick a mode, enter a numeric target (units shown next to the field —
   turns/s for velocity, Nm for torque, or the Move Distance/Velocity/
   Accel-Decel fields for a Position move).
2. **Start** — begins the run. Fails cleanly with a visible error if no
   device is attached (no crash, no hang). While running you get:
   - Live numeric readout: position, velocity, torque, current.
   - Three live mini-charts (position/velocity/torque).
   - A **"Set target"** button to retarget live, without stopping.
   - The active CSV log filename (see §3 below).
3. **STOP** — the red button is always visible and reachable, disabled only
   when nothing is running. Always available regardless of what else is
   happening on screen — this is the safety-critical control.

If the hardware reports an error while running, the session stops itself
automatically and the error is shown on screen — you don't need to notice it
yourself.

#### Controller Gains

Below the main controls, a **Controller Gains** card lets you tune Position
Gain, Velocity Gain, and Velocity Integrator Gain live, without going through
the Configuration wizard:

- Each gain has a slider. Dragging updates the number shown next to it
  immediately; the value is only written to the device when you **release**
  the slider — so dragging doesn't flood the connection with writes.
- Requires a connected device (the card shows "no device" and a prompt
  otherwise) — it reads the board's current gains once connected, so the
  sliders start from whatever's actually on the device, not some default.
- **Save to NVM** persists the current gains to the board's non-volatile
  memory so they survive a power cycle. This briefly reboots the board (an
  ODrive requirement for `save_configuration`), so the button is disabled
  while a Control or Profiles session is running — stop first, then save.
  Without saving, slider changes are live but temporary — they're gone on
  next reboot.

### 2.5 Profiles — resistance-profile training

A layer on top of Control: instead of a fixed velocity/torque target, pick a
**resistance profile** that computes torque dynamically based on the cable's
motion (position/velocity), plus optional rep counting.

1. **Pick a base profile** from the dropdown (registry-driven — whatever
   profiles the backend reports):
   - **Constant** — flat resistance (force → torque conversion only).
   - **Bell curve** — resistance ramps up/down over a position range,
     peaking mid-range (raised-cosine shape).
   - **VBT** (velocity-based training) — adjusts resistance rep-to-rep based
     on how fast the previous rep was.
   - (**Overload** exists as a *modifier*, not a selectable base profile —
     see next step.)
2. Fill in the profile's parameters — the form is generated from the
   profile's schema (labels, min/max) automatically.
3. Optionally enable **Eccentric overload**: a toggle + ratio + target-phase
   selector that multiplies the resistance during one phase of the rep only
   (e.g. heavier on the lowering/eccentric phase). This wraps whichever base
   profile you picked; you don't pick "overload" itself as the profile.
4. Same always-visible **STOP** as the Control tab — this is the same
   underlying session, just a third mode (also real-device-only now, no
   sim/real switcher — see §2.4).
5. **Start** — while running you get:
   - A color-coded **phase badge** (concentric / top hold / eccentric /
     bottom hold) — this is what the phase detector currently thinks the
     cable is doing.
   - A **rep count**.
   - The same live telemetry/CSV behavior as Control.
6. **"Set target"** lets you retarget the profile's primary parameter live
   (e.g. change the base force) without restarting the session — useful for
   forcing a phase change while testing (a negative force flips the
   direction, for example).

A persistent on-screen notice reminds you the profile math is stub-quality
(`# STUB(2A+)`) — real tuning against actual cable rigging happens in
Phase 2A. Treat exact numeric behavior as illustrative, not final.

**Only one of Control or Profiles can run at a time** (they share one
backend session) — starting one while the other is active is refused with a
visible warning, not a silent conflict.

### 2.6 Exercise — cable-attached positioning & safety

For once a cable is physically attached to the spool. Control and Profiles
stay exactly as they are — raw, turns-based, no-cable bench-testing tools;
Exercise is the tab that makes cable-attached operation safe by giving the
machine a length reference and hard end stops. This is **Layer A** only:
positioning and safety. Force feedback / resistance (Layer B) is planned but
not yet built — Exercise does not resist you, it only positions and limits.

1. **Start Exercise Session** — arms the session; the motor does not move
   yet. This is deliberate: nothing in this tab ever moves the cable except
   an explicit action below.
2. **Home** — slow, current-limited reel-in until the cable goes taut,
   which becomes the `0` length reference. Watch the live position/current
   readout while this runs; **Abort Homing** stops it immediately, and the
   always-present **STOP** works throughout too. If it fails (cable not
   attached, slipping, or genuinely stuck), it faults with a clear reason
   instead of reeling in forever.
3. **Max Extension** — once homed, applies a light constant tension (just
   enough to keep the cable taut, trivially overcome by hand) while you pull
   the cable out by hand to a safe maximum, then **Set Max Here**. The
   enforced limit is stored slightly inside the point you marked, as a
   safety margin. **Cancel** discards the attempt without storing anything.
4. **Move** — command the cable to a target length in metres. Requires both
   Home and Max Extension to be set; both ends are enforced by the motor
   itself, not just the input field.
5. **Advanced: Spool Calibration** (collapsed by default — click to expand)
   — corrects for the spool's effective radius changing as cable winds on
   or off. Reel out to some position (via Move), physically measure the
   actual cable length with a tape measure, and enter it — the correction
   factor is computed for you. You never enter a raw multiplier.
6. **Manual Position Reset** — clears the home reference and max-extension
   limit (e.g. after the cable slips, or a bad homing run). Confirmation-
   gated, and only available while the Exercise session is stopped.

**The home reference and max-extension limit do not survive a backend
restart** — they're intentionally never written to disk (a stale reference
after a restart, power cycle, or period of the motor sitting idle would mean
every safety limit is wrong by the same offset). The spool correction factor
*does* persist, since it's a property of the physical spool, not the current
session — you shouldn't have to recalibrate it every time.

### 2.7 Inspector

Full raw property tree for the connected device (single axis0 only — axis1
is hidden, it's an unused ghost node on this board). Use this for low-level
poking: reading/writing arbitrary ODrive properties directly, live property
charts, and anything the wizard doesn't expose. This is the most "raw"
interface — use Configuration/Presets for normal setup, Inspector when you
need something specific the wizard doesn't cover.

### 2.8 Command Console

Free-form command entry against the device (equivalent to typing into an
ODrive Python console, but through the GUI). Use for one-off commands,
calibration sequences, or anything scriptable that doesn't have a dedicated
UI control.

---

## 3. Telemetry logs (CSV)

Every Control or Profiles run writes a CSV to `logs/` at the project root,
named:

```
telemetry_<timestamp>_<mode>_<sim|real>.csv
```

e.g. `telemetry_20260717_143205_profile-overload_real.csv`.

- Since the Control/Profiles sim/real switcher was removed, this suffix is
  now always `real` — even under `mock_dev`, since it reflects which
  internal hardware factory the session used (always the real one now), not
  whether the underlying device happens to be the mock object. Older `_sim`
  files from before that removal are still valid history, just from a
  different code path.
- Columns: `timestamp_iso, t_rel_s, mode, target, position_turns,
  velocity_turns_s, current_iq_a, torque_est_nm, phase, rep_count,
  cable_length_m` (`phase`/`rep_count` are blank except on Profiles runs;
  `cable_length_m` is blank except on Exercise runs, and even then only once
  homed — an un-homed Exercise run has no length reference yet).
- A new file opens automatically on Start and closes on Stop — you don't
  manage this yourself. The active filename is shown on screen while running.
- Note: for an **Overload**-wrapped run, the filename only says
  `profile-overload` — it doesn't record which base profile was wrapped in
  the filename itself. The wrapped profile's parameters are still in the
  CSV's own columns/backend logs if you need to distinguish runs later.

---

## 4. Running with vs without hardware

There's one way to run the app now, not a per-tab switch — the whole app
(Control/Profiles included) always talks to whatever `device_manager` finds:

- **`npm run dev`** — talks to a real connected ODrive. Starting a Control or
  Profiles run with nothing attached fails within a couple of seconds with a
  clear on-screen error; nothing hangs or crashes.
- **`npm run mock_dev`** — no hardware needed; the whole app, including
  Control/Profiles, transparently drives the built-in mock device instead.
  Good for UI development or a demo away from the bench.

(The Control/Profiles tabs' own separate, simpler software simulator — a
per-tab Sim/Real toggle — has been removed; see §2.4.)

---

## 5. Known rough edges (as of Session 3)

- **Live phase/rep telemetry updates every ~150ms** via polling, not a
  websocket — a deliberate, documented tradeoff (see `decisions.md`). You
  may notice slightly less immediacy than a true push update, but it's
  reliable.
- The **resistance-profile math is a stub** — realistic tuning (cable
  geometry, real strength curves, VBT step sizes) is Phase 2A work.
- **Torque-mode velocity limiting** and the **two-simultaneous-connection**
  case (e.g. Inspector and Control both trying to talk to the same real
  device) are flagged but not yet resolved — avoid having both a
  device-connected inspection tab and a Real-hardware Control/Profiles run
  active at once until Phase 2A addresses this.

---

## 6. Quick reference

| Want to... | Go to |
|---|---|
| Write known-good settings to a fresh board | **Configuration** |
| Save/reload a named config | **Presets** |
| Get a quick device health check | **Dashboard** |
| Spin the motor at a fixed velocity/torque | **Control** |
| Train against a dynamic resistance curve / count reps | **Profiles** |
| Home a cable, set safe end stops, and move it by length | **Exercise** |
| Read or write one specific raw property | **Inspector** |
| Run an arbitrary one-off command | **Command Console** |
| Stop the motor immediately | The red **STOP** button (Control, Profiles, or Exercise tab, always visible while running) |
