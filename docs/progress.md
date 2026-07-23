# Session 1 progress — smart-gym-control

Tracks the four-step plan from spec §7 ("Suggested Claude Code session shape").
Checked items are done AND verified (code actually ran). Never mark done speculatively.

Path note: spec says the 1B script lives at `Developer/odrive_config_1B.py`; the
actual file found on disk is `Phase 1/odrive_config_1B.py` (no `Developer/`
subfolder exists in this project). Treated as the same file — logged in decisions.md.

## (a) Clone + run upstream unmodified, confirm no-device state on macOS

- [x] Cloned upstream (`MoonLighTingPY/odrive3.6_web_gui`) into `smart-gym-control/` via
      `git init` + `git remote add upstream` + `git fetch` + `git checkout -b main
      upstream/main`. IMPORTANT: upstream `main` HEAD (commit `d905206`, version tag
      `Titanium_2.0.0`, 2026-06-29) is far ahead of what the build spec's "repo facts"
      section describes (which matches roughly the `lithium_1.4.9` tag, 2025-07-26).
      The spec explicitly says to explore actual layout rather than trust its file list,
      so `main` (the actual current upstream default branch) was used as the fork base,
      not an older tag. Upstream remote kept for future cherry-picks.
- [x] Backend: created a throwaway venv at `.venv-upstream-test/` (pyenv 3.9.18 base,
      `~/.pyenv/versions/3.9.18/bin/python3 -m venv`), `pip install -r
      backend/requirements.txt` succeeded clean (Flask 2.3.3, Flask-CORS 4.0.0,
      flask-sock 0.7.0, odrive 0.6.10.post0 — libusb already present via brew from
      Phase 1B). `python backend/start_backend.py` serves on 127.0.0.1:5000, no crash.
      This venv is scratch/throwaway (not the one the final repo will use — real backend
      env gets (re)created in step (b)/(c) once trimmed requirements are set).
- [x] Frontend: `npm install` in `frontend/` succeeded (0 vulnerabilities), `npm run
      dev:frontend` (vite) serves on localhost:3000.
- [x] Confirmed GUI loads with no ODrive attached: sidebar shows "ODrive Devices /
      Scanning / No ODrive devices found. Make sure your device is connected." — a
      sensible, non-crashing empty state. Verified via a headless Chrome + puppeteer-core
      script (scratchpad, not committed) that captured browser console/pageerror/failed-
      request events: 3 benign messages total (vite HMR connect x2, React DevTools info
      notice), **zero error-level console messages**. Backend log for the same session
      showed only clean `200` responses on `/api/backend/version` and repeated
      `/api/devices` polling — no exceptions, no crash loop. Both test servers stopped
      cleanly afterward.
