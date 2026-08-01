# Smart Gym Control ("Freddy") — User Manual

A practical guide to running and using the GUI. For *why* things were built this
way, see `decisions.md`; for what's been verified done, see `progress.md`. This
file is just: how do I use it.

**Rewritten 28 July 2026** to match the current four-tab app (Configuration /
Control / Train / Inspector) — the previous version described an eight-tab
layout (Presets, Dashboard, Profiles, and a standalone Exercise tab) that no
longer exists. See §7 for what changed and what, if anything, was lost.

Current state: real hardware is wired up (Phase 2A bring-up, ongoing) and this
is the primary way the project runs day to day. Everything below also still
works with no ODrive attached via the built-in **mock device**
(`ODRIVE_MOCK=1` / `npm run mock_dev`) — useful for UI development or a demo
away from the bench.

---

## 1. Starting the app

**Easiest**: double-click **`Start Freddy.command`** in Finder (project root).
It kills any stale backend/frontend on ports 5050/3000, starts both fresh
against **real hardware** (no mock), waits for both to come up, and opens
Safari automatically. Use **`Stop Freddy.command`** to shut both down again —
they run detached (`nohup`), so closing the Terminal window alone does not
stop them.

Manually, from the project root with the Python venv active:

```bash
source .venv/bin/activate
python backend/start_backend.py     # backend, real hardware
```

```bash
cd frontend
npm run dev:frontend    # frontend only — talks to the backend already running above
npm run mock_dev         # no hardware needed — spins up its own mock backend + frontend
```

**Do not use plain `npm run dev`** for real hardware — it spins up a *second*
backend via `concurrently`, using its own (non-activated) Python environment,
which can be missing Flask entirely and risks a second process contending for
the same USB device.

Once running:

- UI: `http://localhost:3000`
- Backend: `http://127.0.0.1:5050` (the frontend talks to this automatically —
  you never need to open it directly; not port 5000, which macOS's own
  AirPlay Receiver silently squats on)

If you see `No ODrive device found` in the sidebar, that's expected with no
hardware and no mock — either wire up a device and hit **Scan**, or restart
with `mock_dev`.

---

## 2. The sidebar (always visible, regardless of tab)

The left-hand device panel (`DeviceList.jsx`) stays on screen no matter which
tab is open:

- **Scan** — looks for a connected ODrive. Manual only; there's no
  automatic/periodic re-scan, so press it once your device is connected and
  powered on.
- **Connect** / **Disconnect** — on the device card once found.
- **Reset** — forgets the backend's cached device handle/lock and drops the
  frontend's own connection state, for a soft reconnect that doesn't touch the
  motor, calibration, or the backend process. Reach for **Restart Freddy**
  (top bar, §1) instead if this alone doesn't clear a stuck connection.
- **EMERGENCY STOP** — always available once connected, independent of
  whatever tab or session is active.
- **Device Status** — live Vbus voltage, axis state, motor/supply current,
  encoder position, and (once homed) cable position.
- **Go Home** — jogs the cable back to its homed position from anywhere in
  the app, without needing to open Train's Settings section first. Disabled
  until the cable has been homed at least once. Arms a session automatically
  if none is running, and releases it again once the cable arrives — it will
  not leave a lingering session behind for Train's setup flow to trip over.
  This reuses the same plain position-move action homing itself is built on,
  **not** the homing current-threshold logic — it can't be confused with "cable
  went taut" the way an actual Home run can.