- [x] Base point for the fork: upstream `main` @ commit `d905206` ("Improve motor
      controls card UI"), version tag `Titanium_2.0.0`.

## (b) Restructure + trim (spec §3, §4)

- [x] Created target top-level layout additions: `core/README.md` (placeholder +
      split-rule doc), `config/` dir (empty, filled in step c). `backend/`,
      `frontend/`, `docs/` already existed from the clone/step-a work.
- [x] Stripped multi-axis UI. Deleted `frontend/src/components/AxisSelector.jsx`
      (the 0/1 toggle) and its two call sites (`MotorControlsCard.jsx`,
      `DeviceList.jsx`). Removed the "Apply to both axes" checkbox + `bothAxes`
      state in `ApplyConfigStep.jsx`, the matching `targetAxis==='both'` branches
      in `modals/ConfirmationModal.jsx`, and the `buildCommandStrings({bothAxes})`
      axis-duplication logic in `hooks/useConfigWizard.js`. Hid axis1 from the
      Inspector property tree by changing `apiReference.js`'s `buildPropertyTree`
      default from `maxAxes=2` to `maxAxes=1`. Removed the now-orphaned
      `setSelectedAxis` reducer from `store/slices/uiSlice.js` (no UI dispatches it
      anymore; `selectedAxis` stays as a permanent `0` so the many hooks that
      thread an axis value through — `useMotorControl`, `useConfigWizard`,
      `useCalibration`, etc. — don't need a separate single-axis code path).
      Left `useMotorControl.js`'s `saveAndReboot` writing `axis1.requested_state
      = IDLE` alongside axis0's (a real ODrive constraint — all axes must be idle
      before `save_configuration`; harmless/no-op on an unconfigured ghost axis,
      and removing it wasn't worth the risk for zero UI benefit).
- [x] Stripped multi-device UI. Backend already only ever returns 0 or 1 device
      (confirmed: `device_manager.discover_and_index()` clears its index and
      inserts at most the single handle from `_find_any()`/`odrive.find_any()` —
      there was no real multi-device backend logic to begin with). Simplified
      `DeviceList.jsx` from an `availableDevices.map(...)` card grid to directly
      rendering the single device (or a "no device found" alert); heading changed
      from "ODrive Devices" to "ODrive Device".
- [x] Verified after every removal round: `npx eslint .` clean (zero warnings),
      `npx vitest run` 40/40 passing (2 skipped, both live-hardware-only
      integration tests, expected), and a full headless-Chrome pass clicking
      through all 5 tabs (Configuration, Presets, Dashboard, Inspector, Command
      Console) with no device connected — zero console errors on every tab.
- [x] Stripped Windows/standalone packaging. Deleted: `build.bat`, `build.sh`,
      `install.bat`, `install.sh`, `backend/odrive_gui.spec`,
      `backend/run_standalone.py`, `backend/requirements-build.txt`,
      `backend/servo.ico`, `backend/app/lifecycle.py`, `backend/app/paths.py`,
      `.github/workflows/build.yml` (3-OS standalone-exe CI), and
      `.github/copilot-instructions.md` (upstream's own outdated AI-agent doc).
      Removed the code wired to them: `/api/heartbeat` + `/api/shutdown` routes and
      the static-frontend-serving block in `backend/app/app.py`;
      `QuitAppButton.jsx`, `UpdateChecker.jsx`, and the `isStandalone`/`heartbeat`/
      `shutdownApp`/`HeartbeatManager` code in `frontend/src/api/backend.js` +
      `frontend/src/App.jsx`. Full detail in `docs/decisions.md`. Backend re-verified
      running clean after each removal round.
- [x] Fixed real v0.5.1 compatibility issue: `backend/requirements.txt` was pinned to
      `odrive==0.6.10.post0` (upstream's current default target); changed to
      `odrive==0.5.1.post0` to match our board's actual firmware, per spec §0 and the
      1B script's own header. Verified: installs clean, backend still starts and
      serves `/api/devices`.
- [x] Found + fixed an unrelated-to-0.5.1, but very real, macOS Apple Silicon bug
      surfaced by that pin change: every `/api/devices` poll was throwing an uncaught
      `usb.core.NoBackendError` traceback from a background thread (stale x86_64
      libusb at `/usr/local/lib` shadowing the correct arm64 build at
      `/opt/homebrew/lib`). Fixed in `backend/app/device_manager.py` via
      `_ensure_macos_libusb_path()` (prepends `/opt/homebrew/lib` to
      `DYLD_LIBRARY_PATH` in-process before the lazy `import odrive`). Verified with
      3 consecutive clean polls, zero tracebacks. Full writeup in `docs/decisions.md`.
- [x] Decided fate of `odrive_api_references/` (old planning-doc name was
      `odrive_docs_local/`; actual dir is `odrive_api_references/`). Confirmed zero
      runtime dependency (only consumed by the now-also-removed
      `scripts/generate_api_reference.py` / `check_api_reference.py`, manual dev
      tools for regenerating the JSON reference against a new firmware release —
      irrelevant since we're permanently locked to v0.5.1). Removed both
      directories; left the load-bearing runtime files
      `frontend/src/utils/odriveApiReference05x.json`/`06x.json` untouched.
- [x] Checked for v0.5.6/0.6.x-only property handling that would error against a
      v0.5.1 board. Found and fixed one real gap: `configSchema.js`'s CAN Bus wizard
      fields used `axis{n}.config.can.node_id` /
      `axis{n}.config.can.heartbeat_rate_ms` — 0.6.x-only paths (0.5.x's
      `axis{n}.config.can` is a non-scalar struct with no such leaves in the
      reference JSON). Fixed the node-ID field to the real flat 0.5.x path
      (`axis{n}.config.can_node_id`, taken straight from `odrive_config_1B.py`'s own
      working "Ghost Axis 1 fix" — the wizard can now actually silence axis1 via
      `can_node_id=63`). Dropped the heartbeat-rate field (no confirmed 0.5.x
      equivalent, not needed by this project). Verified: eslint clean, 40/40 vitest
      still passing. Full detail in `docs/decisions.md`. No other 0.6.x-only
      handling found (backend, mock, and frontend registry/property-tree code are
      all already correctly fw-line-aware).
- [x] Verified ODrive access is already a single choke point per spec §6: the *only*
      call to `odrive.find_any` in the whole backend is inside
      `device_manager._find_any()` (this upstream version already centralises device
      access there — no scattered raw `odrive` references in route handlers). Final
      grep re-confirmation happens in step (d) per spec.

## (c) Rebrand + wizard defaults (spec §4 rebranding scope, §5 constants)

- [x] App title/header rebranded to "Smart Gym Control" everywhere (`frontend/
      index.html` title, `App.jsx` sidebar heading, `package.json` name/version).
      Left "ODrive" strings that describe the connected hardware itself (not
      upstream branding) — see docs/decisions.md.
- [x] Stripped upstream release/version badges; wrote a new project README from
      scratch (spec §0 context paragraph, real repo layout, macOS/pyenv dev-mode
      setup + run instructions, architecture notes). No Windows/standalone
      instructions, no Contributing/star-solicitation boilerplate.
- [x] No UI restyling — confirmed no color/theme files touched this session.
- [x] Created `config/board_constants.py` — single source of truth: firmware
      (expected v0.5.1, warns not crashes on mismatch), motor (pole_pairs=15,
      MOTOR_TYPE_HIGH_CURRENT=0, current limits/calibration values from the 1B
      script), encoder (AS5047P, ENCODER_MODE_SPI_ABS_AMS=257,
      abs_spi_cs_gpio_pin=7, cpr=16384), controller (position control, trap_traj
      gains), axis0-only + axis1 CAN node id=63 (recorded per plan, not
      wizard-reachable — that's a Phase 2B action), bus limits. `# TODO(2A)` on
      the torque-mode-vel-limit constant per spec §8. Exposed via a new
      `GET /api/board-constants` backend route (`backend/app/app.py`) — frontend
      fetches values from there, never duplicates them (see decisions.md for the
      `sys.path` wiring needed to import `config/` from `backend/`).
- [x] Moved `odrive_config_1B.py` → `config/odrive_config.py` verbatim (byte-diff
      confirmed identical), then removed the original from `Phase 1/` per the
      explicit "move" instruction.
- [x] Pre-loaded config wizard defaults from board_constants (`useConfigWizard.js`
      now merges `{...deviceSnapshot, ...boardDefaults}` on pull — project
      defaults win over the raw snapshot for our curated field set). Found and
      fixed a real bug during live verification (initial merge order let the
      device/mock's factory-zero readback silently overwrite our defaults — see
      decisions.md). Also added a missing `abs_spi_cs_gpio_pin` schema field
      (was entirely absent from the wizard) and fixed the mock's line-5 seed data
      to include `can_node_id` (missing from the auto-generated 0.5.x reference,
      needed for mock-mode fidelity). **Verified end-to-end** via headless
      Chrome against `ODRIVE_MOCK=1 ODRIVE_MOCK_FW=5`: connected to the mock
      device, opened Configuration → Apply with "only changed" off, and
      confirmed all ~20 project fields show the exact 1B values (pole_pairs=15,
      abs_spi_cs_gpio_pin=7, encoder mode=257, cpr=16384, control_mode=3,
      vel_limit=2, bus limits 25/8/15/-3/0/2, etc.) with zero console errors.
- [x] Shipped one factory preset generated from the 1B script
      (`factoryPresets.js`, "Smart Gym Cable — Hoverboard + AS5047P") — presets
      import/export mechanism itself untouched (already kept from upstream).
- [x] Backend warns, doesn't crash, on firmware mismatch — verified live: mock
      device (reports 0.5.6) triggers a logged warning + a `firmware_warning`
      field in the `/api/devices` JSON response; connection still succeeds
      (200, not refused).

## (d) Re-verify + Definition of Done self-check (spec §7)

- [x] Re-verified "no device connected" state after all Session 1 changes: fresh
      `pip install -r backend/requirements.txt` in the real project venv (not the
      throwaway one from step a), backend + frontend started via the actual combined
      `npm run dev` script (not separately, as in earlier spot-checks) — confirmed
      via headless Chrome: "Smart Gym Control" branding, "No ODrive device found"
      sensible empty state, zero console errors. Backend log over an extended
      multi-poll window showed only clean `200`s on `/api/devices` and
      `/api/board-constants` — no tracebacks, no crash loop, process stayed alive
      throughout. Both servers stopped cleanly afterward.
- [x] **DoD 1** — `npm run dev` (the actual combined script, `concurrently` running
      both `dev:backend` and `dev:frontend`) works with the pyenv 3.9.18 venv active;
      GUI loads at `localhost:3000` with "Smart Gym Control" branding. Confirmed above.
- [x] **DoD 2** — no-ODrive state is clean (see re-verification above): sensible
      empty state, no crash loop, zero unhandled console errors, confirmed across
      all 5 tabs (Configuration, Presets, Dashboard, Inspector, Command Console).
- [x] **DoD 3** — config wizard opens pre-loaded with the 1B values; generated
      command preview matches the 1B script's settings. Verified end-to-end in step
      (c) against the mock device (`ODRIVE_MOCK=1 ODRIVE_MOCK_FW=5`): all ~20
      project-specific fields (pole_pairs, abs_spi_cs_gpio_pin, encoder mode, cpr,
      control_mode, vel_limit, gains, bus limits, axis0 CAN node ID) show the exact
      1B-script values in the Apply step's command preview.
- [x] **DoD 4** — multi-axis and multi-device UI confirmed gone: `AxisSelector`
      deleted, "Apply to both axes" checkbox gone, Inspector hides axis1, device
      list shows a single device-or-not-found view instead of a card grid. No dead
      buttons found in a final repo-wide sweep for references to anything removed
      this session (QuitAppButton, UpdateChecker, lifecycle/standalone routes, etc.)
      — all clean except the intentional upstream-attribution link in README.md.
- [x] **DoD 5** — (deferred to Phase 2A per spec, listed for completeness) Inspector,
      charts, console, and calibration flows against the real board — acknowledged,
      nothing to do now; these are exactly the features spec §4 said to *keep
      as-is*, and Session 1's job was only to confirm they aren't broken by the trim
      (done via the mock-device pass and the disconnected-state tab sweep above).
- [x] **DoD 6** — `docs/decisions.md` lists every stripped feature and every
      incompatibility/bug found during the trim, each with its reasoning: Windows/
      standalone packaging, multi-axis UI, multi-device UI, the CAN-schema 0.5.x
      path bug, the odrive pip-package version pin, the Apple Silicon libusb bug,
      the odrive_api_references/scripts removal, the missing abs_spi_cs_gpio_pin
      field, the mock's missing can_node_id seed, and the wizard-defaults merge-
      order bug.
- [x] **DoD 7** — `core/README.md` exists (empty placeholder package) with the
      GUI/core split rule explicitly written down ("GUI calls into core/, never the
      reverse").
- [x] **§6 choke point** — grepped the whole `backend/` tree for `find_any` and
      `import odrive`: exactly one call site, `device_manager.py:59` inside the
      module's own `_find_any()` (the five other `find_any()` hits are in
      `config/odrive_config.py`, the standalone Phase 1B hardware-bringup script —
      not part of the GUI backend, never imported by it, run manually by a human in
      Phase 2A). Also confirmed no route handler in `app.py` holds a raw `odrv`
      reference of its own — every handler calls `device_manager.attach_or_get(serial)`
      fresh each request; the only persistent cache lives inside `device_manager`
      itself. Session 2's mock/real hardware-interface swap has exactly one place
      to plug into.

**Session 1 complete.** Every Definition of Done item in spec §7 is checked and
verified above; every item's verification method (grep, headless-Chrome console
capture, live mock-device pass, or direct code reading) is recorded so a fresh
session can trust this checklist without re-deriving it.

---

# Session 2 progress — core/ + Control modes

Tracks spec §10 ("Definition of Done") from `Phase 1/1C_build_spec_session2.md`.
Checked items are done AND verified. Rationale for design decisions, the sim J/B
values, and the websocket-vs-REST outcome are in `docs/decisions.md` (Session 2
section) — this file tracks completion + verification method only.

## §3 — core/ package layout

- [x] Built exactly the shape in spec §3: `core/hardware/` (`interface.py`,
      `sim_hw.py`, `odrive_hw.py`, plus a shared `_macos_usb.py` leaf util per
      §5.1), `core/control/` (`modes.py`, `session.py`), `core/telemetry/`
      (`csv_logger.py`), `core/tests/`. `core/` imports only
      `config.board_constants` and (lazily, inside `odrive_hw.py` methods
      only) the `odrive` package — verified by grep (`grep -rn "backend"
      core/` — zero matches).

## §4 — Hardware interface contract

- [x] `HardwareInterface` ABC (`core/hardware/interface.py`): `connect()` /
      `disconnect()` / `is_connected`, `get_state() -> TelemetrySample`,
      `set_mode()`, `set_velocity_target()` / `set_torque_target()`,
      `stop()`, `get_errors()`. `TelemetrySample` dataclass with `t`,
      `position`, `velocity`, `current_iq`, `torque_est`. Torque constant is
      `config.board_constants.MOTOR_TORQUE_CONSTANT`, a `# TODO(2A)`
      placeholder (open item #2) — see decisions.md. Units are ODrive 0.5.1
      native throughout (turns, turns/s, Nm, A) — verified by code reading,
      no degrees/counts/cable conversions anywhere in `core/`.
- [x] `test_abc_cannot_be_instantiated` (`core/tests/test_interface_contract.py`)
      confirms the ABC itself can't be constructed; both concrete
      implementations verified to satisfy the full contract.

## §5 — odrive_hw.py and sim_hw.py

- [x] `odrive_hw.py`: own `find_any(timeout=...)` call site, does not import
      `device_manager`. Uses the shared `core/hardware/_macos_usb.py` helper
      (extracted from `device_manager.py`'s Session-1 fix, now used by both
      — see decisions.md). Clamps velocity targets to
      `board_constants.CONTROLLER_VEL_LIMIT` and torque targets to
      `MOTOR_CURRENT_LIM * MOTOR_TORQUE_CONSTANT`, logging a warning on
      clamp — verified by code reading (`set_velocity_target`/
      `set_torque_target`). Never writes config/calibration properties —
      confirmed: only `requested_state`, `controller.config.control_mode`,
      `controller.config.input_mode`, `controller.input_vel`/`input_torque`
      are touched. Two-connection conflict flagged `# TODO(2A)` at
      `connect()`, logged in decisions.md.
- [x] `sim_hw.py`: dynamic motor model (`accel = (torque_cmd - b*velocity) /
      J`, Euler integration on each `get_state()` call using elapsed
      monotonic time). `SIM_INERTIA_J`/`SIM_DAMPING_B` chosen and reasoning
      logged in decisions.md. Velocity mode uses a proportional controller
      reusing the same integrator (`SIM_VELOCITY_KP`). `current_iq` derived
      back from applied torque via `MOTOR_TORQUE_CONSTANT` so `torque_est`
      round-trips — verified by
      `test_torque_est_round_trips_from_current_iq`. No noise/load/cable
      model, per spec. Verified: `test_positive_torque_makes_velocity_rise`,
      `test_stop_zeroes_targets_and_idles`,
      `test_velocity_mode_converges_toward_target` all pass
      (`core/tests/test_sim_hw.py`).
- [x] Upstream's `mock_odrive.py` (property-tree mock) untouched this
      session — confirmed via `git status`/diff, zero changes to that file
      or its consumers (Inspector/wizard/console).
- [x] Hardware source selection: `hardware_source ∈ {"sim", "real"}`,
      default `"sim"`, backend-owned on the single `ControlSession`
      instance, settable via `GET/POST /api/control/hardware-source` and
      surfaced in the Control tab UI (Sim/Real buttons + an unmissable
      colored banner). Refused while running — verified by
      `test_hardware_source_refused_while_running` and live via curl
      (`{"error": "Cannot change hardware source while a session is
      running"}`).

## §6 — Control layer

- [x] `modes.py`: `VelocityMode`/`TorqueMode`, thin, each declares
      `hardware_mode` + `unit` and validates/forwards its target type
      (rejects non-numeric with `TypeError` — verified by
      `test_validate_target_rejects_non_numeric`). `TorqueMode` carries the
      `# TODO(2A)` for `enable_torque_mode_vel_limit` (open item #8) per
      spec §11. Kept as classes (a shared `BaseMode` ABC) so Session 3's
      profile mode can slot in without changing `ControlSession`'s API.
- [x] `session.py`: `ControlSession` — owns the active `HardwareInterface`,
      active mode, a 50 Hz background telemetry thread (`TELEMETRY_HZ`, one
      constant), a 500-sample ring buffer (~10s of history), and the CSV
      logger lifecycle. API implemented exactly per spec:
      `start(mode, target)`, `set_target(value)`, `stop()`, `status()`,
      `set_hardware_source()`. Verified end-to-end via
      `core/tests/test_control_session.py` (14 tests) AND live via curl
      against the real Flask app (start/retarget/stop, double-start
      refusal, Real-with-no-device failure) — see below.
- [x] **Safety behaviours — all implemented and tested**
      (`core/tests/test_control_session.py`):
      - `stop()` reaches hardware even if the telemetry thread is wedged:
        `test_stop_reaches_hardware_even_if_telemetry_thread_wedged` (a fake
        hardware whose `get_state()` blocks forever; `stop()` still calls
        `hardware.stop()` and returns in well under the 2s join-timeout
        bound).
      - Telemetry-loop exception → hardware stop + session errored, never a
        silent dead loop: `test_telemetry_loop_exception_auto_stops_and_marks_errored`.
      - `get_errors()` non-empty during a run → automatic stop, surfaced in
        `status()`: `test_hardware_errors_trigger_auto_stop`.
      - Double-start refused: `test_double_start_refused`.
      - `atexit` final-stop: `ControlSession.__init__(register_atexit=True)`
        registers `self._atexit_stop` — verified by code reading (the
        registration + its try/except-wrapped call to `self.stop()`); not
        independently re-tested at the process level beyond that, since
        `atexit` itself is stdlib-guaranteed.

## §7 — Telemetry logger

- [x] `csv_logger.py`: exact columns per spec (`timestamp_iso, t_rel_s,
      mode, target, position_turns, velocity_turns_s, current_iq_a,
      torque_est_nm`), one row per tick, files at `logs/` (repo root,
      already gitignored from Session 1), named
      `telemetry_YYYYMMDD_HHMMSS_<mode>_<sim|real>.csv`, auto-open on
      session start / close on stop, flushes at least 1×/s. Plain stdlib
      `csv`, no pandas. Verified: `core/tests/test_csv_logger.py` (file
      shape/columns/rows) AND live — CSV files inspected during manual curl
      testing showed correct headers, mode/target columns, and plausible
      numeric telemetry (see decisions.md for a sample).

## §8 — Backend + frontend wiring

- [x] `backend/app/control_routes.py`: thin adapter module, zero control
      logic (argument parsing + `ControlSession` calls + JSON only),
      registered on the existing Flask app via `control_routes.register(app,
      sock)`. All five REST routes implemented exactly per spec
      (`GET /api/control/status`, `POST /api/control/start`,
      `POST /api/control/target`, `POST /api/control/stop`,
      `GET/POST /api/control/hardware-source`) plus
      `GET /api/control/telemetry?since=`. Verified live via curl: status
      transitions correctly through idle → running → stopped, retarget
      updates `target` in `status()`, double-start returns a clean 400,
      Real-with-no-device returns a clean 400 with `"No ODrive device
      found"` in ~2s (bounded by `OdriveHardware`'s `find_timeout`).
- [x] `/ws/control-telemetry` websocket built exactly per spec (flask-sock,
      same pattern as the existing per-device telemetry route) — but the
      frontend uses the REST fallback instead. Full root-cause writeup in
      decisions.md: the websocket's *close* path (not its data path) races
      against `simple_websocket`'s own background per-connection thread
      under Werkzeug's dev server, corrupting the frame stream — 100%
      reproducible even bypassing the Vite proxy entirely, so not a proxy
      issue. `useControlTelemetry.js` polls `GET /api/control/status` +
      `GET /api/control/telemetry?since=` every 150ms instead. Verified:
      repeated Control ↔ Inspector ↔ Dashboard tab cycling (5 rounds,
      headless Chrome) — zero console errors.
- [x] Frontend Control tab (`frontend/src/components/tabs/control/ControlTab.jsx`):
      hardware source selector with an unmissable colored banner (yellow
      "SIM" / red "REAL HARDWARE", switchable only while idle), mode select
      (Velocity/Torque) + numeric target input with unit shown, Start
      button (idle only) / "Set target" button (live retarget while
      running) / STOP button (always visible, red, disabled only while not
      running), live numeric readout (position/velocity/torque/current),
      three live mini-charts (position/velocity/torque) reusing the same
      recharts pattern as the Inspector's `LiveCharts.jsx` (dark card,
      colored line, seconds X-axis — the declared Session 1→2 chart-reuse
      touchpoint), error display (both action errors and backend-reported
      hardware errors), and the active CSV log filename. No restyling —
      same Chakra dark theme/odrive color scheme as every other tab.
      Registered in `MainTabs.jsx` alongside the existing five.

## §9 — Verification (all against sim)

- [x] **1. `core/tests/` pytest suite** — 35/35 passing, no Flask, no
      device (`python -m pytest core/tests`). Covers the interface
      contract, sim dynamics sanity, `ControlSession` lifecycle + all five
      safety behaviours, and CSV shape/columns/rows.
- [x] **2. Headless-Chrome pass, Control tab, source=Sim** — velocity run
      started, live values moving (position/velocity/torque/current
      updating), retargeted live (0.5 → 1.0 turns/s, chart and readout
      updated), stopped; same for torque mode (0.2 Nm, then switched
      target while running); CSV filename appeared and changed per run
      (`telemetry_<ts>_velocity_sim.csv`, `telemetry_<ts>_torque_sim.csv`);
      **zero console errors** across the whole flow (verified via a
      puppeteer-core script driving a local headless Chrome — scratchpad,
      not committed, per the Session 1 precedent).
- [x] **3. Regression — all five existing tabs** — clicked through
      Configuration, Presets, Dashboard, Inspector, Command Console (plus
      Control) against `ODRIVE_MOCK=1 ODRIVE_MOCK_FW=5`: **zero console
      errors on every tab**. `npx eslint .` clean (zero warnings/errors).
      `npx vitest run`: 40/40 passing, 2 skipped (live-hardware-only,
      unchanged from Session 1).
- [x] **4. Choke-point audit refreshed** — `grep -rn "find_any"
      --include="*.py" backend core config`: exactly the two documented
      call sites (`backend/app/device_manager.py:37`,
      `core/hardware/odrive_hw.py:67`) plus the five hits inside the
      standalone `config/odrive_config.py` 1B script (never imported by the
      GUI backend or `core/`).
- [x] **5. "Real" source, no device attached** — selecting Real and
      pressing Start fails cleanly: visible `"No ODrive device found"`
      error in the UI, no crash, no hang (bounded ~2s, matching
      `OdriveHardware`'s default `find_timeout`), source switchable back to
      Sim, and Sim verified still fully functional afterward (started a
      session, confirmed CSV log appeared). Verified via a headless-Chrome
      script driving the actual UI buttons, not just curl.

## §10 — Definition of Done

1. [x] `core/` package exists per §3, importable with no side effects
       (`import core.hardware.odrive_hw` etc. succeed without a connected
       device or the `odrive` package being reachable — it's installed in
       this venv, but nothing in `core/` imports it at module scope, only
       lazily inside `odrive_hw.py` methods), tests green (35/35).
2. [x] Control tab works end-to-end against the sim: both modes, live
       retarget, live chart, stop, CSV written — verified live (§9.2).
3. [x] All §6 safety behaviours implemented and covered by tests (§6 above).
4. [x] Mock-vs-real selectable from the GUI; Real fails cleanly with no
       device (§9.5).
5. [x] Torque mode reachable programmatically: the 5-line snippet in
       `core/README.md` verified to actually run (`python3 -c "..."`
       against the sim, no Flask involved) — printed a live
       `TelemetrySample` and stopped cleanly.
6. [x] Existing tabs regression-clean; eslint/vitest green (§9.3).
7. [x] `docs/progress.md` Session 2 section fully checked with verification
       notes (this section); `docs/decisions.md` updated — torque constant,
       macOS usb helper extraction, two-connection flag, sim J/B values,
       the websocket-vs-REST root cause and outcome, `threaded=True`, and
       the `/ws` proxy addition.

## §11 — Known follow-ups flagged in-code (not solved, per spec)

- [x] Two-connection conflict (`core/hardware/odrive_hw.py` §5.1) —
      `# TODO(2A)` at `OdriveHardware.connect()`.
- [x] `enable_torque_mode_vel_limit` vs. profile-layer velocity behaviour
      (open item #8) — `# TODO(2A)` at `TorqueMode` in `core/control/modes.py`.
- [x] Torque constant placeholder (open item #2) — `# TODO(2A)` at
      `MOTOR_TORQUE_CONSTANT` in `config/board_constants.py`.
- [x] Sim `J`/`B` placeholders — noted in `core/hardware/sim_hw.py` module
      docstring and `core/README.md`.

**Session 2 complete.** Every Definition of Done item in spec §10 is checked and
verified above; every item's verification method (pytest, headless-Chrome console
capture + live UI interaction, curl against the real Flask app, or direct code
reading) is recorded so a fresh session can trust this checklist without
re-deriving it. Out-of-scope items from spec §12 (live hardware, resistance
profiles, `core/profiles/`, any profile math, phase/rep detection, spool-radius
conversion, restyling, CAN/Pi, regen) were not touched.

---

# Session 3 progress — resistance profile layer

Tracks `Phase 1/1C_build_spec_session3.md` §4–§9. Checked items are done AND verified
(code actually ran). Pre-session note: found an uncommitted, undocumented change to
`frontend/vite.config.js` (proxy target port 5000 → 5050) plus a stray `.orig` backup
file, neither mentioned anywhere in Session 2's docs — stashed (not discarded,
`git stash` "pre-session3: stray vite.config.js..."), tree confirmed clean before
starting. See decisions.md.

## §4 — New constants (`config/board_constants.py`)

- [x] `SPOOL_RADIUS_M = 0.05` placeholder added (`# TODO(2A)`); force↔torque
      conversion lives in exactly one function,
      `core/profiles/units.py::force_to_torque()` (+ inverse
      `torque_to_force()`) — verified by grep (only that one file references
      `SPOOL_RADIUS_M`) and by `test_force_to_torque_and_back`.
- [x] `ECCENTRIC_OVERLOAD_RATIO_DEFAULT = 1.35` added, consumed by
      `OverloadWrapper`'s default `ratio` and surfaced in its `/api/profiles`
      schema entry — verified live via curl (§7).
- [x] Phase-detector tuning constants (`PHASE_VEL_THRESHOLD_TURNS_S = 0.05`,
      `PHASE_HYSTERESIS_TURNS_S = 0.02`, `REP_EWMA_ALPHA = 0.05`,
      `REP_PROXIMITY_TURNS = 0.1`) added under a "profile layer tuning" comment
      block, all `# TODO(2A)` — verified imported and used correctly by
      `core/tests/test_detectors.py` (§5.1 below).

## §5 — `core/profiles/` package

- [x] Package layout created per §5 (`__init__.py`, `units.py`, `detectors.py`,
      `base.py`, `constant.py`, `bell_curve.py`, `overload.py`, `vbt.py`) —
      verified: `import core.profiles` and every submodule succeed with no
      side effects (no Flask/hardware touched at import time), full package
      exercised by 69/69 passing tests below.
- [x] §5.1 `detectors.py`: `Phase` enum (4-state: CONCENTRIC/TOP_HOLD/ECCENTRIC/
      BOTTOM_HOLD), `CABLE_SIGN = +1` sign convention documented in the module
      docstring, `PhaseDetector` (velocity-sign with hysteresis on hold-exit and
      on direct moving-phase reversal), `RepCounter` (EWMA + phase-gated
      proximity, gated on BOTTOM_HOLD specifically — see decisions.md for why),
      `ProfileState` dataclass. Verified: `core/tests/test_detectors.py`, 5/5
      passing — 3-clean-rep synthetic sinusoid produces the exact
      BOTTOM_HOLD→CONCENTRIC→TOP_HOLD→ECCENTRIC→BOTTOM_HOLD cycle and
      `rep_count == 3`; noise dithered at 0.9×threshold (never clearing
      threshold+hysteresis) produces zero phase flicker; a phase sequence with
      no CONCENTRIC ticks produces zero rep counts; reset() on both classes
      verified. Run: `.venv/bin/python -m pytest core/tests/test_detectors.py -v`.
- [x] §5.2 `base.py`: `ResistanceProfile` ABC — `compute_torque(state)`, `name`,
      `describe()` (name/is_wrapper/primary_parameter/parameters-with-schema, also
      the source for the backend's `/api/profiles` route), `primary_parameter_label`
      property, `set_primary_parameter()` (spec) + `get_primary_parameter()` (added,
      not in spec text — see decisions.md for why), `reset()`. `IS_WRAPPER` class
      attr (default False) added so the registry can flag overload without a
      second hardcoded list. Verified: imports cleanly, exercised indirectly by
      every §5.3 stub's tests below (an ABC can't be instantiated directly, so
      there's no standalone base.py test — covered via subclasses).
- [x] §5.3 four stubs, all carrying `# STUB(2A+)` on their math body:
      `ConstantProfile` (`force_to_torque(base_force_n)` exactly),
      `BellCurveProfile` (raised-cosine `curve_factor` bump over
      `[x_start, x_end]` peaking at `peak_multiplier`, injectable/replaceable
      callable), `OverloadWrapper` (composition over any wrapped profile,
      multiplies only in `target_phase`, defaults ECCENTRIC, constructible with
      `target_phase=Phase.CONCENTRIC`, zero-arg constructible via a default
      `ConstantProfile`, primary parameter passes through), `VBTProfile`
      (accumulates mean |v| during CONCENTRIC, adjusts an internal scalar by
      `adjust_step` exactly once per completed rep — verified not per-tick).
      `PROFILE_REGISTRY` in `core/profiles/__init__.py` (name -> factory, all four).
      Verified: `core/tests/test_profiles.py`, 21/21 passing — constant emits
      `force*radius` exactly; bell-curve equals base force outside range and
      peaks at the midpoint; the injected `curve_factor` callable is actually
      called with position; OverloadWrapper multiplies only in its target phase
      (both ECCENTRIC and CONCENTRIC configs) and never in either hold (4-way
      parametrized); primary-parameter pass-through confirmed; VBT scales down
      after a slow rep, up after a fast rep, holds in-band, and — critically —
      the scalar is provably unchanged across 20 mid-rep ticks and only moves at
      the rep-boundary tick; every registry entry is a real `ResistanceProfile`
      with `is_wrapper` correctly `True` only for `"overload"`; a profile whose
      `compute_torque` raises does raise (session-level auto-stop wiring is
      §3/session.py's job, tested there). Run:
      `.venv/bin/python -m pytest core/tests/test_profiles.py -v`.

## §3 — ProfileMode + wiring into ControlSession's 50 Hz loop

- [x] `core/control/modes.py`: `BaseMode` gained three concrete default-no-op/
      identity extension hooks (`tick`, `csv_log_name`, `status_target`) so
      `ControlSession` stays generic across all three modes with zero isinstance
      checks. `ProfileMode` added: `hardware_mode=TORQUE`, `validate_target`
      accepts a `ResistanceProfile` at start / a float on retarget,
      `apply_target` stores+resets the profile (start) or calls
      `set_primary_parameter` (retarget), `tick()` runs phase detector + rep
      counter + `compute_torque` + `hardware.set_torque_target` every tick
      (same clamp path as Session 2 — no new clamp added, see decisions.md),
      `csv_log_name`/`status_target` overridden for the profile-name filename
      and primary-parameter status/CSV target respectively. Registered as
      `MODES_BY_NAME["profile"]`.
- [x] `core/control/session.py`: `_telemetry_loop` now calls
      `mode_handler.tick(hardware, sample)` between `get_state()` and
      `get_errors()` inside the same try/except that already auto-stops on any
      exception — a profile's `compute_torque` raising is indistinguishable
      from a hardware read failure, same auto-stop path. `start()`/
      `set_target()` route the CSV logger name and `status()`'s `target` field
      through the new mode hooks. `status()` gained `phase`/`rep_count` fields
      (None when not running a profile). Verified:
      `core/tests/test_profile_mode.py`, 8/8 passing — a `ConstantProfile` runs
      end-to-end through `ControlSession` (status shows phase/rep_count/correct
      primary-parameter target); retargeting adjusts the same profile object in
      place (not a new one); CSV filename gains `profile-<name>`; an
      `OverloadWrapper`-wrapped profile runs end-to-end with its primary
      parameter passed through; **a profile whose `compute_torque` raises
      auto-stops the session** (extends all 5 Session-2 safety behaviours to
      ProfileMode, spec §3's explicit requirement); starting with a non-profile,
      non-numeric target raises `TypeError` before touching hardware. Full
      69/69 `core/tests` suite (35 pre-existing + 34 new) still green. Run:
      `.venv/bin/python -m pytest core/tests -v`.

## §6 — CSV logger extension

- [x] `phase`, `rep_count` columns appended after `torque_est_nm`; empty strings
      for non-profile runs (verified explicitly:
      `test_velocity_mode_csv_leaves_phase_and_rep_count_columns_empty`).
      Filenames gain `profile-<name>` (`ControlSession` routes this through
      `ProfileMode.csv_log_name`, verified
      `test_profile_mode_csv_filename_includes_profile_name`). Amendment noted
      in decisions.md. Existing `core/tests/test_csv_logger.py` (Session 2,
      unmodified) still passes unchanged against the new 10-column schema.

## §7 — Backend + frontend wiring

- [x] `GET /api/profiles` — registry-driven list (name, parameter schema with
      label/value/default/min/max per parameter, `is_wrapper` flag, `wraps` +
      `target_phase` for the overload entry). `backend/app/control_routes.py`
      (same thin-adapter module as Control tab routes, per spec §7). Verified
      live via curl against the real Flask app (`ODRIVE_MOCK=1
      ODRIVE_MOCK_FW=5 .venv/bin/python backend/start_backend.py`): all 4
      registry entries returned with correct schemas, `overload.is_wrapper ==
      true`, others `false`.
- [x] `POST /api/control/start` extended for `mode: "profile"` (`{profile,
      params, overload: {enabled, ratio, target_phase} | null}`) — composes
      `OverloadWrapper` server-side when `overload.enabled` (spec §7: frontend
      never constructs a wrapper directly). Existing velocity/torque
      `{mode, target}` shape untouched (regression-verified live: both still
      start/report the same as before). Rejects an unknown profile name and
      rejects selecting `"overload"` itself as the base profile (checked via
      `factory.IS_WRAPPER`, not a hardcoded name) — both verified live via curl
      returning clean 400s with readable error messages.
- [x] `status()` gains `phase` + `rep_count` (verified live: `null` when idle,
      populated string/int while a profile runs). Telemetry REST route
      (`/api/control/telemetry`) deliberately NOT extended with per-sample
      phase/rep_count history — see decisions.md for why (status()'s
      point-in-time values are what the spec's own Profiles-tab description
      needs: a live badge, not a phase-over-time series).
- [x] Frontend Profiles tab (`frontend/src/components/tabs/profiles/ProfilesTab.jsx`,
      registered in `MainTabs.jsx` between Control and Inspector): registry-driven
      profile picker (`GET /api/profiles`, `overload` excluded from the base-profile
      dropdown since it's a modifier, not a fifth profile), schema-driven parameter
      inputs (labels/min/max straight from `describe()`, primary parameter marked
      "live"), eccentric-overload toggle + ratio + target-phase select, same
      unmissable Sim/Real banner + always-visible STOP as the Control tab, live
      phase badge (color-coded per phase) + rep count, persistent stub-math notice,
      warns and disables Start if the *other* mode is already running on the shared
      `ControlSession`. Reuses `useControlTelemetry` (same session/polling as
      Control, since profiles are a third mode on the one backend session, not a
      separate one) and the extracted `MiniChart` component (pulled out of
      `ControlTab.jsx` into `control/MiniChart.jsx` so both tabs share the exact
      same recharts config — spec §7's explicit "extract shared pieces" ask).
      `frontend/src/api/profiles.js` (new) + `startProfileSession()` added to
      `frontend/src/api/control.js`.
      Verified: `npx eslint .` clean (zero warnings) across the whole frontend;
      `npx vitest run` 40/40 passing, 2 skipped (unchanged baseline); a headless-
      Chrome pass (puppeteer-core, scratchpad script, not committed, same
      precedent as Sessions 1-2) clicked through all 7 tabs (6 original + Profiles)
      against `ODRIVE_MOCK=1 ODRIVE_MOCK_FW=5` — **zero console errors** (some
      benign recharts `ResponsiveContainer` "width(0)/height(0)" `warn`-level
      messages appeared during tab transitions, same category of benign warning
      as Session 1's vite/DevTools notices — no `error`-level messages at all).
      Then, still headless: selected `constant`, enabled eccentric overload
      (ratio 1.35, target phase eccentric), clicked Start — CSV filename
      `telemetry_..._profile-overload_sim.csv` appeared, phase badge showed
      CONCENTRIC (sim moves one direction under a positive constant torque, per
      spec §8.3's own note). Live-retargeted the primary parameter to `-30`
      (flipping the force sign) via "Set target" — phase badge visibly changed to
      ECCENTRIC within ~2.5s, confirming the detector runs live end-to-end through
      the browser, not just in tests. Clicked STOP — CSV filename cleared, zero
      console errors throughout the whole flow. This is exactly the "drive phase
      changes by live-retargeting the base force sign" approach spec §8.3
      pre-authorized, noted here as required.

## §8 — Verification (all against sim)

- [x] 1. Detector unit tests: 3-rep synthetic sequence → correct phase cycle +
      `rep_count == 3`; noise-at-threshold → zero flicker; no-CONCENTRIC → no reps.
      `core/tests/test_detectors.py`, 5/5 passing (§5.1 above).
- [x] 2. Profile unit tests: constant exact `force*radius`; bell-curve peak/edges;
      OverloadWrapper multiplies only in target phase (both configs, never in
      holds); VBT steps down/up only on rep boundaries; `compute_torque` raising →
      raises (session-level auto-stop tested separately, see next item).
      `core/tests/test_profiles.py`, 21/21 passing (§5.3 above).
- [x] 3. End-to-end against sim: 5-line-snippet `ConstantProfile` run (no Flask,
      `core/README.md`) — printed a live sample + phase + rep_count, stopped
      cleanly. `core/tests/test_profile_mode.py` (8/8) additionally proves via
      `ControlSession`: end-to-end run, retarget-adjusts-in-place, CSV filename/
      columns, `OverloadWrapper` composition, **and the safety-behaviour
      extension** (`compute_torque` raising auto-stops the session, matching
      Session 2's existing exception-auto-stop path exactly). Then, live: `GET
      /api/profiles` + `POST /api/control/start` (profile, profile+overload,
      unknown-profile-400, overload-as-base-400) verified via curl against the
      real Flask app; headless-Chrome Profiles tab pass — constant + overload
      selected, started, phase badge shown (CONCENTRIC), live-retargeted the
      base-force sign to force a direction reversal, phase badge visibly changed
      to ECCENTRIC within ~2.5s, stopped cleanly, **zero console errors**
      throughout (see §7 above for the full transcript/how phase transitions
      were exercised, per spec §8.3's explicit note).
- [x] 4. Regression: Control tab's actual velocity start → CSV-filename-appears →
      live-retarget → STOP flow re-verified live via a second headless-Chrome
      pass after the `MiniChart` extraction (not just "tab loads") — identical
      behaviour to Session 2, zero console errors. All 7 tabs (6 original +
      Profiles) console-clean against `ODRIVE_MOCK=1 ODRIVE_MOCK_FW=5` (only
      benign `warn`-level recharts sizing messages during tab transitions, same
      category as Session 1's benign vite/DevTools notices — zero `error`-level
      messages). `npx eslint .`: clean, zero warnings, full frontend tree.
      `npx vitest run`: 40/40 passing, 2 skipped (unchanged baseline). Full
      `core/tests` pytest suite: **69/69 passing** (35 pre-Session-3 + 34 new:
      5 detectors + 21 profiles + 8 ProfileMode/session integration).
- [x] 5. Choke-point audit: `grep -rn "find_any" --include="*.py" backend core
      config`: still exactly 2 real call sites (`backend/app/device_manager.py`,
      `core/hardware/odrive_hw.py`) plus the 5 hits inside the standalone
      `config/odrive_config.py` 1B script — unchanged from Session 2's audit,
      confirming `core/profiles/` introduced zero new hardware-access paths.

## §9 — Definition of Done

- [x] 1. `core/profiles/` exists per §5 (`__init__.py`, `units.py`, `detectors.py`,
      `base.py`, `constant.py`, `bell_curve.py`, `overload.py`, `vbt.py`),
      importable with no side effects (verified: none of these modules touch
      hardware or Flask at import time — `units.py`/`base.py`/stubs only import
      `config.board_constants` and each other), pytest green (69/69, see §8.4).
- [x] 2. Phase detector + rep counter pass synthetic-sequence tests incl.
      no-flicker hysteresis (§5.1/§8.1 above).
- [x] 3. All four stubs runnable end-to-end against sim through `ProfileMode`
      (§8.3 above — constant proven both programmatically and via the full
      backend+browser stack; bell_curve/vbt covered at the unit level plus the
      registry-iteration test that constructs and calls `.describe()` on every
      one of the four); `OverloadWrapper` composes over any profile and either
      moving phase (parametrized test matrix: 2 target phases × [2 moving-phase
      checks + 2 hold checks] = verified never-multiplies-holds and
      multiplies-only-in-target-phase for both ECCENTRIC and CONCENTRIC
      configurations).
- [x] 4. Profiles tab works: registry-driven picker, schema-driven params,
      overload toggle, live phase badge + rep count, stub-math notice, STOP —
      all verified live via headless Chrome (§7/§8.3 above).
- [x] 5. `core/README.md` gains a second snippet: ConstantProfile session against
      sim, no Flask. Verified: ran the exact snippet text (`.venv/bin/python3 -c
      "..."`) — printed a live `TelemetrySample`, `phase='concentric'`,
      `rep_count=0`, stopped cleanly. Also noted (decisions.md) that the
      *existing* Session 2 snippet, run as literally written with no sleep,
      reliably prints `latest_sample: None` (a race against the 50 Hz thread's
      first tick) — added a short `time.sleep(0.1)` to the new snippet so it's
      honestly deterministic rather than repeating that same unstated race.
- [x] 6. Safety behaviours verified to cover ProfileMode: all 5 Session-2
      behaviours hold structurally unchanged (ProfileMode is just another
      `BaseMode`), and the profile-specific case — `compute_torque` raising —
      is explicitly tested
      (`test_profile_compute_torque_raising_auto_stops_session`) to auto-stop
      the session exactly like a hardware read failure does.
- [x] 7. CSV extension in place (`phase`, `rep_count` columns after
      `torque_est_nm`); Session-2 modes' logs unaffected apart from the two new
      (empty) columns — verified explicitly
      (`test_velocity_mode_csv_leaves_phase_and_rep_count_columns_empty`) and
      the original `core/tests/test_csv_logger.py` (Session 2, untouched this
      session) still passes unmodified against the new 10-column schema.
- [x] 8. Regression + audits per §8.4–8.5 (above); `docs/progress.md` (this
      file) + `docs/decisions.md` updated throughout, not just at the end.

**Session 3 complete.** Every Definition of Done item in spec §9 is checked and
verified above; every item's verification method (pytest, direct code-reading,
curl against the real Flask app, or headless-Chrome console capture + live UI
interaction) is recorded so a fresh session can trust this checklist without
re-deriving it. Out-of-scope items from spec §11 (live hardware, real profile math
beyond structural behaviours, m-term/acceleration estimation, filtering beyond the
EWMA, set/workout-level logic, user accounts/persistence, restyling, websocket
revisit, CAN/Pi, regen) were not touched. Known follow-ups flagged in-code per
spec §10 (all detector tuning constants + `SPOOL_RADIUS_M` + overload ratio;
`enable_torque_mode_vel_limit` now also noted on `ProfileMode`; the two-connection
conflict, unchanged; VBT per-set/Tonal-Burnout-style set-level control; real
strength-curve data injection for BellCurve) are all in place as `# TODO(2A)` /
`# STUB(2A+)` comments in the relevant files.

---

# Phase 2A hardware bring-up — first live hardware run

`config/odrive_config.py` was run for the first time against the actual, physically
wired-in board (ODrive Mini + hoverboard motor + AS5047P + brake resistor + bench PSU +
isolated USB). Motor was never energized; nothing moved before the crash below.

- [x] **Bug caught on this first real run:** crashed with
      `fibre.protocol.ChannelBrokenException` immediately after the "Erase existing
      configuration" confirmation prompt. Root cause: `erase_configuration()` reboots
      this board mid-RPC, severing the USB connection before the call returns — the
      script's own reconnect line (`odrv0 = odrive.find_any()`) was unreachable because
      the exception fires first. Full root-cause + fix writeup in `docs/decisions.md`
      ("Phase 2A hardware bring-up" section).
- [x] **Fixed** with a reusable `call_and_reconnect()` helper (catches the expected
      `ChannelBrokenException`, reconnects via `odrive.find_any(timeout=...)`, fails
      loudly with `sys.exit(1)` and a clear message if the board doesn't reappear —
      no silent retry). Applied at all four reboot-triggering call sites in the script:
      the one `erase_configuration()` call and all three `save_configuration()` calls
      (bus-limits save, static-config save, post-calibration save) — the latter three
      had the identical unreachable-reconnect bug, not yet hit live only because the
      script crashed on the first (`erase_configuration`) call before reaching them.
      Confirmation-gate structure and every existing safety check (`wait_for_idle`,
      `check_errors`, `check_motor_calibration_sane`) preserved exactly — verified by
      diff, only the call+reconnect lines changed.
- [x] **Audited for the same bug elsewhere:** grepped the whole repo (excluding
      `.venv`) for `erase_configuration`, `save_configuration`, and `.reboot(` — the
      four sites just fixed are the only Python call sites; no `.reboot()` call exists
      anywhere. The frontend's own calls to these two methods (Presets tab, calibration
      hook, config wizard, erase-config modal) go through the Flask backend's
      `device_manager`, a fresh-handle-per-request architecture unaffected by this bug
      — confirmed, not a matching issue, logged in decisions.md.
- [x] **Verified without touching real hardware** (per explicit instruction — board is
      live on the bench, real-hardware runs stay in the user's own session):
      `python -m pytest core/tests` still 69/69 passing (fix is isolated to
      `config/odrive_config.py`, outside `core/`); `python -m py_compile
      config/odrive_config.py` clean; `call_and_reconnect`'s actual AST node extracted
      from the real file and exec'd against a fake `odrive` module (scratch script, not
      committed) to exercise normal reconnect, the board-never-reappears failure path
      (bounded, non-zero exit, no hang), an unrelated exception propagating instead of
      being swallowed, and a non-raising call still reconnecting — all 7 checks passed.

Not yet done: re-running the fixed script against the real board (deferred to the
user's own session).

- [x] **Second bug caught on the same live run**, right after the erase/reconnect fix
      worked correctly: crashed setting `odrv0.config.enable_brake_resistor = True` —
      this attribute doesn't exist on this board's firmware (v0.5.1), confirmed live via
      `dir(odrv0.config)`. On this firmware the brake resistor is enabled implicitly by
      `brake_resistance` being non-zero; there's no separate boolean flag. Fixed:
      removed the erroneous line, updated the comment above `brake_resistance` to say so
      explicitly. Full writeup + the follow-on attribute audit in `docs/decisions.md`
      ("Phase 2A hardware bring-up" section).
- [x] **Audited the rest of the script's `.config.` attributes** against the project's
      bundled `odriveApiReference05x.json` (best available offline proxy — the
      `ODRIVE_MOCK` Flask mock isn't wired to this standalone script). 26/28 checked out
      clean. Two items the reference can't confirm either way and were left unchanged:
      `can_node_id`/`odrv0.can.set_baud_rate` (reference only models the nested 0.6.x-
      style equivalent; Session 1 already reasoned through this exact gap and chose the
      flat path from this script's own working-hardware comment — not newly suspicious,
      but not yet live-verified since the crash happened earlier in Section 1) and the
      three `trap_traj.config.*` lines (reference has no `trap_traj_config` group at
      all, so there's nothing to check them against either way). Noted explicitly that
      this reference file is labeled v0.5.6, not our exact v0.5.1, and had already been
      caught giving one wrong answer (`enable_brake_resistor`) — so it's a screen for
      obviously-wrong names, not a substitute for the live board's own `dir()`.
      Verified: `python -m py_compile config/odrive_config.py` clean,
      `python -m pytest core/tests` still 69/69.

## Encoder offset calibration bounded auto-retry (21 July 2026, follow-up session)

- [x] **Added a bounded auto-retry loop around `AXIS_STATE_ENCODER_OFFSET_CALIBRATION`**
      in `config/odrive_config.py`, per the recommendation carried forward in open item
      #14 (project plan). Up to 5 attempts; success is checked via
      `axis0.encoder.is_ready` and `axis0.encoder.error == ENCODER_ERROR_NONE` rather
      than just "no exception," since the failure mode is `ENCODER_ERROR_NO_RESPONSE`
      without the state transition itself raising. `odrv0.clear_errors()` between
      attempts (the confirmed top-level RPC per `odriveApiReference05x.json` — clears
      all device + submodule errors) so a failed attempt doesn't block the next retry.
      On success: sets `axis0.encoder.config.pre_calibrated = True` and saves
      immediately (matches the manual workaround already in use, now automated). If all
      5 attempts fail, exits without saving and points at the next diagnostic step
      (physical AS5047P chip inspection) rather than retrying indefinitely.
- [x] **Verified without touching real hardware**: `python -m py_compile
      config/odrive_config.py` clean. `python -m pytest core/tests` not re-run this
      pass — venv currently has no `pytest` installed (not present in `requirements-dev.txt`
      or wasn't installed into this venv); unrelated to this change, this script isn't
      imported by `core/` either way (same reasoning as the prior verification entry
      above).

Not yet done: running the updated script against the real board — deferred to the
user's own live session, since the confirm() gates exist specifically for a human to
verify physical safety conditions (isolator connected, area clear, wiring intact)
immediately before each energizing step.

## Encoder offset calibration tier-2 diagnostic attempt (open item #14, second follow-up, 21 July 2026)

- [x] **Added a second retry tier to `config/odrive_config.py`'s encoder offset
      calibration loop**, gated on the tier-1 5-attempt loop (previous section, still
      unchanged in logic) exhausting all attempts. New context motivating this: motor
      calibration always succeeds cleanly, and the SPI link is confirmed alive/correct
      at idle (`shadow_count`/`pos_estimate` track correctly while hand-spinning with
      phases unenergized) — the `ENCODER_ERROR_NO_RESPONSE` fault is specific to the
      one step where phases are actively switching while the encoder is read
      continuously, pointing at EMI from motor drive current coupling into the SPI
      lines rather than a dead encoder/CS pin/wiring fault. Tier 2 temporarily lowers
      `axis0.motor.config.calibration_current` (5.0 → 3.0 A, less phase current → less
      EMI) and `axis0.encoder.config.bandwidth` (3000 → 1000, less susceptible to
      noise-induced glitches in the SPI-derived estimate), then runs another 5
      attempts with the identical `is_ready`/`error` check and per-attempt
      individual-field error clearing as tier 1 (shared via one extracted
      `run_encoder_calibration_attempts()` helper, not duplicated). On tier-2 success,
      the reduced values are kept (not reverted) as the new working baseline and
      persist through the existing `save_configuration()` call; the script prints
      exactly which tier succeeded and at which settings. On tier-2 failure (all 5
      attempts at both tiers exhausted), `calibration_current`/`encoder.config.bandwidth`
      are explicitly restored to 5.0/3000 before exiting, so a failed low-current
      experiment doesn't silently become the new default for the next diagnostic step
      (physical AS5047P inspection). Full writeup in `docs/decisions.md`.
- [x] **Added matching (non-value-changing) comments** in `config/board_constants.py`
      near `MOTOR_CALIBRATION_CURRENT` and `ENCODER_BANDWIDTH`, pointing at this
      tier-2 diagnostic path, so a future reader isn't confused if a live board dump
      ever shows 3.0/1000 instead of the project defaults 5.0/3000.
- [x] **Verified without touching real hardware**: `python -m py_compile
      config/odrive_config.py config/board_constants.py` clean.

Not yet done: running the updated script against the real board to see whether tier 1
or tier 2 actually succeeds (or neither) — deferred to the user's own live session, to
be reported back and logged here + in `docs/decisions.md` once known.

## Encoder offset calibration tier-3 diagnostic added — motor-recalibration hypothesis (open item #14, third follow-up, 21 July 2026)

- [x] **Ran the live diagnostic session** referenced by the previous entry: ~15 manual
      attempts at `AXIS_STATE_ENCODER_OFFSET_CALIBRATION`, exactly one success. That one
      success immediately followed a fresh `AXIS_STATE_MOTOR_CALIBRATION` in the same
      session with no reboot in between; every other attempt (encoder calibration alone,
      motor not freshly re-run) failed. New hypothesis for open item #14 — **explicitly
      n=1, not yet confirmed**, easily confounded with other time-varying factors.
- [x] **Added tier 3 to `config/odrive_config.py`'s retry system** (gated behind tiers 1
      and 2 both exhausting all 5 attempts; tier 1/tier 2 code and behavior verified
      unchanged). For up to 5 attempts: clear errors, run a fresh motor calibration,
      check it succeeded by reusing the existing checks (factored `check_errors()` and
      `check_motor_calibration_sane()`'s core logic into new boolean helpers
      `axis_has_errors()`/`motor_calibration_is_sane()` rather than duplicating them —
      original exit-on-failure functions/call sites unchanged in behavior), and on
      success immediately (no reboot, no extra delay) run encoder offset calibration,
      then check `is_ready`/`error` after a 0.2s settle delay (added because the live
      session showed a false-positive "no error" reading immediately after the state
      transition, before the attempt had actually run). On success: sets
      `pre_calibrated = True` for both motor and encoder (tier 3 is the first tier that
      re-runs motor calibration itself) and reports which attempt/tier succeeded. On
      failure of all 5 tier-3 attempts: exits the same way as tier-2 exhaustion,
      restores `calibration_current`/`encoder.config.bandwidth` to 5.0/3000 (defensive —
      tier 2's own failure branch already does this), and the failure message now names
      all 3 tiers plus flags that an oscilloscope/logic analyzer check on the SPI lines
      may be the next step once physical inspection is exhausted, since software-side
      retries are now exhausted too. Full writeup in `docs/decisions.md`.
- [x] **Verified without touching real hardware**: `python -m py_compile
      config/odrive_config.py` clean. Control-flow read-through confirmed the
      tier-2-scoped `orig_calibration_current`/`orig_encoder_bandwidth` names are always
      in scope by the time tier 3's failure branch references them.

Not yet done: running the updated script against the real board to see whether tier 1,
2, or 3 actually succeeds (or all three fail), and whether the motor-recalibration
hypothesis holds beyond its single n=1 data point — deferred to the user's own live
session, to be reported back and logged here + in `docs/decisions.md` once known.

## New diagnostic script: `config/diagnose_encoder_spi.py` (open item #14, fourth follow-up, 21 July 2026)

- [x] **Added a new standalone diagnostic script** to isolate WHERE the
      `ENCODER_ERROR_NO_RESPONSE` fault actually is, using ODrive's own diagnostic
      states/tools, instead of continuing to iterate on the calibration state machine
      directly (as the three tiers in `config/odrive_config.py` do). Two confirm()-gated
      tests: **Step 1** enters `AXIS_STATE_LOCKIN_SPIN` (open-loop drive, entirely
      bypassing the encoder-offset-calibration algorithm) and polls
      `encoder.spi_error_rate`/`pos_estimate`/`shadow_count`/`vel_estimate` at ~10 Hz for
      a few seconds, printing a "SPI healthy under drive" vs. "SPI failure under drive
      confirmed" verdict; **Step 2** runs one `AXIS_STATE_ENCODER_OFFSET_CALIBRATION`
      attempt with `axis0.config.calibration_lockin`'s vel/accel temporarily slowed
      in-memory (restored afterward regardless of outcome, nothing saved), testing a
      timing-budget hypothesis. Ends with a combined summary suggesting the most likely
      next diagnostic direction based on both verdicts together. Full design reasoning
      in `docs/decisions.md`.
- [x] **Read-only with respect to saved config**: no `erase_configuration()`/
      `save_configuration()` calls, `pre_calibrated` never set on anything. Does not
      modify `odrive_config.py` or `board_constants.py`. Extracted the small reusable
      bits (`confirm()`, `wait_for_idle()`, individual-field error clearing) into a new
      shared module, `config/odrive_diag_common.py`, since `odrive_config.py` can't be
      imported (top-level script, runs on import) and wasn't to be touched.
- [x] **Verified without touching real hardware**: `python -m py_compile
      config/diagnose_encoder_spi.py config/odrive_diag_common.py` clean. Ran the actual
      script's `main()` end-to-end against a hand-built fake `odrive` module (same
      fake-module precedent used earlier for `call_and_reconnect()`) — full control flow
      (Step 0 dump, Step 1 poll loop, Step 2 slow/restore cycle, final summary) completed
      with no exceptions.

Not yet done: running this script against the real board — deferred to the user's own
live session, to be reported back and logged here + in `docs/decisions.md` once known
(per the task's own framing, this entry logs the script's existence/purpose only, not an
outcome).

---

## Live bring-up session, 21 July 2026 — open items #14 and #7 resolved

- [x] **Open item #14 — Resolved (21 July 2026).** Root cause: the onboard AS5047P can
      enter a latched fault state matching what the ODrive community forum calls
      "super-sulk" (frozen `shadow_count`/`pos_estimate`, `spi_error_rate` misleadingly
      stays `0.0`). Confirmed it does **not** clear via `clear_axis_errors()`,
      `odrv0.reboot()`, or `save_configuration()`'s implicit reboot — only via a full
      physical DC-bus power cycle. After a live power cycle, encoder offset calibration
      succeeded cleanly on the first attempt, was saved
      (`motor.config.pre_calibrated=True`, `encoder.config.pre_calibrated=True`,
      `save_configuration()`), and confirmed durable across a subsequent `odrv0.reboot()`
      (`motor.is_calibrated=True`, `encoder.is_ready=True`, clean `dump_errors()` on both
      axes). Tiers 1-3 in `config/odrive_config.py`'s retry loop are confirmed to have been
      testing the wrong layer of the problem (none of them address a hardware-latched
      fault) — left in place as harmless, but a prominent comment now points straight at
      the DC-power-cycle fix ahead of them. Full root-cause writeup, forum reference, and
      isolation method: `docs/decisions.md` ("AS5047P 'super-sulk' latched fault — root
      cause found").
- [x] **Open item #7 — Resolved (21 July 2026)**, gains half only. With a working saved
      calibration, closed-loop control was tested and gains were tuned live at the bench
      on a free-spinning wheel (no cable load yet): `pos_gain` 1.0→3.0→**6.0**, `vel_gain`
      0.02→**0.05**, `vel_integrator_gain` 0.0→0.05→**0.1**, `motor.config.current_lim`
      10.0→**15.0** — each step confirmed smooth (no oscillation/overshoot) before
      increasing further. Saved live via `save_configuration()`, confirmed to persist.
      `config/board_constants.py` updated to match. **Not yet resolved**: item #7 as
      originally scoped in the project plan also bundled the 25V bench-only
      `dc_bus_overvoltage_trip_level`, which still must be raised before the battery phase
      (~42V) — untouched this session, tracked separately via the comment on
      `DC_BUS_OVERVOLTAGE_TRIP_LEVEL` in `config/board_constants.py`. Gains may also need
      re-tuning once real cable load (not a free-spinning wheel) is introduced in later 2A
      work. Full writeup: `docs/decisions.md` ("Live gain tuning at the bench").

---

## First real-hardware Freddy (web GUI) session, 22 July 2026

- [x] Backend/frontend route audit against real hardware: clean, no mismatches found.
- [x] Two real bugs found and fixed live in `backend/app/device_manager.py`: silent
      exception-swallowing in `_find_any()` (a real USB error looked identical to "no
      device"), and a self-contention bug (`odrive.find_any()` resets the USB bus every
      call; nothing prevented two concurrent `/api/devices` polls from colliding). Also
      fixed `serial_number` being reported as decimal instead of the hex format every
      other ODrive tool uses. Full writeup: `docs/decisions.md`.
- [x] **Open item resolved: the `# TODO(2A)` two-connection conflict** flagged since
      Session 2 in `core/hardware/odrive_hw.py`. `OdriveHardware` now takes optional
      injected `find_any_fn`/`lock_provider` hooks (default no-op, so `core/tests`/
      `core/README.md` usage is unchanged); `backend/app/control_routes.py` injects
      `device_manager.get_shared_handle`/`get_shared_io_lock` so a Control-tab run
      reuses the sidebar's already-open connection instead of opening a rival one that
      resets the bus out from under it. `stop()` deliberately stays unlocked to preserve
      the Session 2 wedge-safety guarantee. `core/tests`: 69/69 still passing. Backend
      log from the user's own subsequent session shows 3 successful
      `POST /api/control/start` calls interleaved with normal sidebar `/api/devices`
      polling and zero bus-reset/USB-error log lines in that window (a sharp contrast to
      the collision errors logged pre-fix) — good live evidence the fix works, though the
      specific "sidebar stays accurate through an auto-stop" scenario that originally
      surfaced the bug wasn't separately, deliberately re-verified. Full design writeup:
      `docs/decisions.md`.
- [x] Added `Start Freddy.command` (repo root, replaces the untracked mock-mode
      `Start UI.command`): one double-click kills any stale backend/frontend, starts both
      fresh in real-hardware mode, waits for both to respond, opens Safari. Verified live.
- [x] **Found and fixed a second, more serious bug the same session**: after the board was
      physically unplugged mid-connection, `device_manager._find_any()` stopped respecting
      its own timeout and hung indefinitely — confirmed live (`/api/devices` didn't
      respond even after 20s, while non-USB routes stayed instant) and root-caused (a
      fresh process's `find_any()` returned cleanly in 2.01s against the same unplugged
      board — the wedge was specific to accumulated state in the long-running process).
      Because discovery never completed, the stale cached "connected" handle from before
      the unplug never got cleared — **this is what made the UI show "connected" with the
      USB not even plugged in.** Fixed with a hard wall-clock ceiling
      (`_FIND_ANY_HARD_TIMEOUT_S = 5.0`) around the actual `find_any()` call, run in a
      daemon thread and joined with a timeout, so a wedge now degrades to a clean "no
      device found" (correctly clearing the stale cache) instead of hanging the whole
      backend. `core/tests`: 69/69 still passing. Live: `/api/devices` now responds in
      ~1-2s post-restart instead of hanging. Full writeup: `docs/decisions.md`.

Not yet done: deliberately re-triggering the auto-stop-with-sidebar-watching scenario that
first surfaced the two-connection bug, to directly confirm (not just infer from logs) that
the sidebar stays accurate through it —
deferred to the user's next session with the board physically connected.

## Same session, immediate follow-up: request pileup + port-5000/AirPlay conflict

- [x] The `_discovery_lock` hang-fix above could itself pile up the whole backend under
      normal load (real scans with the board present + other USB peripherals can
      legitimately take a few seconds; strict serialization + a 3s poll interval meant
      requests could arrive faster than they drained). This is what actually caused the
      "shows connected with USB unplugged", frozen Dashboard (`0.0V`/`UNDEFINED` despite
      "Error States: OK"), "Enable Motor" no-op, and Control tab "load failed" symptoms —
      one root cause, not four. Fixed: `discover_and_index()` now takes `_discovery_lock`
      non-blocking and falls back to the current cache if a scan's already in flight,
      instead of queueing.
- [x] Also found (by accident, while diagnosing): the backend process had actually died,
      and because macOS's AirPlay Receiver squats on the wildcard `*:5000`, every request
      silently fell through to it (real HTTP 403s, `Server: AirTunes`) instead of a clean
      connection error — nearly invisible as a cause. An old, never-applied git stash in
      this repo shows a previous session hit this exact issue and half-fixed it
      (`vite.config.js` only) without finishing or documenting it. Properly fixed this
      time: backend moved to port 5050 everywhere (`start_backend.py`, `vite.config.js`,
      `Start Freddy.command`, the live-integration test default, README/user manual).
      `Start Freddy.command` also switched from `&`+`disown` (failed — no job control in
      that shell context) to `nohup`, so the backend can't be taken down by its own
      launcher shell exiting.
- [x] `core/tests`: 69/69 still passing throughout. Live: 8-poll overlap stress test with
      zero pileup, confirmed the backend survives independently of the launching shell,
      and a direct property read through the fixed stack came back with real live values
      (`vbus_voltage: 14.71V`, `axis0.current_state: 1`, `motor.is_calibrated: true`,
      `encoder.is_ready: true`) — confirming the Dashboard symptom was entirely downstream
      of the pileup/crash, not a separate bug in property reads. Full writeup:
      `docs/decisions.md`.
- [x] **Found the real, deeper cause of a recurring "connected but frozen at zero" Dashboard**
      even on a genuinely fresh page load: `discover_and_index()` reset the USB bus on
      *every* poll, unconditionally, even when a device was already connected and
      healthy — eventually killing whatever else (the telemetry websocket, a Control
      session) was using that connection (`fibre.protocol.ChannelBrokenException`, 16
      occurrences in one log). `getattr(obj, name, default)` only swallows
      `AttributeError`, not that exception, so it crashed the request instead of
      degrading gracefully. Fixed: `discover_and_index()` now answers from the cache
      with zero bus access whenever the cache is still alive, only falling through to a
      real (resetting) scan if nothing's cached or the cached entry is actually dead.
      `core/tests`: 69/69 still passing. Live: 10 rapid polls against an already-connected
      device now take ~4ms each (was 1-5s+) with zero channel-broken errors afterward,
      and a property read immediately after confirms the connection survived. Full
      writeup: `docs/decisions.md`.

## GUI cleanup: real-only Control/Profiles + live PID gain sliders, 22 July 2026

User feedback after using the app hands-on with real hardware for a while: never uses
the Control/Profiles tabs' sim option, wants it gone; separately wants to tune the
controller PID gains from the Control tab itself (sliders), instead of going through
the Configuration wizard every time.

- [x] **Removed the Sim/Real hardware-source toggle from the GUI.** Deleted the colored
      banner + Sim/Real button pair from both `ControlTab.jsx` and `ProfilesTab.jsx`
      (identical blocks in both), along with the now-dead `hardwareSource` state,
      `handleHardwareSourceChange`, and the `apiSetHardwareSource`/`setHardwareSource`
      imports in each. Changed `backend/app/control_routes.py`'s `ControlSession`
      construction from `hardware_source="sim"` to `hardware_source="real"`, so a fresh
      backend process now boots straight into real-hardware mode with no user action
      needed — previously it silently defaulted to sim with no GUI way to notice.
      Deliberately did **not** touch `core/hardware/sim_hw.py`, `ControlSession`'s
      `set_hardware_source()`, or the `/api/control/hardware-source` GET/POST route —
      left as working, tested backend/core capability, just no longer surfaced in the
      GUI (still reachable via curl/tests if ever useful).
- [x] **Added a "Controller Gains" card to the Control tab** — three sliders (Position
      Gain, Velocity Gain, Velocity Integrator Gain) reading/writing
      `axis0.controller.config.{pos_gain,vel_gain,vel_integrator_gain}` directly via the
      existing generic `readProperties`/`writeProperties`/`invokeCommand` backend client
      (the same one the config wizard and Inspector use — no new backend route needed).
      Reads the device's current gains once connected; slider drag updates the displayed
      number continuously (`onChange`) but only writes to the device on release
      (`onChangeEnd`), so dragging doesn't flood the connection with writes. A "Save to
      NVM" button calls `save_configuration` to persist tuned gains across reboots —
      disabled while a session is running, since that call reboots the board.
- [x] Verified: `npx eslint .` clean across the whole frontend, `npx vitest run` 40/40
      passing (2 skipped, unaffected). Live: with the user's real backend/frontend dev
      servers already running against a connected board (Flask's debug reloader and
      Vite's HMR picked up the changes automatically — servers were **not** restarted, to
      avoid disturbing the live session), a separate passive headless-Chrome check (new
      tab, no interaction with Start/Stop/sliders) confirmed both tabs render with no
      "SIM"/"REAL HARDWARE" text anywhere, the Controller Gains card appears on Control
      and correctly shows "no device" in that fresh tab's own (unconnected) session
      state, and zero console errors.
- [x] Updated `docs/user_manual.md` and `docs/manual.html` (the styled HTML twin) to
      match: rewrote the intro framing (hardware is now wired and primary, not "Session
      3, no hardware yet"), rewrote §2.4 Control (three modes now, no sim/real step, new
      Controller Gains subsection), trimmed the sim/real line from §2.5 Profiles, noted
      in §3 that CSV filenames' `_real`/`_sim` suffix is now always `_real` (it reflects
      which internal hardware factory was used, not whether the device is physically
      real or the `ODRIVE_MOCK` mock), and replaced §4 "Sim vs Real" with "Running with
      vs without hardware" — clarifying the two independent sim mechanisms in this
      codebase (`ODRIVE_MOCK=1`/`mock_dev`, backend-level, untouched by this change; vs.
      the now-removed per-tab `ControlSession` simulator) so a future reader doesn't
      conflate them. Did not do a full pass on the rest of either manual's other,
      unrelated staleness (e.g. the "seven tabs"/"Session 3" framing predates Position
      mode and the new sidebar Reset/Restart-backend buttons, and §5's
      two-simultaneous-connection rough edge was actually already fixed per the entries
      above) — out of scope for this change, flagged here for a future doc pass.

---

# Exercise tab, Layer A (cable-attached positioning & safety), 23 July 2026

Built per `exercise_tab_build_spec_layerA.md` (source WHAT doc:
`exercise_tab_WHAT_plan.md`). Layer A only — homing, max-extension calibration,
spool-geometry correction, length-based control, manual reset. Explicitly **not**
built: force feedback, concentric/eccentric phase logic, isokinetic mode (all
Layer B, WHAT-planned only). Control and Profiles tabs untouched.

Full architecture-fit analysis, constant-by-constant reasoning, and the
homing-state-machine design were reported at the session's mid-point
checkpoint and are recorded permanently in `docs/decisions.md` ("Exercise tab
Layer A" entry) — this section is the §11 Definition of Done walkthrough.

## §11 Definition of Done

- [x] **`core/cable/` built**: `geometry.py` (spool turns↔length conversion +
      `k` calibration, zero project-specific imports — pure math), `homing.py`
      (`HomingStateMachine`), `limits.py` (target clamp + runtime guard + max-
      extension sanity check), plus `state.py` (`CableState`, a deviation from
      the spec's suggested 4-module layout — see decisions.md) and
      `exercise_mode.py` (the `ControlSession` integration). All hardware-free,
      Flask-free, `ControlSession`-free except `exercise_mode.py` itself.
      Homing's six required synthetic-sequence cases (§8: clean detection,
      grace-period transient, sub-debounce transient, travel-bound fault,
      timeout fault, abort) written and passing *before* anything was built on
      top of the state machine, per the session's explicit requirement — all
      ten homing tests passed on the first run, no design issues surfaced
      there. The synthetic tests **did** catch a real issue elsewhere:
      `core/tests/test_geometry.py`'s round-trip property test found that the
      first-guess `SPOOL_CORRECTION_K_BOUNDS = (±0.01)` let a value *within*
      that bound break the spool model's invertibility within about one turn
      of travel — tightened to `(±0.0005)`, full reasoning in decisions.md.
- [x] **Integration into the running control loop**, following the
      `ProfileMode` precedent (`ExerciseMode(BaseMode)`, runs inside
      `ControlSession`'s existing 50Hz loop, no second thread). Three
      deviations from the precedent, all forced by something the spec
      couldn't see without the codebase in front of it, all logged in
      decisions.md: (1) home/max live in `CableState`, injected via a new
      `ControlSession.mode_factories` hook, not owned by the mode instance —
      `ControlSession.stop()` destroys `_mode_handler`, but spec §3.5 needs a
      still-valid home to survive a Stop; (2) `ExerciseMode` calls
      `hardware.set_mode()` itself when the action changes (velocity/torque/
      position within one session), since `ControlSession` only ever calls it
      once at `start()`; (3) `calibrate_k`/`reset_position` bypass
      `ControlSession` entirely (backend-route-level operations directly
      against `CableState`) since neither needs the motor moving and reset
      specifically must work while nothing is running.
- [x] **Backend routes** (`backend/app/exercise_routes.py`, mirroring
      `control_routes.py`'s structure per spec §2.3 rather than extending its
      `{mode, target}` shape): `/api/exercise/{start,home,abort_homing,
      start_max_calibration,confirm_max,cancel_max_calibration,move,stop,
      reset_position,calibrate_k,status}`. REST polling only, no websocket —
      matches the Control/Profiles precedent (`useControlTelemetry.js` had
      already abandoned the websocket for the flask-sock close-path race the
      spec anticipated). Shares the one `control_session` singleton, so the
      `find_any()` choke point stays a single call site with zero new code.
      No dedicated pytest file — this project has no backend-level test
      infrastructure at all (`control_routes.py` doesn't have one either);
      verified via the Flask test client end-to-end and, separately, in a
      real browser (see below).
- [x] **Exercise tab frontend** (`frontend/src/components/tabs/exercise/
      ExerciseTab.jsx`, registered in `MainTabs.jsx` alongside Control/
      Profiles): session start/stop, Home/Abort Homing with a live homing-
      state badge, max-extension calibration (start/confirm/cancel), length-
      based Move, confirmation-gated + idle-gated Manual Position Reset. Spool
      calibration lives in a collapsed "Advanced" `Collapse` section (spec
      §2.4), not visible by default. `api/exercise.js` +
      `hooks/useExerciseStatus.js` follow the Control/Profiles precedent
      exactly (REST polling); the status hook differs in one respect —
      it keeps polling `/api/exercise/status` even while nothing is running,
      since `cable.is_homed` must stay visible after a Stop.
      **Verified in a real browser**: dev servers started against
      `ODRIVE_MOCK=1` (backend on 127.0.0.1:5050, frontend via Vite on an
      auto-selected port since the user's own dev server was already running
      on 3000 — left untouched), driven headlessly via Chrome DevTools
      Protocol (raw CDP over websocket, not a library — nothing suitable was
      pre-installed and a full Puppeteer/Chromium download wasn't worth it
      for one check). Confirmed: the Exercise tab renders with **zero console
      errors and zero exceptions**; clicking through Start → Home → a live
      "Reeling in…" badge → Abort → Stop round-trips through the whole real
      stack (frontend → Flask → `ControlSession` → `ExerciseMode` →
      `OdriveHardware` → the mock device) with no crashes; the Advanced
      section toggles open/closed correctly. `ODRIVE_MOCK=1` turned out to
      provide a live, connectable mock device (not just "no device found"),
      so this exercised the full happy path, not just error handling.
- [x] **All eight §4 safety behaviours implemented and individually tested**
      (`core/tests/test_exercise_mode.py`, `core/tests/test_homing.py`):
      1. No motion without an explicit user action —
         `test_construction_does_not_move_anything`,
         `test_arm_holds_zero_velocity_no_homing_started`.
      2. Homing cannot latch on a transient — `test_homing.py`'s grace-period
         and sub-debounce-window transient cases (2 tests).
      3. Homing always terminates — `test_homing.py`'s travel-bound and
         timeout-bound fault cases (2 tests).
      4. Current limit always restored — `test_homing_completes_latches_
         home_and_restores_current_limit`,
         `test_homing_fault_restores_current_limit_and_records_reason`,
         `test_abort_homing_restores_current_limit_and_stops_immediately`
         (success/fault/abort, all three exit paths individually).
      5. Length control unavailable without a valid home —
         `test_move_rejected_when_unhomed`,
         `test_max_calibration_requires_homed`, plus `limits.py`'s own
         `test_validate_homed_raises_when_not_homed`.
      6. Both end stops enforced at runtime, not just command time —
         `test_move_clamps_target_beyond_max` (mechanism 1: target clamping)
         and `test_tick_raises_when_position_leaves_range_beyond_tolerance`
         (mechanism 2: runtime guard, reusing `ControlSession`'s existing
         raising-mode-auto-stops-the-session path).
      7. Stop remains available and effective during every state — the
         Exercise tab's Stop and the sidebar's always-present emergency-stop
         both call the same `control_session.stop()` already tested
         extensively in `test_control_session.py`; unchanged by this session.
      8. Manual reset is idle-gated and confirmation-gated — idle-gating
         enforced in `exercise_routes.py` (rejected while an Exercise session
         is running at all); confirmation is a frontend dialog (same pattern
         as the existing erase-config modal), gated the same way `resetOpen`/
         `ConfirmationModal`-style dialogs already work elsewhere in this
         codebase.
- [x] **All §5 constants in `config/board_constants.py`**, no inline literals
      — including two not in the spec's own table but needed to make its own
      requirements concrete (`MAX_EXTENSION_MIN_TRAVEL_TURNS`,
      `POSITION_GUARD_TOLERANCE_TURNS`) and one more
      (`SPOOL_CALIBRATION_MIN_THETA_M_RAD`) for the calibration-input guard.
      Full reasoning per constant in decisions.md.
- [x] **`MOTOR_TORQUE_CONSTANT` updated to `0.516875`**, commented as a
      fallback estimate pending the hand-spin KV measurement (open item #13).
      **Flagged explicitly**: this is not Exercise-tab-local — it raises
      Control/Profiles' `TorqueMode`/`ProfileMode` clamp ceiling from ~0.9 Nm
      to ~7.75 Nm and changes every `torque_est` reading. Spec-mandated
      regardless; no existing test hardcoded the old value, so nothing broke,
      but this is the one deliberate, visible exception to "Control/Profiles
      unchanged."
- [x] **Persistence split per §6** — `k` persists to
      `config/spool_calibration.json` (gitignored), home/max never touch
      disk. `core/tests/test_cable_state.py::
      test_k_persists_across_a_fresh_instance_simulating_backend_restart`
      constructs a second `CableState` against the same sidecar path and
      asserts `k` survives while home/max do not — the closest a hardware-
      free test gets to an actual backend restart. Backend restarts un-homed
      by construction (a fresh `CableState` simply starts with
      `home_turns = None`), not via a separate reset-on-boot step that could
      be forgotten.
- [x] **Cable length added to telemetry and CSV** — caught mid-DoD-review that
      the first pass only added `cable_length_m` to the live status "extra"
      passthrough, not the CSV logger, contradicting spec §7 explicitly.
      Fixed: `CsvLogger` gains one more trailing column (same additive
      pattern as the Session 3 `phase`/`rep_count` amendment), populated once
      homed during Exercise runs, empty string otherwise. Two existing CSV
      tests that asserted against fixed negative column indices were
      hardened to look up columns by name instead, since the new trailing
      column had silently shifted what those indices pointed at (one test
      would have started checking the wrong columns without failing).
- [x] **Full regression green**: `pytest core/tests` 172/172 (170 Layer A +
      2 caught during the CSV fix above), `npx eslint .` clean, `npx vitest
      run` 40/40 passing (2 skipped, unaffected).
- [x] **Control and Profiles tabs verified unchanged in behaviour** — neither
      tab's source files were touched. Their shared dependencies
      (`core/control/session.py`, `core/hardware/odrive_hw.py`) changed in
      ways confirmed backward-compatible: `mode_factories` defaults to the
      unchanged `MODES_BY_NAME`; `status()`'s new `"extra"` field is additive
      (existing `phase`/`rep_count` fields untouched); `OdriveHardware.
      connect()`'s new current-limit reassertion is a no-op in the common
      case (nothing else ever changes it away from `MOTOR_CURRENT_LIM`).
      Confirmed live against `ODRIVE_MOCK=1`: `POST /api/control/start` with
      `mode=velocity` and `GET /api/profiles` both behave identically to
      before. The one intentional, visible exception (`MOTOR_TORQUE_CONSTANT`)
      is called out above and in decisions.md, not silently absorbed into
      this checklist item.
- [x] **Choke-point audit clean** — `grep -rn "find_any("` still finds exactly
      one real call site (`backend/app/device_manager.py`'s
      `odrive.find_any(timeout=1.0)`); `core/hardware/odrive_hw.py`'s own
      fallback is unreachable in the actual backend (always overridden by
      `_real_hardware_factory`'s injection, which Exercise reuses unchanged);
      `config/odrive_config.py`/`diagnose_encoder_spi.py` remain standalone
      scripts outside the Flask app, unaffected.
- [x] `docs/progress.md` (this entry) and `docs/decisions.md` updated,
      including every deviation from the spec and the reasoning for each
      chosen constant.
- [x] `docs/user_manual.md` and `docs/manual.html` updated for the new tab
      (see the entry immediately below this one) — did not rabbit-hole into
      either manual's known pre-existing staleness, per instruction.

## Housekeeping note: pre-existing uncommitted diffs

Several files this session needed to edit (`config/board_constants.py`,
`core/hardware/odrive_hw.py`, `core/hardware/interface.py`, `core/control/
modes.py`, `core/tests/test_control_session.py`) already had uncommitted
changes sitting in them from earlier bench sessions (10A→15A current-limit
bump, live-tuned controller gains — both already narrated earlier in this
log, just never committed). Flagged to the user mid-session rather than
deciding unilaterally how to handle it; chosen: fold together rather than
surgically split hunks per file. Some of this session's commits therefore
contain both Layer A work and carried-forward bench-session content, called
out explicitly in each affected commit message.