The app's top bar also has a **Restart Freddy** button — a full backend
process restart (heavier than Reset; disabled while a session is running,
same as the Control tab's "Save to NVM").

---

## 3. The four tabs

### 3.1 Configuration — the config wizard

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
  touching Control or Train.
- A factory preset ("Smart Gym Cable — Hoverboard + AS5047P") is available
  from inside the wizard — it's the exact wizard defaults, saved for quick
  reapplication. (The old, separate Presets tab that also offered
  import/export of named snapshots has been removed — see §7.)

### 3.2 Control — velocity/torque/position motor control

Direct, low-level motor control in three modes: **Velocity**, **Torque**, and
**Position**. Always drives the real connected device (or the mock device
under `mock_dev`) — no sim/real switcher.

1. Pick a mode, enter a numeric target (turns/s for velocity, Nm for torque,
   or the Move Distance/Velocity/Accel-Decel fields for a Position move).
   - **Position mode's Move Distance field has a `turns` / `m` unit toggle.**
     Metres are converted to turns on the frontend using the live cable
     spool geometry (`r0`/`k`, read from the same status Train uses) — the
     turns value actually sent is identical to typing turns directly.
     Existing turns-only behaviour is unaffected; `turns` stays the default.
2. **Start** — begins the run. Fails cleanly with a visible error if no
   device is attached (no crash, no hang). While running you get:
   - Live numeric readout: position, velocity, torque, current.
   - Live mini-charts (position/velocity/torque).
   - A **"Set target"** button to retarget live, without stopping.
   - The active CSV log filename (see §5).
3. **STOP** — the red button is always visible and reachable, disabled only
   when nothing is running.

If the hardware reports an error while running, the session stops itself
automatically and the error is shown on screen.

#### Controller Gains

A **Controller Gains** card lets you tune Position Gain, Velocity Gain, and
Velocity Integrator Gain live, without going through the Configuration
wizard:

- Each gain has a slider; dragging updates the number immediately, but the
  value is only written to the device on **release** (so dragging doesn't
  flood the connection with writes).
- Reads the board's current gains once connected, so sliders start from
  whatever's actually on the device.
- **Save to NVM** persists the current gains through a power cycle. This
  briefly reboots the board, so it's disabled while a session is running —
  stop first, then save. Without saving, slider changes are live but
  temporary.

### 3.3 Train — cable-attached positioning, calibration, and resistance training

The primary tab once a cable is physically attached to the spool. Covers
everything the old Exercise tab did (homing, end stops, spool calibration)
plus position-based resistance profiles, in one place.

**Header card**: live Cable position (m, from home), Target force (N),
Commanded torque (Nm), and Max extension (m, or "not calibrated"), plus a
**STOP** button while a Train session is running.

If the cable isn't homed yet, an on-screen notice points you at the
Settings/Startup section below before you can start a Train session; if a
different mode (Control, or the setup session itself) is already running
elsewhere, Train tells you to stop it first — they all share one underlying
`ControlSession`.

#### 3.3.1 Settings / Startup (collapsible, open by default)

- **Start setup session** — arms a session for homing/calibration (this is
  Train's setup flow; internally it's the same `ExerciseMode` machinery the
  old Exercise tab used). **Stop setup session** ends it — a prominent button
  in the section header, not a small ghost button.
- **Homing** — **Home** starts a slow, current-limited reel-in until the
  cable goes taut, which becomes the `0` length reference; **Abort** stops it
  immediately. A badge shows live state (Reeling in… / Homed / Fault:
  travel bound exceeded / Fault: timed out / Aborted). Underneath, **Homing
  velocity** and **Current threshold** are live-adjustable, persisted
  fields — **Update** applies them to the *next* Home, not one already
  running.
- **Max-extension calibration** — once homed, **Start** applies a light
  constant tension while you pull the cable out by hand to a safe maximum;
  **Confirm** stores the limit (slightly inside the marked point, as a
  safety margin); **Cancel** discards the attempt. Two independent toggles
  sit underneath: **Enforce home-side guard during Train** and **Enforce
  max-extension guard during Train** — each can be relaxed on its own; either
  one, when on, hard-stops a Train session if the cable crosses that end of
  the calibrated range. Neither affects the setup session's own guard.
- **Spool calibration** — **Spool radius (r0)**: the bare spool radius before
  any wrap builds up, editable directly (affects every force/velocity
  conversion). **Wrap-growth correction (k)**: how much the effective radius
  grows per turn as cable winds on. Reel out to some position (via Control's
  Position mode — see §3.2), physically measure the actual length, enter it
  under **Measured length**, and hit **Calibrate from measurement** — the
  correction factor is computed for you. You can also **Set k** directly if
  you already know it from a previous calibration.
- **Graph history buffer** — how many seconds of history the Train graphs
  below keep (default 90s), live-adjustable and persisted.

There is **no manual jog/Move control in Train** — for manual jogging, use
the Control tab's own Position mode (§3.2), which already has PI tuning and
now a turns/metres toggle. This was a deliberate simplification made after
the tab's first round of real use; see `docs/decisions.md` ("Train tab
refinements") if you're wondering where Move went.

#### 3.3.2 Resistance profile

Build a position-based resistance profile from one or more **segments**,
each with a **Start**/**End** position (metres) and a **shape**:

- **Constant** — flat force.
- **Linear** — ramps between a start force and an end force across the segment.
- **Bell** — rises from a start force to a peak (at a chosen position) and
  back down to an end force (defaults to 0 → peak → 0, but the edges can be
  raised independently).

**Add segment** appends a new one starting where the last left off; each
segment can be removed individually. A **live preview** graph updates
(debounced) as you edit, showing the draft profile's force-vs-position curve
before you apply it.

- **Save** / **Load** / delete (trash icon) — named profiles persist in your
  browser's local storage so a segment layout doesn't need retyping every
  session. This is a frontend-only convenience; profiles are not synced to
  the backend or to other machines/browsers.
- **Start Train session** (when nothing is running) or **Apply profile**
  (once a session is already running, to change segments live).

#### 3.3.3 Graphs

Two graphs, both with independently-scaled, independently-labelled Y axes
per plotted quantity (each with its own Auto/manual-range control) — so a
small-magnitude quantity is never squashed unreadable next to a
large-magnitude one:

- **Time-series** — Position (actual + target overlay), Velocity, Torque
  against time, over the graph history buffer window from §3.3.1.
- **Force vs. position** — the profile's Planned curve against the Actual
  measured force as the cable moves, so you can see how closely the real
  session is tracking the profile you built.

> **Force calibration is a known, unresolved issue**: displayed/estimated
> force is computed from motor current via `MOTOR_TORQUE_CONSTANT`, which is
> an explicitly-flagged fallback estimate, not a bench-measured value (open
> item — see the master plan doc). Planned vs. measured force can currently
> differ by roughly an order of magnitude. Treat the Actual curve's exact
> numbers as illustrative, not precise, until that constant is properly
> measured.

### 3.4 Inspector

Full raw property tree for the connected device (single axis0 only — axis1
is hidden, it's an unused ghost node on this board). Use this for low-level
poking: reading/writing arbitrary ODrive properties directly, live property
charts, and anything the other tabs don't expose.

---

## 4. What used to be here, and isn't reachable from the UI right now

Two older capabilities are **fully implemented and tested in the backend**
but currently have **no tab or UI control**:

- **Force Feedback** (`ExerciseMode`'s Engage/Disengage concentric/isokinetic
  torque resistance, with a let-go safety detector and a FAULT/Resume flow) —
  reachable only via raw calls to `/api/force/*`, not through Freddy's UI.
- **The Session-3 resistance-profile system** (`ProfileMode`: constant,
  bell-curve strength-curve matching, VBT auto-regulation, eccentric-overload
  wrapper, with live phase/rep detection) — reachable only via a raw
  `mode: "profile"` session start, not through Freddy's UI.

Whether this is a deliberate simplification (Train's segment profiles judged
to cover the same need) or an oversight from the tab cleanup is an open
question — see `docs/decisions.md` ("Frontend consolidation to four tabs")
and the master plan doc's open items. If you need either capability today,
it's a backend/API job, not a UI one.

Also gone, with no replacement needed: the old **Dashboard** tab (a generic
at-a-glance telemetry view — superseded by the sidebar's Device Status panel)
and the old **Presets** tab (named config snapshots — the Configuration
wizard's own factory preset covers the one preset actually in use).

---

## 5. Telemetry logs (CSV)

Every Control or Train run writes a CSV to `logs/` at the project root,
named:

```
telemetry_<timestamp>_<mode>_real.csv
```

- Columns: `timestamp_iso, t_rel_s, mode, target, position_turns,
  velocity_turns_s, current_iq_a, torque_est_nm, phase, rep_count,
  cable_length_m, commanded_force_n, estimated_force_n, cable_velocity_m_s,
  regen_power_w, force_state, power_limiter_active` — populated per-mode;
  columns that don't apply to the current mode are left blank. Columns are
  only ever appended, never reordered or removed, so older logs stay readable
  against this same reference.
- A new file opens automatically on Start and closes on Stop. The active
  filename is shown on screen while running.

---

## 6. Running with vs without hardware

- **Real hardware**: `Start Freddy.command`, or `start_backend.py` +
  `npm run dev:frontend` manually. Starting a session with nothing attached
  fails within a couple of seconds with a clear on-screen error.
- **`npm run mock_dev`**: no hardware needed; the whole app transparently
  drives the built-in mock device instead. Good for UI development or a demo
  away from the bench. CSV filenames still say `_real` even under
  `mock_dev` — the suffix reflects which internal hardware factory the
  session used, not whether the device object itself is the mock.

---

## 7. What changed since the last version of this manual

The previous version of this manual described eight tabs (Configuration,
Presets, Dashboard, Control, Profiles, Exercise, Inspector, Command Console)
and a Layer-B-only Force Feedback section inside Exercise. Since then:

- **Command Console** was removed along with the rest of the old raw-testing
  furniture — if you relied on it for one-off ODrive commands, the Inspector
  tab's property tree is the closest remaining tool.
- **Exercise's homing/max-extension/spool-calibration UI moved into Train**
  (§3.3.1) — same backend routes, same persisted state, just relocated.
- **Force Feedback and the old Profiles tab lost their UI entirely** — see §4.
- **Train** is new since that version (constant/linear/bell segment
  profiles, save/load, the two graphs in §3.3.3).
- The sidebar's **Go Home** and **Reset** buttons, and the top bar's
  **Restart Freddy**, are new conveniences that work regardless of tab.

If something you used to rely on from the eight-tab version isn't mentioned
above, it likely fell into the gap in §4 — flag it, since that gap wasn't a
deliberate, documented decision.
