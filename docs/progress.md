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

---

# Exercise tab, Layer B Session B1 (concentric force feedback), 23 July 2026

Built per `exercise_tab_build_spec_layerB.md`. Concentric only — constant
force and isokinetic resistance, plus the safety machinery that makes
either safe to stand in front of. Eccentric (B2) is explicitly out of scope,
gated behind B1 being validated on real hardware with a real person, not
merely behind B1 being merged. Full architecture reasoning, constant-by-
constant justification, the §5.2 power analysis, and three named
first-live-run watch items are in `docs/decisions.md` ("Exercise tab Layer B
Session B1" entry) — this section is the §15 Definition of Done walkthrough.

## §2 preconditions — how this session actually started

Checked before writing any code, per explicit instruction to stop rather
than work around unmet preconditions. All four were unmet:
`SPOOL_RADIUS_M`/`BRAKE_RESISTANCE`/`DC_MAX_NEGATIVE_CURRENT`/
`MAX_REGEN_CURRENT` were still placeholders (§2.3/§2.4), the KV measurement
was outstanding (§2.2, open item #13, still is), and Layer A had never been
run against real hardware with a cable attached (§2.1, still hasn't). Full
precondition-check report given to the user; the user then provided real,
measured values for §2.3/§2.4 and explicitly authorized proceeding with the
build/sim-test path on §2.1/§2.2 (per the spec's own carve-out for §2.2;
§2.1 was the user's explicit call to override the spec's stricter framing,
not a default I assumed).

## §11 DoD walkthrough

- [x] **Governor, let-go detector, and power limiter built as pure,
      synthetically-tested modules** (`core/cable/{governor,letgo,
      power_limiter,ramps}.py`), written and tested before any integration,
      per the session's own hard requirement (matching Layer A's homing.py
      precedent). 40 tests, all passing on the first run except the power-
      limiter's quadratic-solving edge cases, which needed the smaller-root
      derivation worked out carefully up front (see decisions.md's power
      limiter module docstring for the reasoning) rather than being
      caught by a failing test after the fact.
- [x] **Force session state machine integrated per the §8 decision**
      (`core/cable/force_mode.py::ForceMode`), running in the existing
      50Hz `ControlSession` loop — no new thread. Registered as a sixth
      mode (`"force"`) alongside velocity/torque/position/profile/exercise
      on the one shared session, sharing `CableState` with `ExerciseMode`
      via the `mode_factories` hook Layer A added.
- [x] **`enable_torque_mode_vel_limit = False` set explicitly**, open item
      #8 closed in `docs/decisions.md` with reasoning — applied as a
      runtime-owned property in `OdriveHardware.set_mode()`'s TORQUE
      branch (reasserted every torque-mode entry, not a one-time NVM
      write), so it resolves the item project-wide rather than
      Force-mode-locally. Live-board confirmation of the property path
      itself is a named, explicit action item in decisions.md — not yet
      done, cannot be done without hardware access.
- [x] **§2.4 regen configuration written**, with real values from the
      user (`BRAKE_RESISTANCE=2.0` confirmed against the physical
      resistor; `DC_MAX_NEGATIVE_CURRENT=-0.5`, tightened from an
      unjustified -3.0 placeholder and justified against the bench's
      13-15V bus; `MAX_REGEN_CURRENT=0` confirmed correct). Property names
      cross-checked against `config/odrive_config.py`'s own live-run
      comments (`odrv0.config.brake_resistance`/`dc_max_negative_current`/
      `max_regen_current`, all top-level bus config, all previously
      confirmed live) rather than trusted from the bundled reference alone.
- [x] **All ten §6 safety behaviours implemented and individually tested**
      (`core/tests/test_force_mode.py`, 29 tests):
      1. No torque without explicit engagement —
         `test_construction_and_arm_apply_zero_torque`,
         `test_engage_requires_explicit_action`.
      2. Force ramps in and out, never steps —
         `test_force_ramps_in_not_instant`,
         `test_force_ramps_in_reaches_target_eventually`,
         `test_force_ramps_out_on_disengage_not_instant`.
      3. Let-go detector fires on sustained reel-in, debounced, hard-stops —
         `test_letgo_fires_during_concentric_and_hard_stops`,
         `test_letgo_does_not_fire_on_subdebounce_transient`.
      4. Let-go detector is state-gated, does not fire outside concentric —
         `test_letgo_does_not_fire_during_holding`,
         `test_letgo_does_not_fire_while_armed` (explicit tests for the
         gating itself, per the spec's own instruction, not just the
         positive case).
      5. No integrator in any force path —
         `test_no_windup_on_sustained_hold_still` (500 ticks held exactly
         at rest, commanded force settles and stays flat — this is also
         the test that caught the `_force_n_param`/isokinetic-base-force
         bug, see below).
      6. Commanded force clamped by F_max, hardware torque-limit, and the
         power limiter, in that order — `test_force_clamped_at_force_max`
         plus the power_limiter.py module tests already covering the
         other two layers' composition.
      7. Force eases off approaching max extension, not a fault under full
         load — `test_force_tapers_approaching_max_extension`.
      8. Fault zeroes torque and requires explicit manual resume —
         `test_resume_returns_to_armed_not_engaged`,
         `test_resume_preserves_force_params_and_leaves_home_max_untouched`,
         `test_resume_rejected_when_not_faulted`.
      9. Stop remains available and effective in every state, including
         mid-rep under full load, and the Layer A current-limit-restore
         path still behaves when Stop lands mid-ENGAGED —
         `test_global_stop_mid_engaged_zeroes_torque_and_restores_
         current_limit` (end-to-end via the real `ControlSession`, not
         just the recording fake).
      10. Sign correctness, asserted directly not just magnitude —
          `test_commanded_torque_opposes_pay_out_during_concentric`.
- [x] **§5.2 break-even analysis computed against real constants and
      recorded** — see decisions.md. Caught and corrected a flawed first
      pass before reporting it (used `CONTROLLER_VEL_LIMIT` as an
      achievable-velocity ceiling that doesn't actually apply once torque
      mode's velocity limiter is disabled) — the corrected analysis shows
      the power limiter is a real, active behaviour during fast constant-
      force reps, not a formality, while isokinetic is self-limiting by
      construction.
- [x] **Constants in `config/board_constants.py`, each with documented
      reasoning** — full table in decisions.md. Two spec §9 rows
      intentionally not duplicated as new constants (hold-threshold reuses
      `PHASE_VEL_THRESHOLD_TURNS_S`, isokinetic force floor reuses
      `FORCE_MIN_N`); two new ones the table didn't list
      (`MOTOR_PHASE_RESISTANCE_OHM`, `ENABLE_TORQUE_MODE_VEL_LIMIT`).
- [x] **UI per §10, including the uncalibrated-force label while §2.2 is
      outstanding** (`frontend/src/components/tabs/exercise/
      ExerciseTab.jsx`'s new Force Feedback card): Newtons primary with a
      kgf secondary hint, mode select (constant/isokinetic) with the
      velocity-cap field only shown for isokinetic, Engage/Disengage
      visually distinct from session Start/STOP via colour and placement,
      live state/commanded-force/estimated-force/velocity/power-limiter
      display, confirmation-gated Resume for FAULT. The uncalibrated-
      estimate label is driven by `board_constants.force.
      torque_constant_is_estimate`, persistent until open item #13 lands
      (same pattern as the Profiles tab's stub-math notice).
      **Verified in a real browser** (headless Chrome via CDP): card
      renders with zero console errors/exceptions; Start Force Session
      correctly disabled while un-homed; mode select toggling to
      isokinetic correctly reveals the velocity-cap field; kgf hint and
      uncalibrated-estimate label both render. Also caught and fixed while
      verifying: a stray backend process left over from earlier in this
      session was squatting on port 5050 without `ODRIVE_MOCK`, silently
      serving "No ODrive device found" to every request.
- [x] **Telemetry and CSV extended per §11** — `commanded_force_n`,
      `estimated_force_n`, `cable_velocity_m_s`, `regen_power_w`,
      `force_state`, `power_limiter_active` appended after
      `cable_length_m`; phase/rep_count columns reused unchanged, not
      duplicated, exactly as the spec asked.
- [x] **Full regression green**: `pytest core/tests` 242/242 (172 Layer A
      baseline this session started from + 40 Layer B pure modules
      (ramps/governor/letgo/power_limiter) + 1 geometry helper + 27
      ForceMode + 2 CSV columns — see commit history for the running count
      at each step), `npx eslint .` clean, `npx vitest run` 40/40 (2
      skipped, unaffected).
      **Layer A and Control/Profiles behaviour confirmed unchanged**: no
      Layer B commit touched `core/cable/exercise_mode.py`, the Control
      tab, or the Profiles tab (confirmed via `git diff --stat` across
      every Layer B commit); live-smoke-tested velocity mode (Control),
      the profile registry (Profiles), and exercise start/stop (Layer A)
      against `ODRIVE_MOCK=1` post-Layer-B, all identical to pre-Layer-B
      behaviour. **Choke-point audit clean** — still exactly one real
      `odrive.find_any()` call site (`backend/app/device_manager.py`);
      `ForceMode` shares the existing `control_session`/
      `_real_hardware_factory`, no new hardware connection path.
- [x] `docs/progress.md` (this entry) and `docs/decisions.md` updated,
      including every architecture deviation and the reasoning for each
      chosen constant, plus three named first-live-run watch items
      cross-referenced to §14's specific escalation steps (added per
      explicit follow-up instruction after the checkpoint 2 report, so
      they survive to whoever is actually at the bench).
- [x] `docs/user_manual.md` / `manual.html` gain the force-feedback
      section (see the entry immediately below this one) — did not
      rabbit-hole into either manual's known pre-existing staleness.
- [x] **Open items L-B1…L-B4 addressed**:
      - **L-B1** (bench-measured torque constant, open item #13):
        **unresolved**, unchanged status. Layer B ships on the fallback
        estimate (`MOTOR_TORQUE_CONSTANT=0.516875`); the UI's uncalibrated-
        estimate label is the honesty mechanism while this stays open.
      - **L-B2** (manual-resume flow after a runaway hard-stop): **resolved**.
        Built exactly per the WHAT doc's own direction — lighter than
        re-homing, an explicit confirmed action, force params preserved,
        home/max untouched, never automatic (`ForceMode`'s FAULT->ARMED
        `resume` action, `/api/force/resume`, confirmation-gated in the UI).
      - **L-B3** (concrete resistance-strength UI): **resolved**. Newtons
        primary (§10.1), kgf secondary hint, `FORCE_MAX_N` as the enforced
        range, `force_to_torque()` (the existing single conversion site,
        reused not duplicated) as the mapping to torque.
      - **L-B4** (explicit start/stop gating for live-vs-idle resistance):
        **resolved** — this is what the ARMED/ENGAGED split *is* (spec §4.1
        literally frames it as resolving this item): zero torque while
        ARMED, resistance only ever live in ENGAGED_CONCENTRIC/HOLDING,
        entered only by an explicit "engage" action.

## First live-hardware session, 23 July 2026 — two bugs fixed, then a "more control" feature phase

The user ran the Exercise tab against real hardware for the first time this
session (bench, no reduction gearing yet — see `docs/decisions.md`'s "First
live run against the real board" entry for full root-cause detail on both
bugs). Two crashes were reported with screenshots
(`enable_torque_mode_vel_limit not found` and `Exercise target must be a
dict, got 0.5`); both fixed same-day and documented in `docs/decisions.md`.
Homing worked; the user then asked, in one long combined message, for
substantially more on-screen control rather than editing
`config/board_constants.py` and restarting the backend for every bench
tuning pass. Built directly off that request, item by item:

- [x] **Live-adjustable homing tuning** (current threshold, reel-in
      velocity, current limit) — `CableState.set_homing_settings()`,
      validated atomically (limit > threshold, limit ≤
      `board_constants.MOTOR_CURRENT_LIM`, no partial application on a
      rejected call), persisted through the same sidecar `k` already used
      (generalized `_load_settings`/`_save_settings` from a single value to
      a settings dict — see `core/cable/state.py`'s module docstring).
      `HomingStateMachine` gained optional constructor overrides (default
      `None` -> `board_constants`); the four safety-margin constants
      (debounce/grace/travel-bound/timeout) deliberately stayed
      `board_constants`-only — not requested, and they're safety margins,
      not calibration values.
- [x] **Live-adjustable spool radius (r0)** — `CableState.set_r0()`, same
      persistence pattern. Caught and fixed a consistency gap before
      shipping: `ForceMode` still read `board_constants.SPOOL_RADIUS_M`
      directly in six places (torque conversion, two velocity conversions,
      power limiter, regen estimate) — the live setting would have been
      stored but silently never used. `force_to_torque()`/`torque_to_force()`
      gained an optional `r0` override to fix this without breaking the
      Profiles-tab callers that have no `CableState`.
- [x] **Live-adjustable max-extension calibration hold force** —
      `CableState.set_calib_hold_force()`, same pattern, exposed via
      `POST /api/exercise/update_calib_hold_force`.
- [x] **Cable position vs. encoder position**, split into two distinct
      status fields (`backend/app/exercise_routes.py::_cable_status_dict`):
      `cable_position_turns` (zeroed at home, `None` until homed) alongside
      the raw absolute `latest_sample.position` (whatever arbitrary value
      the encoder read at power-on) — the ambiguity was the user's specific
      complaint ("wasn't sure if I was looking at 0 from home or the raw
      number").
- [x] **Homing tucked into a collapsible sub-section**, `Collapse`/
      `useDisclosure` (`defaultIsOpen: true` — still visible by default for
      an unattended first run per spec §10), same UI pattern already
      established for Advanced Spool Calibration.
- [x] **Move + Force Feedback laid out side by side**, `SimpleGrid`,
      resolved via `AskUserQuestion` rather than guessed: kept as two
      separate cards (they're still mutually-exclusive modes on the shared
      `ControlSession`, a merged card would blur that), not a merged
      toggle. Move gained Control-tab-style controls it never had — Move
      Velocity and Accel/Decel fields (the backend route already accepted
      `move_velocity_turns_s`/`accel_decel_turns_s2`, just wasn't exposed)
      plus a client-side turns estimate under the length field (r0-only,
      ignores the `k` wrap-growth correction, same simplification already
      used for the kgf force hint — informational, not authoritative).
- [x] **Force Feedback configurable start/end travel sub-range**
      (`core/cable/force_mode.py`) — `engage`/`update_params` accept
      optional `start_length_m`/`end_length_m`, converted to absolute
      encoder turns and validated against the calibrated `[home, max]`
      range (rejected outright if outside it or zero-width, never silently
      clamped). Omitted -> full range, unchanged from before this feature.
      Resolved via `AskUserQuestion`: taper off near both range edges, the
      same as the existing max-extension taper, not a hard disengage or a
      visual-only warning. Reuses the existing pure `taper_factor()` at
      both edges rather than adding a second pure function. One subtlety
      caught by the existing test suite before shipping: the end edge
      always tapers (unchanged safety behaviour, default or custom), but
      the start edge only tapers when it's a real custom boundary away from
      home — tapering a default (home-anchored) start by default would
      have silently changed existing behaviour for every caller who never
      asked for a sub-range (surfaced immediately as `test_force_mode.py`
      failures going from full-force to force=0 at the very first tick,
      since the existing tests engage and tick without ever moving away
      from home).
- [x] **Full regression green**: `pytest core/tests` 266/266 (242 Layer B
      baseline + 24 new across this whole feature phase: homing-settings/
      r0/calib-hold-force persistence and validation tests in
      `test_cable_state.py`, plus 8 range-feature tests in
      `test_force_mode.py`), `npx eslint src/` clean, `npx vitest run`
      40/40 unaffected (no component-level tests exist for
      `ExerciseTab.jsx`; covered by browser verification below instead).
      **Verified in a real browser** (headless Chrome via CDP, against the
      real (non-mock) backend already running from earlier in this session,
      with no ODrive device attached — confirmed via `GET /api/devices`
      returning `[]` before touching anything, so no risk to real
      hardware): navigated to the Exercise tab, confirmed zero console
      errors/exceptions, and confirmed every new field renders — Move
      Velocity/Accel/Decel fields and the turns estimate, the Force
      Feedback Start/End range fields with `home`/`max` placeholders, the
      Max Extension hold-force field, and the Cable position / Encoder
      position split. Screenshotted the Move/Force Feedback side-by-side
      layout to confirm it holds at typical desktop width. Did not click
      any state-mutating action (Start Session, Home, Engage, etc.) against
      this backend — GET-only polling and pure rendering checks, since it's
      the same real (non-mock) `CableState`/sidecar-file instance the user's
      own bench session already persisted real values into.
- [x] `docs/progress.md` (this entry) and `docs/decisions.md` updated.

## Train tab, 25 July 2026

Built from `train_tab_build_spec.md`, a fresh, from-scratch resistance-training
tab built on plain torque control — deliberately *not* `ForceMode`'s (now
`ExerciseMode`'s) governor/ramp/hold/let-go machinery. The spec itself said
it was written from memory and asked its §0 assumptions be checked first;
several were stale (`ForceMode` merged into `ExerciseMode`, `MODES_BY_NAME`
only has 4 entries with "exercise" injected via `mode_factories`, `core/
profiles/` isn't a stub). Full reasoning and the design decisions this forced
(Move/jog built inside `TrainMode` rather than editing `ExerciseMode`; the
real root cause of the graph time-window bug) are in `docs/decisions.md`
("Train tab — build spec §0 research pass").

### §8 Definition of Done

- [x] `core/cable/train_profiles.py` (pure, hardware-free: `TrainSegment`/
      `TrainProfile`, constant/linear/bell shapes, one `preview()` evaluator)
      + `core/cable/train_mode.py` (`TrainMode(BaseMode)`) built, unit-tested
      against the sim/fake-hardware harness (30 + 14 new tests).
- [x] `TrainMode` registered on `ControlSession` via a `mode_factories`
      override in `backend/app/control_routes.py` (`"train":
      lambda: TrainMode(cable_state)`), same pattern `"exercise"` already
      uses — not `MODES_BY_NAME` itself. Confirmed mutually exclusive
      alongside the other five modes and sharing the exact same `CableState`
      singleton as `ExerciseMode` (`ex.cable_state is tr.cable_state is
      control_routes.cable_state`).
- [x] Max-extension enforcement toggle: `CableState.train_max_extension_
      enforced` (persisted, default `True`), live-adjustable via
      `POST /api/train/update_settings`, scoped to `TrainMode`'s tick only
      (reuses the existing `check_runtime_guard`/`position_guard_hard_turns`
      — no new tolerance invented).
- [x] Move panel extended with a torque parameter — built as `TrainMode`'s
      own `move` action (`hardware.set_position_target(..., torque_limit=
      ...)`), not added to `ExerciseMode`. Reasoning (the §3-vs-§6/DoD
      tension this created, and why torque *limit* was chosen over a raw
      torque jog) logged in `docs/decisions.md`.
- [x] Resistance profile editor: segments, 3 shapes (constant/linear/bell),
      live preview graph (`frontend/src/components/tabs/train/
      TrainProfileEditor.jsx`, debounced against `POST /api/train/
      preview_profile`).
- [x] Both Train graphs built fresh (`TrainTimeSeriesChart.jsx`,
      `TrainPositionChart.jsx`) — do not import or modify `MiniChart.jsx`.
      Time-windowing fixed at the actual root cause (a fixed 300-point
      buffer cap at a 50 Hz tick rate silently held only ~6s regardless of
      the "60s"/"All" buttons): `useTrainTelemetry.js`'s rolling buffer
      evicts by sample *age* against a new persisted `train_telemetry_
      buffer_s` setting (default 90s) instead. Toggleable lines (Position
      actual/target, Velocity, Torque) and the target-position dotted
      overlay confirmed working in the browser pass below.
- [x] Every new numeric default is a persisted, `CableState`-backed setting
      (`train_max_extension_enforced`, `train_telemetry_buffer_s`) — the
      standing rule's own named example (graph buffer size). Per-jog
      transient parameters (move length/velocity/accel/torque-limit) follow
      the existing Exercise Move-panel precedent of live text-field defaults
      instead — reasoning in `docs/decisions.md`.
- [x] Exercise/Control/Profiles tabs confirmed unchanged: `git status`
      diffed against this session's own start — the only files this session
      touched are `core/cable/train_*.py` (new), `core/cable/state.py`
      (additive settings only), `core/cable/__init__.py` (new exports),
      `backend/app/control_routes.py`/`app.py` (new mode/route registration,
      additive), `backend/app/train_routes.py` (new), `config/
      board_constants.py` (new Train constants, additive), `core/tests/
      test_train_*.py` (new), `frontend/src/components/tabs/train/*` (new),
      `frontend/src/api/train.js` (new), `frontend/src/hooks/
      useTrainTelemetry.js` (new), `frontend/src/utils/trainGeometry.js`
      (new), `frontend/src/components/MainTabs.jsx` (new tab entry only).
      `exercise_mode.py`, `force_routes.py`, `ExerciseTab.jsx`,
      `ControlTab.jsx`, `MiniChart.jsx`, `ProfilesTab.jsx` all carry only
      the pre-existing uncommitted diff that predates this session
      (verified against the diff captured before any Train work began).
- [x] Full regression green: `pytest core/tests` 335/335 (291 pre-existing +
      44 new: `test_train_profiles.py`, `test_train_mode.py`), `eslint .`
      clean, `vitest run` 40/40 unaffected (no component-level tests exist
      for any tab in this repo; covered by the browser pass below), `vite
      build` succeeds (new `TrainTab` chunk bundles at 26.6kB).
      **Verified in a real browser** against `ODRIVE_MOCK=1` (`npm run
      mock_dev`, headless Chromium via Playwright — no `chromium-cli` in
      this environment, installed directly instead). One real complication
      hit and resolved along the way: a *different*, already-running backend
      process was found bound to port 5050 mid-setup, connected to **real**
      ODrive hardware (`hardware_source: "real"`, a genuine device serial,
      non-zero velocity/current history) — not mock. Flagged to the user
      immediately rather than guessing; the user chose to stop it (via the
      project's own `Stop Freddy.command`, the sanctioned graceful path,
      not a raw kill) so the mock instance could run safely instead. Confirmed
      the mock was actually active before clicking anything state-mutating
      (`GET /api/devices` returning the mock's fake serial `123456789abc`,
      distinct from the real device's `367836843335`). Then exercised the
      full flow end to end: homed (mock homing needed the current threshold
      live-lowered first, since `ODRIVE_MOCK` doesn't simulate a real
      current spike — same limitation `SimHardware`/homing tests already
      route around; restored the threshold and every other live-adjusted
      setting back to their original bench-tuned values afterward), added a
      second (bell-shaped) profile segment and watched the live preview
      update, started a Train session, applied a profile change mid-run,
      jogged via Move and watched the target-position dotted overlay and
      the force-vs-position live overlay both populate correctly, toggled a
      chart line, and stopped — zero console errors the entire time
      (`console --errors` equivalent: Playwright's `console`/`pageerror`
      listeners, empty on the final clean run).
- [x] `docs/progress.md` (this entry) and `docs/decisions.md` updated.

## Train tab refinements, 25 July 2026

First round of feedback after the user actually used the tab. Full
reasoning behind each non-obvious call in `docs/decisions.md` ("Train tab
refinements"). Summary of what changed:

1. **Homing**: added Homing velocity + Current threshold fields to Train's
   Settings/Startup section (`TrainSettingsSection.jsx`), same
   `updateHomingSettings()` call and persisted fields Exercise's own UI
   already uses.
2. **Max-extension calibration**: "Enforce max-extension guard during
   Train" toggle moved into this section, right under Start/Confirm/Cancel.
3. **Setup session**: added a prominent, unmissable "Stop setup session"
   button in the Settings/Startup card header (was previously a small ghost
   button easy to miss).
4. **Manual Move removed entirely** (not just decoupled) from Train, in
   favour of the Control tab's own Position mode. This simplified
   `TrainMode` back to a single state (`core/cable/train_mode.py`) — no
   `_apply_move`/`_apply_stop_move`/`_tick_moving`, no `"moving"` action,
   `/api/train/move`+`/api/train/stop_move` routes removed,
   `moveTrainCable`/`stopTrainMove` removed from the API client. 7 tests
   removed from `test_train_mode.py`, one added (asserts `"move"`/
   `"stop_move"` now correctly rejected as unknown actions) — 328/328
   passing after.
   - **Control tab enhancement** (the other half of this ask): Position
     mode's Move Distance field gained a `turns`/`m` unit toggle.
     Frontend-only — converts metres to turns client-side via the live
     cable `r0`/`k` (new `turnsDeltaFromLength()` in `frontend/src/utils/
     cableGeometry.js`, renamed from `trainGeometry.js` since it's now
     shared) before sending the same turns-based target `PositionMode`
     always took. Zero backend changes; existing turns-only behaviour is
     unaffected (default unit is still turns).
5. **Resistance profile**: untouched, exactly as requested.
6. **Force calibration**: flagged as a real, known issue (displayed vs.
   felt force mismatch; planned ~7N vs. measured ~-80N on the graphs) —
   not patched. Likely root cause and why, recorded in `docs/decisions.md`
   for whoever picks up the calibration procedure next (points at
   `MOTOR_TORQUE_CONSTANT`, already flagged elsewhere as an unmeasured
   fallback — open item #13).
7. **Graphs**: both Train graphs now have proper axis labels, and every
   plotted quantity (Position/Velocity/Torque on the time-series chart;
   Planned/Actual on the force-vs-position chart) gets its own independent
   Y axis with an Auto/manual-range control (`AxisRangeControl.jsx`,
   `domainFromRange()` in `utils/chartDisplay.js`) — not just a shared axis
   with adjustable bounds. This alone fixes the "small quantity unreadable
   next to a large one" complaint even with every axis left on Auto.

### Verification

`pytest core/tests` 328/328, `eslint .` clean, `vitest run` 40/40
unaffected, `vite build` succeeds. Real-browser pass against
`ODRIVE_MOCK=1` (Playwright, as before) confirmed: new homing fields
present and functional, max-extension toggle relocated, Stop Setup Session
button visible/functional, Move panel fully absent (`0` matches for "Move
(manual jog)"), Control tab's metres toggle converts and submits correctly,
and — with an active Train session and all three time-series lines
enabled — all three independently-scaled, independently-labelled Y axes
render correctly. One real bug caught and fixed during this pass: a second
right-side Y axis had its ticks/label clipped at the chart edge (the
`LineChart`'s `margin.right` wasn't growing to fit it) — fixed by computing
the margin from the active right-axis count. Zero console errors throughout.

Hit the same live-hardware-safety situation as the original build session:
a real backend came up on port 5050 mid-verification (the user's own
`Start Freddy.command` session, restarted between turns). Confirmed with
the user before touching it — they clarified no motor is physically
connected this time, so it was safe to interact with directly, but a
firmware/property-tree quirk on that specific board (`RemoteObject` object
has no attribute `axis0'` — likely still in bootloader mode, given it
reports firmware `0.0.0`) meant no session could actually be exercised
against it anyway. Switched to a disposable `ODRIVE_MOCK=1` instance for
the actual verification, as before, and restored every setting touched
along the way (`k`, `train_max_extension_enforced`, `train_telemetry_
buffer_s`, homing threshold/limit) back to the user's real bench-tuned
values afterward — including catching and fixing a subtlety missed the
first time: restoring a setting via a one-off script only fixes the JSON
sidecar on disk, not a *running* server process's own in-memory
`CableState`, which will silently overwrite the file with its own stale
values on the next unrelated settings save. Restored `k` correctly this
time by fixing the sidecar only after stopping every backend process, once
nothing was left alive to clobber it.
- [x] `docs/progress.md` (this entry) and `docs/decisions.md` updated.

## Frontend consolidation to four tabs, 28 July 2026

*Written by reading the working tree directly rather than a live build
session transcript — this entry and the matching one in `docs/decisions.md`
document a body of uncommitted changes that were sitting in the repo
undocumented (no corresponding `progress.md`/`decisions.md` entries existed
for any of it before now). Flagged so the gap is visible rather than
silently backfilled as if it had been logged at the time.*

Since the "Train tab refinements" entry above (which still describes an
eight-tab app with a separate Exercise tab), the frontend has been reduced
to **four tabs**: Configuration, Control, Train, Inspector.
`ExerciseTab.jsx`, `DashboardTab.jsx`, `PresetsTab.jsx`, `ProfilesTab.jsx`
(and their supporting files — `useExerciseStatus.js`,
`presetsOperations.js`, `DashboardTab.css`, `frontend/src/api/profiles.js`)
are deleted from disk and no longer referenced from `MainTabs.jsx`'s
`TAB_CONFIG`.

**Nothing was removed at the backend/`core/` level** — `ExerciseMode`
(including the force-feedback machinery merged into it during the "more
control" phase, per the §0 discrepancies note in `docs/decisions.md`),
`core/profiles/`'s four resistance-profile stubs, and their respective
routes (`exercise_routes.py`, `force_routes.py`, `control_routes.py`'s
`"profile"` mode) are all still registered on the Flask app
(`backend/app/app.py` still imports and registers all four route modules)
and still covered by `core/tests`. What changed is **reachability**:

- **Force Feedback (Engage/Disengage, constant/isokinetic torque
  resistance, the ARMED/ENGAGED/HOLDING state machine documented in the
  "First live-hardware session" entry's §2.6.1 write-up above) currently
  has no frontend UI at all.** `frontend/src/api/force.js` still exists but
  is no longer imported by any component (confirmed:
  `grep -rn "from.*api/force" frontend/src` returns nothing) — it's
  reachable only via raw HTTP calls to `/api/force/*`, not through Freddy's
  UI. This looks like an unintentional gap left by the tab cleanup rather
  than a deliberate decision (no `docs/decisions.md` entry motivates it),
  and is carried forward as a new open item in the master plan doc.
- **The Session-3 resistance-profile stubs (constant/bell-curve/overload/
  VBT via `ProfileMode`) are in the same position** — `core/profiles/` and
  `"profile"` mode are alive and tested, but `ProfilesTab.jsx` is gone and
  nothing else in the UI starts a `"profile"` session. Superseded in
  practice by Train's own position-based segment profiles
  (`core/cable/train_profiles.py`), which cover the same "dynamic
  resistance vs. position" need through a different, simpler mechanism —
  but the old phase/rep-aware profiles (bell-curve strength-curve matching,
  VBT auto-regulation, eccentric-overload wrapper) are not equivalent to
  Train's segments, and are now effectively unreachable, not just replaced.
- **Homing, max-extension calibration, and spool calibration** (all
  originally Exercise-tab UI) are still fully reachable — they moved into
  Train's own "Settings / Startup" collapsible section
  (`TrainSettingsSection.jsx`), which drives the exact same
  `startExerciseSession`/`homeExercise`/`startMaxCalibration`/
  `calibrateSpoolK`/`updateHomingSettings` routes the old `ExerciseTab.jsx`
  called, against the same shared `CableState`. This is not a regression —
  the "Train tab refinements" entry above already documents this
  consolidation starting; this pass finished it by deleting the
  now-fully-redundant standalone Exercise tab.

**Other additions bundled into this same uncommitted state**, not
previously logged:

- **Train profile save/load** (`TrainProfileEditor.jsx` gained Save/Load/
  Delete against `frontend/src/utils/trainProfilesManager.js`) — named
  segment layouts persist in `localStorage` (`freddy.trainProfiles.v1`),
  same pattern as the old `presetsManager.js` but for the
  `{name, segments}` `TrainProfile` shape. Not written to `CableState` /
  the backend at all — purely a frontend convenience so a profile doesn't
  need retyping every session.
- **Always-available sidebar controls** (`DeviceList.jsx`, persistent
  regardless of active tab): a **Go Home** button that jogs the cable back
  to its homed position via `ExerciseMode`'s existing move action (only
  enabled once homed; arms a session if none is running and releases it
  again on arrival), a **Reset** button that forgets the backend's cached
  device handle/lock for a soft reconnect without a full restart, and the
  existing **EMERGENCY STOP**. `App.jsx` separately has a **Restart
  Freddy** button (full backend process restart, heavier than Reset).
- **One-click launchers**: `Start Freddy.command` (kills any stale
  backend/frontend on ports 5050/3000, starts both fresh against real
  hardware — no `ODRIVE_MOCK` — waits for both to come up, then opens
  Safari) and `Stop Freddy.command` (kills both ports) at the project
  root, replacing the earlier `Start UI.command` mentioned in older docs
  (never actually committed; not present on disk any more).
- **`config/diagnose_encoder_spi.py` + `config/odrive_diag_common.py`**:
  read-only bench diagnostic tooling (`AXIS_STATE_LOCKIN_SPIN` open-loop
  drive test + a slowed-down encoder-calibration attempt) built during the
  investigation that root-caused the AS5047P "super-sulk" fault (see the
  master plan doc's §11.1) and left in the repo as a reusable diagnostic,
  not folded into `odrive_config.py` itself.
- **`INDEX.md`** (directory-tree reference, generated 21 July) is now stale
  against the current tree — regenerated as part of this same doc pass.

### Verification

Not independently re-run as part of this doc-only pass — the last known
green baseline is "Train tab refinements"'s `pytest core/tests` 328/328 /
`eslint .` clean / `vitest run` 40/40 / `vite build` succeeds, and no
`core/`-level code changed since (only frontend deletions + additive
frontend/doc files). Worth a fresh full run at the start of the next
session before trusting that number, since it predates the tab deletions.
- [x] `docs/progress.md` (this entry), `docs/decisions.md`, `README.md`,
      `INDEX.md`, and the master plan doc (`skripsie_project_plan_1_6.md`)
      updated to match.

## Train tab — calibration overhaul, 29 July 2026

Six change requests against the Train tab. See `docs/decisions.md`'s
matching entry for the reasoning behind each — two (guard toggles, spool
growth calibration) needed investigation before any code change, and that
investigation changed what "the fix" actually was for both.

- [x] **Hard Reset control** — `TrainTab.jsx` gained a Reset button
      (disabled while a session is running) behind a new confirm modal
      (`frontend/src/components/modals/TrainResetModal.jsx`, same
      self-contained shape as `EraseConfigModal.jsx`). Calls the existing
      `/api/exercise/reset_position` (clears home/max/marked-max, leaves
      r0/k/growth/homing settings and saved named profiles untouched) plus
      clears pending (unsaved) spool-growth calibration points; the
      frontend additionally resets its own draft profile (remount key),
      action-error state, and an active telemetry freeze. Found and fixed
      a real gating gap while wiring this up: the route's idle-check only
      ever blocked a running *Exercise* session, not Train — widened to
      any running session (`_any_session_running`, was
      `_exercise_action_running`).
- [x] **Guard-toggle "bug"** — investigated (re-read `TrainMode.tick()`,
      re-ran all 21 existing guard tests, all green); no code defect
      found. Shipped a UI-clarity fix instead
      (`TrainSettingsSection.jsx`): the "only applies to a running Train
      session, not Exercise's own guard" caveat now sits directly under
      each toggle rather than trailing below both.
- [x] **Spool radius compensation** — `TrainMode.tick()`'s force→torque
      conversion now uses `SpoolGeometry.r_eff_at_turns_delta()` (the
      position's actual effective radius under whichever spool model is
      calibrated — k or the piecewise growth fit) instead of the static
      r0, floored at `SPOOL_MIN_EFFECTIVE_RADIUS_M` (load-bearing: the
      piecewise model's open-ended final segment can extrapolate through
      zero given a negative slope and a disabled guard — see decisions.md).
      `core/tests/test_train_mode.py` gained 3 new tests. Also fixed the
      same bug's frontend twin: `cableGeometry.js` gained a piecewise
      mirror (`createSpoolGeometry`, cross-checked against
      `geometry.py`'s `SpoolGeometry` — `cableGeometry.test.js`, 11
      tests) and `useTrainTelemetry.js` now uses it for the live chart's
      position/force conversion instead of the old flat-r0/k-only mirror.
      Confirmed via the existing `SpoolGrowthCalibration.jsx` flow itself
      needs no code fix — its Start button is precondition-gated (setup
      session + homed) the same as the neighboring max-calibration button,
      not blocked by anything.
- [x] **Resistance profile segment editor** (`TrainProfileEditor.jsx`) —
      segments can now be split in place (new "Split" button per segment,
      midpoint cut, both halves immediately editable; bell segments get
      their `peak_pos_m` recentered per half so validation passes
      immediately) instead of requiring the whole profile to be rebuilt
      to insert one in the middle. `addSegment()`'s existing
      start-position auto-continue gained a force counterpart: a new
      segment's force now seeds from the previous segment's own
      end-force instead of a hardcoded default.
- [x] **Telemetry pause/freeze** — new `frontend/src/hooks/
      useFreezableSeries.js`, a thin, reusable wrapper (not baked into
      the chart or the polling hook) around any live series array; wired
      into the Train tab's time-series chart via a Pause/Resume button.
      Reset (above) clears an active freeze.
- [x] **Telemetry logic audit + reuse** — audited `useTrainTelemetry.js`
      first (already correct: age-based buffer eviction against
      `cable.train_telemetry_buffer_s`, not a fixed point count) and
      extracted its merge/cutoff logic into `frontend/src/utils/
      telemetryBuffer.js::appendAndTrimByAge()` (6 new tests). Control
      tab's `useControlTelemetry.js` had the exact older bug
      (`MAX_CHART_POINTS = 300`, ~6s of real history at 50Hz regardless
      of its range buttons) — now uses the same shared function.
      Inspector's `LiveCharts.jsx` keeps its WebSocket/Redux transport
      (genuinely different requirements — arbitrary per-property
      selection at ~10ms vs. Train/Control's small fixed set at 150ms
      REST poll; not swapped out) but its own fixed-point display window
      (`WINDOW_POINTS = 240`) was replaced with a new age-based
      `chartDisplay.js::filterByAgeMs()` helper at an equivalent default
      duration — `chartDisplay.test.js` added (11 tests; first coverage
      for this file, now shared by three components).

### Verification

- [x] `pytest core/tests/` — 373/373 (was 373 before this session's new
      tests were added and counted; net +3 in `test_train_mode.py`, no
      regressions elsewhere).
- [x] `vitest run` (frontend) — 72 passed, 2 skipped (pre-existing
      live-hardware-only integration tests), 0 failed. New files:
      `cableGeometry.test.js` (11), `telemetryBuffer.test.js` (6),
      `chartDisplay.test.js` (11, first coverage for that file).
- [x] `vite build` — succeeds, no new warnings beyond the pre-existing
      chunk-size and dynamic/static `deviceSocket.js` import notices.
- [ ] Manual pass on real hardware — not done as part of this session
      (no device attached). Still needed before trusting this on the
      actual thicker-strap rig: Reset button end-to-end, guard toggles
      during an actual running Train session (not just Exercise setup),
      the spool growth calibration flow with real measured lengths across
      the ~0.06m→~0.04m range, segment split + force continuity in the
      editor, pause/resume on the Train chart, and a visual check that
      Control's chart range buttons and Inspector's charts now show their
      claimed durations.

## Same graphs everywhere: Control/Inspector get Train's chart style, 29 July 2026

Follow-up to the calibration-overhaul session above — see
`docs/decisions.md`'s matching entry for the full reasoning, including
the `AskUserQuestion` resolution on why Control got a literal one-chart
merge while Inspector kept per-property cards with upgraded controls.

- [x] **`components/shared/TelemetryTimeSeriesChart.jsx`** (+ moved
      `AxisRangeControl.jsx`) — Train's chart, generalized from a
      hardcoded 3-line config to a `lines` prop, with pause/freeze now
      owned internally (`useFreezableSeries`) instead of by the caller.
      New `axisKey` support lets two lines share one Y axis (used for
      Control's target-position overlay).
- [x] **Control tab** — `ControlTab.jsx` now renders one
      `TelemetryTimeSeriesChart` (Position/Target position/Velocity/
      Torque, all in one card with the full Train-style control set)
      instead of three separate `MiniChart.jsx` cards.
      `useControlTelemetry.js`'s buffer duration constant
      (`CONTROL_TELEMETRY_BUFFER_S`) exported so the chart's range
      buttons cap themselves against the real buffer. `MiniChart.jsx`
      deleted (no remaining callers).
- [x] **Train tab** — `TrainTab.jsx` updated to the shared component;
      its own Pause/Resume button and "Frozen" badge (previously in the
      tab's top button row) removed in favor of the ones now built into
      the chart card itself. Reset remounts the chart via a `key` bump
      to drop an active freeze (no imperative API on the chart).
- [x] **Inspector tab** — `LiveCharts.jsx`'s per-property `PropertyChart`
      cards gained axis-range/invert/smoothing controls (smoothing now
      user-controlled, default Off, replacing a fixed always-on
      `SMOOTHING_WINDOW=5`), plus one shared header Pause (freezes every
      property's data at once) and a shared `1s/2.5s/5s/10s/All`
      duration control. Card height 220px → 320px. Transport
      (WebSocket→Redux) unchanged — kept for its arbitrary per-property
      selection at a much higher rate than Train/Control's REST poll.
      `chartDisplay.js::filterByAgeMs()` gained `ms == null` = "no
      filter" to support "All."
- [x] **Bug found and fixed via a real-browser smoke pass, not the unit
      test suite**: `TrainTab.jsx`'s Reset used two separate `useState(0)`
      counters as `key` props on two sibling components
      (`TrainProfileEditor`, the chart) — always bumped together, so
      always numerically equal, so React warned about duplicate sibling
      keys on every render. `vitest` never renders this tree, so nothing
      caught it until an actual Chromium render did. Fixed by
      string-prefixing each key.

### Verification

- [x] `pytest core/tests/` — 373/373, unaffected (this pass was
      frontend-only).
- [x] `vitest run` — 73/73 passed, 2 skipped (pre-existing
      live-hardware-only), unchanged from before this pass.
- [x] `vite build` — succeeds.
- [x] **Real-browser smoke pass** (Playwright + headless Chromium against
      `npm run mock_dev`, no project run-skill existed yet so one was
      improvised per the `run` skill's browser-driven fallback pattern —
      worth turning into a proper project skill via
      `/run-skill-generator` next time this comes up) — all three tabs
      (Control/Train/Inspector) navigated, zero console errors after the
      key-collision fix, and interactive checks (select an Inspector
      property, Pause → "Resume"/"Frozen" badge, change duration) all
      behaved as designed. Screenshots confirmed Control's combined
      chart, Train's chart with pause now in its own header, and
      Inspector's per-property card controls all render correctly.
- [ ] Still not verified against real hardware / real telemetry actually
      flowing (mock backend reports no device connected in this
      environment) — the interactive controls were exercised structurally
      (empty-data state) but not against a live-updating chart.

---

# Testing tab — controlled experiments (Static Weight Hold)

Tracks the "Testing Tab — Build Spec" (30 July 2026). New `core/experiments/`
package, a Testing tab mirroring the Train tab pattern, and the static weight
hold experiment described in the spec. Full reasoning for every judgment call
is in `docs/decisions.md` ("Testing tab" section) — this file tracks
completion + verification method only.

## §8 — Open questions, resolved by reading the code (no guessing)

- [x] **#1 — where Train persists calibration**: `core/cable/state.py::CableState`.
      `home_turns`/`max_turns` are in-memory only, by explicit existing design
      (a fresh backend process always comes up un-homed) — not a new gap this
      feature introduces; the Testing tab gates on the exact same
      `is_homed`/`has_max` Train already gates on. Flagged to Ivan in
      decisions.md rather than silently assumed fine.
- [x] **#2 — 50 Hz loop extension point**: confirmed clean via
      `mode_factories` (no refactor needed) — `ExperimentMode` registered in
      `backend/app/control_routes.py` exactly like `"train"`/`"exercise"`,
      same shared `cable_state`/`control_session` singletons (proof of "no
      second ODrive connection").
- [x] **#3 — phase vs. bus current**: only phase current (`current_iq`,
      `Iq_measured`) was exposed; added `TelemetrySample.bus_voltage_v` (new
      field, defaulted so ~20 existing test call sites are unaffected),
      populated from `odrv0.vbus_voltage` (real) / `SIM_BUS_VOLTAGE_V`
      placeholder (sim).
- [x] **#4 — Stop shutdown behavior**: confirmed `HardwareInterface.stop()`
      zeros velocity/torque and requests `AXIS_STATE_IDLE` — the experiment's
      COMPLETE/ABORTED paths call this directly, no new shutdown sequence.

## §2 — `core/experiments/` package

- [x] Built per the spec's suggested shape: `base.py` (`ExperimentState`,
      `ExperimentConfig`, `ExperimentStepResult`, the `Experiment` ABC —
      deliberately hardware-free, mirroring `ResistanceProfile`'s pure-function
      shape rather than `TrainMode`'s hardware-writing `tick()`),
      `static_hold.py` (`StaticWeightHoldExperiment`), `registry.py`
      (`EXPERIMENT_REGISTRY`, mirrors `PROFILE_REGISTRY`), `telemetry.py`
      (`estimated_power_w()` helper only — CSV schema itself stays in
      `core/telemetry/csv_logger.py`), `mode.py` (`ExperimentMode(BaseMode)`,
      lives in `core/experiments/` following `TrainMode`'s own
      cross-package-BaseMode-subclass precedent).
- [x] RAMPING → LIFTING → HOLDING → COMPLETE/ABORTED implemented exactly per
      §2.2–§2.4, including the literal `clamp(torque_command, 0,
      max_torque_nm)` HOLDING formula (flagged as spec's deliberate v1
      simplification, not an oversight) and the flat frozen-torque LIFTING
      approach. `max_torque_nm`/`max_duration_s` enforced every `step()` tick.
      Sign convention (no `CABLE_SIGN` flip on this experiment's torque) and
      the COMPLETE-vs-ABORTED spec inconsistency (resolved: timeout →
      COMPLETE, torque breach → ABORTED) both documented in-code and in
      decisions.md.
- [x] Every numeric threshold is a persisted, user-editable `CableState`
      setting (`set_test_settings()`, same subset-update/validate/persist
      pattern as `set_force_settings`/`set_train_settings`), defaulting from
      seven new `config/board_constants.py` constants — never a bare literal.
- [x] `ExperimentMode` two-phase action dispatch (`configure` — safe, zero
      motion; `confirm_start` — the one explicit, human-confirmed call that
      begins RAMPING) — the motor-energization gate (spec §5) is structural,
      not just a UI convention: the motor cannot move between the two calls.
      `tick()` calls `hardware.stop()` immediately, same-tick, the instant
      COMPLETE/ABORTED is reached.

## §3 — Telemetry

- [x] `core/telemetry/csv_logger.py` gained 7 columns (`experiment_state,
      position_m, velocity_m_s, commanded_torque_nm, bus_voltage_v,
      estimated_power_w, target_position_m`), additive, empty-string default
      for every other mode — same pattern as every prior amendment (phase/
      rep_count, cable_length_m, the six Force-mode columns). No separate
      `measured_current_a` column — reuses the existing `current_iq_a`
      column (documented, not duplicated). `core/control/session.py`'s
      `_telemetry_loop` threads the new extras through.
- [x] `estimated_power_w` = mechanical power (`torque_est * velocity *
      2*pi`), documented choice over `current * voltage` (would double-count
      against the phase-current channel already logged).

## §4/§5 — Backend + frontend wiring, safety gates

- [x] `backend/app/experiment_routes.py` (new): `GET /api/experiments`
      (registry-driven, mirrors `/api/profiles`), `GET /api/experiments/status`
      (reuses `exercise_routes._cable_status_dict()`, adds
      `current_position_m`), `POST /api/experiments/configure`,
      `POST /api/experiments/confirm_start`, `POST /api/experiments/stop`.
      Registered in `backend/app/app.py` alongside the other three route
      modules. `backend/app/control_routes.py` gained one `mode_factories`
      entry (`"experiment": lambda: ExperimentMode(cable_state)`), same
      shared singletons every other mode already uses.
- [x] Frontend Testing tab (`frontend/src/components/tabs/testing/`):
      `TestingTab.jsx` + `ExperimentConfigForm.jsx`, registered in
      `MainTabs.jsx`. Prerequisite banner (mirrors Train's `!isHomed` alert,
      extended to `has_max` too), registry-driven experiment selector,
      schema-driven config form (`initial_position_m` read-only + Refresh,
      never free-typed, per §4.3), explicit "Confirm & Energize Motor"
      button (only enabled once `CONFIGURED`), always-visible STOP, three
      shared `TelemetryTimeSeriesChart` lines (position with a dashed
      target-position reference line, torque, current/voltage/power), and a
      post-run summary card once `experiment_state` is
      `complete`/`aborted`. `api/experiments.js` + `useExperimentTelemetry.js`
      (mirrors `api/train.js`/`useTrainTelemetry.js` exactly).
- [x] **Note for Ivan, not in the spec's open questions but worth flagging**:
      the spec's "Sim/Real banner" ask (§4) describes a UI element that no
      longer exists — this project runs against real hardware only in the
      GUI now (`control_session` hardcoded `hardware_source="real"`). The
      Testing tab mirrors what Train actually looks like today instead
      (connection/running/homed badges, no sim/real switcher).

## §7 — Verification

- [x] **1. `core/tests/` pytest suite** — 410/410 passing (69 new: 20 pure
      `Experiment`/`StaticWeightHoldExperiment` state-machine tests
      (`test_experiments.py`, no hardware fake needed), 6 `ExperimentMode`
      tests against a `RecordingHardware` fake (`test_experiment_mode.py`,
      same style as `test_train_mode.py`), 7 end-to-end `ControlSession`
      tests against `SimHardware` (`test_experiment_session.py` — full
      RAMPING→LIFTING→HOLDING cycle, CSV column/label correctness, Stop
      verified from RAMPING/LIFTING/HOLDING in three separate runs,
      `max_torque_nm` breach → ABORTED + same-tick `hardware.stop()`,
      `max_duration_s` timeout → COMPLETE, start rejected when not homed),
      2 new `csv_logger` column tests). No real hardware required.
- [x] **2. `npx eslint .`** — clean, zero warnings, whole frontend tree.
      **`npx vitest run`** — 73/73 passing, 2 skipped (unchanged baseline).
- [x] **3. Live wiring check** — spun up the real Flask app (`ODRIVE_MOCK=1`)
      and confirmed `/api/experiments` returns the correct registry-driven
      schema and `/api/experiments/status` returns the expected
      cable/control shape, via curl.
- [x] **4. Headless-Chrome pass** (puppeteer-core + local Chrome, scratchpad
      script, same precedent as every prior session) — Testing tab renders,
      prerequisite banner correctly shows "Complete calibration in the Train
      tab first — cable is not homed" and correctly hides the config form
      while un-homed, **zero console errors**.
- [ ] **Not verified**: the full Configure → Confirm & Energize → RAMPING →
      LIFTING → HOLDING → Stop cycle against a *live browser*. Homing
      against `SimHardware` cannot complete in reasonable time — the sim has
      no cable-load model (documented, pre-existing limitation, not
      introduced by this feature): homing's current-threshold detection
      never trips against a free-spinning sim motor, so it always ends in
      `FAULT_TRAVEL_EXCEEDED`/`FAULT_TIMEOUT` rather than `HOMED`. The
      identical code path (`ExperimentMode` + a directly-homed `CableState`)
      IS verified end-to-end by `test_experiment_session.py` above, just not
      through the browser. Real-hardware verification of this tab, same as
      the rest of the spec's own Definition of Done, is deferred to a
      supervised session with Ivan present.

## Definition of Done

- [x] `core/experiments/` package per §2, tests against the mock/sim, no
      real hardware required to pass (§7 above).
- [x] Testing tab renders, shows prerequisite state correctly, blocks start
      when calibration is missing (verified live, §7.4 above).
- [x] Full RAMPING → LIFTING → HOLDING → COMPLETE cycle runs end-to-end
      against the mock/sim, produces a CSV with all channels, correct state
      labels per row (`test_experiment_session.py`).
- [x] Stop verified to safely halt from RAMPING, LIFTING, and HOLDING in
      separate test runs (`test_experiment_session.py`).
- [x] `max_torque_nm`/`max_duration_s` abort/complete paths tested against
      the mock/sim (`test_experiment_session.py`).
- [x] No new ODrive connection opened — `ExperimentMode` shares the exact
      same `cable_state`/`control_session` singletons as every other mode.
- [x] `docs/progress.md` (this section) and `docs/decisions.md` updated,
      including the sign-convention caveat, the COMPLETE-vs-ABORTED spec
      inconsistency resolution, the 0-floor HOLDING clamp v1 simplification,
      and the removed Sim/Real banner note.
- [ ] Not yet run against real hardware — deferred to a supervised session
      with Ivan present, per the spec's own explicit instruction.

---

# Anti-cogging calibration — added to Configuration → Motor Controls

Task: "Add anti-cogging calibration to Freddy" (add a way to trigger/monitor
ODrive's built-in anti-cogging calibration from the GUI). Initially placed
the card in the Testing tab; moved at the user's explicit request to the
Configuration tab's existing "Motor Controls" sub-tab
(`frontend/src/components/tabs/config wizard/ConfigurationTab.jsx`,
`subTabIndex === 1`) instead, alongside the existing `MotorControlsCard`
(Enable/Disable Motor, Full/Motor/Hall/Encoder calibration, Clear Errors,
Save & Reboot) — the same family of quick hardware actions, a better fit
than a tab built for controlled cable-load experiments.

## §1 — Design decision: separate module, not a ControlSession mode

- [x] Deliberately NOT built as a `core/control/modes.py` `BaseMode` /
      `core/experiments/` `Experiment` — those model a continuous per-tick
      control loop; anti-cogging calibration is a one-shot,
      firmware-autonomous routine (the axis spins through ~1 turn on its own
      once `controller.start_anticogging_calibration()` is called — nothing
      here commands it tick by tick) that writes NVM config and reboots the
      board. That's exactly the "config/calibration writes" territory
      `core/hardware/odrive_hw.py`'s own docstring assigns to "the wizard's
      and the 1B script's job," not to a `HardwareInterface`. Built instead
      as its own module, `core/hardware/anticogging.py`
      (`AnticoggingCalibration`, a small request-driven state machine:
      IDLE → start() → RUNNING → poll() [repeated] → DONE/ABORTED/FAILED),
      plus `backend/app/anticogging_routes.py` (thin adapter, same split as
      every other routes module).
- [x] Still routes through the one real choke point: `backend/app/
      anticogging_routes.py` calls `device_manager.get_shared_handle()` /
      `get_shared_io_lock()` — the exact same functions
      `core/hardware/odrive_hw.py::OdriveHardware` is injected with via
      `control_routes.py::_real_hardware_factory` — never `odrive.find_any()`
      directly. Confirmed via `grep -rn "find_any" --include="*.py" backend
      core config`: no new call site.
- [x] `GET /api/anticogging/status` is the one route that drives the state
      machine forward: if RUNNING, it polls the live `calib_anticogging`
      flag on every call, and the moment that flips to finished, the SAME
      call runs the whole restore-gains/`pre_calibrated`/
      `save_configuration()` sequence inline (no separate "saving" phase to
      poll for — it's a handful of fast property writes plus one RPC).
      `save_configuration()` reboots the board mid-call; the expected
      `fibre.protocol.ChannelBrokenException` is caught exactly like
      `config/odrive_config.py`'s `call_and_reconnect()` does. Right after a
      DONE transition, `device_manager.forget_all()` is called so the rest
      of the app (Inspector, sidebar, any other tab) reconnects on its very
      next access instead of waiting for the ambient ~3s sidebar poll to
      notice the dead cached handle on its own.

## §2 — `core/hardware/anticogging.py`

- [x] `AnticoggingCalibration.start()`: rejects if already running; rejects
      via `RuntimeError` if `axis.motor.is_calibrated`/`axis.encoder.is_ready`
      are false (never re-runs motor/encoder calibration itself — that's
      `config/odrive_config.py`'s job); captures the *current*
      `pos_gain`/`vel_integrator_gain` (not board_constants' tuned values —
      if the board's since been re-tuned, that's what "restore" should mean);
      sets `control_mode=CONTROL_MODE_POSITION_CONTROL`,
      `input_mode=INPUT_MODE_PASSTHROUGH`, the two calibration thresholds,
      raises the two gains by the given multipliers, requests
      `AXIS_STATE_CLOSED_LOOP_CONTROL`, then calls
      `controller.start_anticogging_calibration()`.
- [x] `.poll()`: no-op while `calib_anticogging` is still true; on
      completion, restores both gains exactly, sets
      `anticogging.pre_calibrated = True`, calls `save_configuration()`
      (catching the expected reboot-triggered `ChannelBrokenException`,
      any other exception → `FAILED` with a message, gains restored either
      way).
- [x] `.abort()`: requests `AXIS_STATE_IDLE`, restores both gains, does
      **not** set `pre_calibrated` and does **not** save — matches the task
      spec's abort sequence exactly.
- [x] Property paths corroborated against
      `frontend/src/utils/odriveApiReference05x.json` before writing any
      code: `axis{n}.controller.config.anticogging.{pre_calibrated,
      calib_anticogging, calib_pos_threshold, calib_vel_threshold,
      anticogging_enabled}` and `axis{n}.controller.start_anticogging_
      calibration()` all confirmed present; `axis{n}.controller
      .anticogging_valid` (read-only) also found and surfaced as a
      diagnostic. `axis{n}.motor.is_calibrated` / `axis{n}.encoder.is_ready`
      (the precondition check) also confirmed present in the same reference.
- [x] `core/tests/test_anticogging.py` — 17/17 passing, fake `odrv`/`axis`
      object tree (same "fake the hardware surface directly" style as
      `RecordingHardware` elsewhere, since this deliberately isn't a
      `HardwareInterface`): rejects on uncalibrated motor/encoder, rejects
      double-start, rejects invalid numeric args, gain-multiplication +
      RPC-triggering on start, poll-while-running is a no-op, poll-on-
      completion restores gains + sets `pre_calibrated` + saves,
      `ChannelBrokenException` on save is treated as success, any other
      save exception → FAILED with the message surfaced, abort restores
      gains without saving, restart-after-abort works.

## §3 — Config: `config/board_constants.py` + backend routes

- [x] New constants: `ANTICOGGING_POS_GAIN_MULTIPLIER_DEFAULT` /
      `ANTICOGGING_VEL_INTEGRATOR_GAIN_MULTIPLIER_DEFAULT` (both 6.0 — the
      task's own suggested "4-8x" starting range, expressed as a multiplier
      of the *live-tuned* `CONTROLLER_POS_GAIN`/`CONTROLLER_VEL_INTEGRATOR_
      GAIN`, not a second pair of absolute values, so re-tuning the normal
      gains never leaves this block silently stale), and
      `ANTICOGGING_CALIB_POS_THRESHOLD_DEFAULT` / `_VEL_THRESHOLD_DEFAULT`
      (1.0 / 0.5 — flagged `TODO(bench)`: no documented ODrive default found
      in the bundled reference or anywhere else in this repo; conservative
      placeholders, not measured values). All four served via
      `GET /api/board-constants`'s new `"anticogging"` key — never
      duplicated into frontend code.
- [x] `backend/app/anticogging_routes.py`: `GET /api/anticogging/status`,
      `POST /api/anticogging/{start,abort,set_enabled}`. `start` is rejected
      with a clear 400 if any Control/Train/Testing `ControlSession` mode is
      currently running (anti-cogging calibration takes over
      control_mode/input_mode/gains directly, bypassing `ControlSession`
      entirely, so it can't safely run alongside one). `set_enabled` is a
      direct, independent property write (`anticogging_enabled`) — no
      calibration state-machine involvement, always available, doesn't
      erase the saved map.
- [x] Registered in `backend/app/app.py` alongside the other four routes
      modules. Verified live: `python -c "...create_app()..."` lists all
      four `/api/anticogging/*` rules; full `core/tests` suite still
      427/427 passing.

## §4 — Frontend: Configuration → Motor Controls gets an "Anti-cogging Calibration" card

- [x] `frontend/src/api/anticogging.js` (thin client, same `getJson`/
      `postJson` pattern as every other API module),
      `frontend/src/hooks/useAnticoggingStatus.js` (1s REST poll, same
      convention as every other tab — no websocket),
      `frontend/src/components/AnticoggingCalibrationCard.jsx` (new,
      alongside `MotorControlsCard.jsx` at the same directory level) —
      initially built inside the Testing tab, **moved at the user's explicit
      request** into `ConfigurationTab.jsx`'s "Motor Controls" sub-tab,
      rendered directly below `MotorControlsCard` (same `subTabIndex === 1`
      `isActive` gating). Deliberately NOT wired through `useCalibration`'s
      axis-state-polling mechanism (that hook watches the axis return to
      IDLE after a state-machine calibration step; anti-cogging calibration
      instead polls a dedicated `calib_anticogging` boolean and needs its
      own gain-raise/restore + save+reboot sequence) — reads
      `control_session_running` from its own polled status rather than a
      prop, so it has no dependency on whichever tab happens to render it.
- [x] Gain-multiplier/threshold fields editable per-run, pre-filled from
      `GET /api/board-constants`'s new `anticogging` section (same
      pattern as `ExperimentConfigForm`'s config fields on the Testing tab)
      — not persisted live-adjustable settings via `CableState` (a narrower
      reading of this task's "editable settings in board_constants.py, not
      buried constants" than the Testing tab's own build spec's stronger
      "user-editable, persisted setting" wording; see docs/decisions.md).
- [x] Explicit confirmation dialog ("Run anti-cogging calibration?" /
      "Confirm & Energize Motor") before `start()` fires — same
      motor-energization-gate convention as the Testing tab's own experiment
      flow and `App.jsx`'s Restart-Freddy dialog. Abort button visible only
      while running. `anticogging_enabled` toggle (Switch) always available.
      State/`pre_calibrated`/`anticogging_valid` badges.
- [x] Verified: `npx eslint .` clean; `npx vitest run` 73/73 passing (2
      skipped, unchanged baseline); headless-Chrome pass against the real
      running dev server — connected the real device via the sidebar
      (Scan → Connect, normal read-only app usage), navigated Configuration
      → Motor Controls, confirmed both `MotorControlsCard` ("Enable Motor"
      etc.) and the new card render side by side (IDLE / MAP SAVED / MAP
      VALID badges, all four fields, defaults line, "Calibrate anti-cogging"
      button), and confirmed the card no longer appears on the Testing tab.
      **Confirm was never clicked** — this session's dev backend is
      connected to the real physical board (see docs/decisions.md), so
      actually triggering calibration was deliberately left for a
      supervised session with Ivan present.

## Definition of Done

- [x] `core/hardware/anticogging.py` + tests, no real hardware required to
      pass (§2 above).
- [x] Backend routes wired, gated on no-other-session-running, no new
      `odrive.find_any()` call site (§1/§3 above).
- [x] Configuration tab's Motor Controls sub-tab shows a "Calibrate
      anti-cogging" action with a
      progress/status indicator (state badge, polled) and an abort path,
      plus an independent `anticogging_enabled` toggle (§4 above).
- [x] All thresholds/gain multipliers are named `config/board_constants.py`
      settings, editable per-run from the GUI, not buried literals (§3/§4).
- [x] `docs/progress.md` (this section) + `docs/decisions.md` updated.
- [ ] **Not yet triggered against real hardware** — deliberately not done
      this session despite a real board being connected (see
      docs/decisions.md); needs a supervised session with Ivan present,
      same as the rest of this project's motor-energizing actions.

---

# DC bus overvoltage ramp fix — Train mode hard-pull trips, 5 August 2026

- [x] **Bug diagnosed and fixed:** hard/fast cable pulls in Train mode were
      spiking vbus toward the 25V overvoltage trip and faulting, even with a
      correctly-valued brake resistor wired in. Root cause:
      `odrv0.config.enable_dc_bus_overvoltage_ramp` was `False` (firmware
      default) — the DC bus overvoltage ramp (drives brake resistor duty
      directly off measured vbus, distinct from the primary current-based
      regen logic tied to `max_regen_current`) was inactive, so the resistor
      only ever reacted to sustained regen current, not fast voltage
      transients. Full root-cause writeup in `docs/decisions.md` ("DC bus
      overvoltage ramp fix" entry).
- [x] **Fix applied and verified live:** `enable_dc_bus_overvoltage_ramp =
      True`, `dc_bus_overvoltage_ramp_start = 24.0`,
      `dc_bus_overvoltage_ramp_end = 25.0`. Hard pull in Train mode now stays
      ~23.6V, no fault (previously spiked toward trip). Confirmed persistent
      across a full DC bus power cycle — `save_configuration()` via Freddy's
      Apply & Save is working correctly on this board for this path.
- [x] **`dc_bus_overvoltage_trip_level` raised to 27V** — a deliberate
      decision distinct from the ramp fix itself, superseding the prior 25V
      bench-only value.
- [x] **Brake resistor wattage rating now known: 100W** (two spare resistors
      wired in parallel, `BRAKE_RESISTANCE` updated 2.0 → 2.35 Ω) — resolves
      the wattage-unknown half of open item #4 (project plan).
- [x] Wired into `config/board_constants.py` (updated `BRAKE_RESISTANCE`/
      `DC_BUS_OVERVOLTAGE_TRIP_LEVEL`, new
      `ENABLE_DC_BUS_OVERVOLTAGE_RAMP`/`DC_BUS_OVERVOLTAGE_RAMP_START`/
      `DC_BUS_OVERVOLTAGE_RAMP_END`, all exposed via
      `GET /api/board-constants`) and `config/odrive_config.py`'s static
      config section (matching literal assignments), so a fresh board
      bring-up or post-`erase_configuration()` re-run reproduces this fix
      automatically rather than relying on the live board's current flash
      state.
- [ ] **Thermal margin under sustained real training load — NOT yet
      verified.** With the ramp enabled and the PSU dial turned up to ~25V
      with the motor idle, the resistor was observed to get uncomfortably
      hot within seconds during a real-load test. Despite the now-confirmed
      100W rating, extended/hard sessions have not been run yet. Do not run
      extended/hard training sessions until this is checked — open item #4
      stays open for this half.

---

# Sidebar Homing split, live-tunable Testing tab, Setup tab, torque/force calibration — 5 August 2026

Requested as a single 7-item list (numbered 1/2/4/5/6/7 in the original
message — no item 3), explicitly asking for a simple implementation reusing
existing patterns rather than new machinery.

## Item 1 — Sidebar: split "Go Home" into "Homing" + "Go Home"

- [x] `DeviceList.jsx`'s single "Go Home" button is now two: **Homing**
      (fresh re-home — reels in and latches a NEW home reference, no prior
      home required) and **Go Home** (unchanged — returns to the existing
      home, no re-latch). Both call the existing `exercise_mode.py`
      `_apply_home`/`_apply_go_home` actions (`homeExercise()`/
      `goHomeExercise()`); no backend changes needed.

## Item 2 — Testing tab rebuilt on Control tab's own Position mode

- [x] The session-1 Testing tab redesign (a dedicated `ExperimentMode` with
      a configure → confirm → energize → immutable-run flow) turned out too
      rigid in practice — the user wanted Control tab's Position-mode feel
      instead: change a field, hit Update, see the effect immediately, keep
      adjusting without stopping. Rather than adapting `ExperimentMode`,
      the Testing tab now drives Control's existing `mode: "position"`
      session directly.
- [x] **Deleted** the entire `core/experiments/` package,
      `backend/app/experiment_routes.py`, `frontend/src/api/experiments.js`,
      `frontend/src/hooks/useExperimentTelemetry.js`,
      `ExperimentConfigForm.jsx`, and their tests — net removal, not a
      parallel path. Confirmed via `grep -rn` across the whole repo that no
      references to any of it remain.
- [x] Rebuilt `TestingTab.jsx` + new `useTestingTelemetry.js`: Known Weight
      (kg, unchanged), **Move Distance** (relative to current position, m or
      turns — replaces the old absolute "Target Position from Home"), Move
      Velocity, and **Torque Limit** with a 3-way unit selector (Nm / N /
      kg). All four fields are editable while the session is running via an
      "Update" button, exactly like Control tab's Position mode.

## Item 4 — Safety guard fix: ExerciseMode wasn't respecting the Train guard toggles

- [x] **Bug:** "Session auto-stopped ... Safety stop" kept firing during
      Go Home/Homing/manual moves even after disabling the corresponding
      guard toggle in the Train tab. Root cause: `train_home_guard_enforced`/
      `train_max_extension_enforced` (`core/cable/state.py`) were only ever
      consulted by `TrainMode.tick()` — `ExerciseMode.tick()`'s own position
      guard was unconditional by original design ("always on" for the setup
      session), and the frontend's own text at the time said as much.
- [x] **Fix:** `ExerciseMode.tick()`'s guard now gates on the same two
      toggles, combined with OR — disabling *either* toggle turns the guard
      off entirely for Exercise-mode operations, rather than staying
      half-enforced. A deliberate simplification vs. `TrainMode`'s fully
      independent per-side gating (`check_runtime_guard_split`), flagged as
      such in code; revisit if per-side parity turns out to matter here too.
      Two new tests added (`test_exercise_mode.py`).

## Item 5 — New "Setup" tab

- [x] The Train tab's "Settings / Startup" block (Homing, Max-extension
      calibration, Spool calibration, guard toggles) moved — not
      redesigned — into a new top-level **Setup** tab, positioned between
      Configuration and Control. `TrainSettingsSection.jsx` +
      `SpoolGrowthCalibration.jsx` + `SpoolModelDiagnostics.jsx` moved via
      `git mv` (history preserved) into `components/tabs/setup/`, with a new
      thin `SetupTab.jsx` wrapper polling `/api/exercise/status`. Dropped the
      now-unneeded `trainSessionRunning` prop (no longer coupled to Train's
      own running state). Train tab now contains only training-related
      functionality.

## Items 6 & 7 — Torque/force calibration, with full developer visibility

- [x] New `core/cable/torque_calibration.py` (`TorqueCalibrationPoint`,
      `fit_linear`, `TorqueCalibration`) — corrects the fixed-
      `MOTOR_TORQUE_CONSTANT` torque estimate against experimentally
      recorded points (hang a known mass, record the torque it actually took
      to hold): 0 points → identity, 1 point → scale-only, 2+ points →
      ordinary least squares (scale + offset). Iterative and additive, not a
      one-shot automatic calibration — matches the user's explicit ask.
      Persisted to a new `config/torque_calibration.json` sidecar, same
      pattern as the existing spool-growth calibration.
- [x] Applied **everywhere** torque/force conversions already happen (same
      "everywhere, not just one tab" precedent as the earlier `r_eff`
      fix): `ExerciseMode`'s `estimated_force_n`, `TrainMode`'s and
      `ExerciseMode`'s force→torque commands, and all calibration-hold
      torques. New routes `POST /api/exercise/record_torque_calibration_point`
      / `clear_torque_calibration`.
- [x] **Full developer visibility (item 7):** `_cable_status_dict()` gained
      a `torque_model` block (scale, offset, equation string, every recorded
      point, the underlying `motor_torque_constant_nm_per_a`). New
      `TorqueModelDiagnostics.jsx` — collapsed-by-default "Developer
      diagnostics" panel, same convention as the spool-growth calibration's
      own panel — shows the fitted equation with numbers substituted in and
      a plain-text walkthrough of current → torque → force → mass.
- [x] Verified: full backend pytest suite green (410 passed at the time),
      `npx eslint`/`npm run build` clean.
- [ ] **Not yet verified against a real known mass on the bench** at the
      time this round shipped — see the follow-up round below, which used
      an actual bench screenshot (2 recorded points, 5kg/10kg) to check the
      math, and found a real bug in the process (sign handling — see below).

---

# Calibration coverage audit, resistance display unit (N/kg), torque sign fix — 5 August 2026

Follow-up to the round above, triggered by the user attaching a real bench
screenshot of the Testing tab mid-calibration (2 points recorded: 5kg → raw
-0.9456 Nm, 10kg → raw -4.6892 Nm; fitted model
`corrected = -0.511925 * raw + 1.284924`) and asking three things: (1) is
this calibration actually used everywhere in the app, (2) can resistance be
displayed/entered in kg instead of N, (3) why is torque sometimes negative
when it's presented as "resistance."

## Screenshot math check

- [x] Manually verified the fit against the two recorded points —
      `-0.511925 * -0.9456 + 1.284924 = 1.7690` (vs expected
      `5 * 9.81 * 0.0361 = 1.7707`) and the same for the 10kg point — the
      fit itself was arithmetically correct (2 points on a line fit
      exactly). The negative scale was the real problem (see below), not a
      fitting bug.

## Item 1 — Calibration coverage: Train/Testing had it, Control tab didn't

- [x] **Found:** `core/control/modes.py`'s generic `PositionMode`/
      `TorqueMode` (used directly by the Control tab, and — via the item-2
      redesign above — by the Testing tab too) have no `CableState`
      awareness at all. The Testing tab already converts client-side before
      sending (documented in its own code), but the **Control tab did not**
      — its "Torque (est.)" stat and its Torque-mode/Position-mode-Torque-
      Limit targets went straight to/from raw motor-constant Nm, bypassing
      the calibrated model entirely. Train/Exercise modes were already
      correct (server-side, both directions) from the round above.
- [x] **Fixed:** `useControlTelemetry.js` now also polls
      `/api/exercise/status` for the `cable` calibration snapshot (same
      pattern `useTestingTelemetry.js` already used) and stamps every
      sample with a calibrated `torque_est_corrected` field. `ControlTab.jsx`
      displays the calibrated value by default (raw kept as an off-by-default
      secondary chart line), and converts both the Torque-mode target and
      the Position-mode Torque Limit through the calibration's inverse
      correction before sending — calibration is now the single source of
      truth everywhere in the app that reasons about torque/force.

## Item 2 — Resistance display unit preference (N vs kg)

- [x] New persisted `CableState` setting, `resistance_display_unit_kg`
      (default `False` = Newtons), same `_PERSISTED_DEFAULTS`/
      `set_train_settings()` mechanism as the guard toggles — set via a new
      toggle in the **Setup tab** ("Display resistance in kilograms"),
      surfaced through both `/api/train/update_settings` and
      `_cable_status_dict()` (so Control/Testing can read it too, though
      only the Train tab's profile builder consumes it so far).
- [x] `TrainProfileEditor.jsx`'s resistance-profile builder now shows/
      accepts every force field (constant/linear/bell shapes, the live
      preview chart) in the selected unit — conversion happens only at this
      component's own input/output boundary (`buildProfilePayload`/
      `segmentsFromPayload`/the preview chart's data mapping); the wire
      format and `core/cable/train_profiles.py` are unchanged, always
      Newtons. Deliberately **not** extended to `TrainPositionChart.jsx`
      (the separate Planned-vs-Actual diagnostic overlay, which already has
      its own manual per-curve scale-factor controls — a developer view,
      out of scope for this user-facing preference) or to the Testing tab's
      existing independent Nm/N/kg Torque Limit selector (a different,
      already-flexible per-field control, not this global preference).

## Item 3 — Torque sign: a real calibration-logic bug, not just display

- [x] **Bug found:** `core/cable/torque_calibration.py`'s `fit_linear` fit
      the SIGNED `raw_torque_nm` against the always-positive
      `expected_torque_nm` (a known weight is never negative). For this
      bench's data (both calibration holds recorded a negative raw
      reading), that produced an exact-fitting but physically nonsensical
      negative `scale` — it happened to reproduce both points, but would
      have silently flipped sign on any raw reading in the other direction
      (a different exercise, the other side of a hold). This is exactly
      what produced the "-0.7 Nm for a 5kg equivalent" symptom the user
      noticed in the Testing tab's Torque Limit field: `scale` was negative,
      so converting a positive real-world torque limit back to a raw
      command came out negative.
- [x] **Fixed at the conversion-logic level, not just display:** `fit_linear`
      now fits against `|raw_torque_nm|` (magnitude) vs `expected_torque_nm`
      (also magnitude) — `scale`/`offset` now describe how big the torque
      really is, never which way it's pointing. `corrected_torque_nm()`/
      `raw_torque_nm_for_corrected()` split the sign off before correcting
      the magnitude and reapply it unchanged afterward, so direction (still
      meaningful for control/debugging) is fully preserved everywhere it's
      needed. Mirrored exactly in `frontend/src/utils/cableGeometry.js`.
- [x] **Display fix on top:** the Testing tab's main "Measured torque"/
      "Measured force" stats (the user-facing "how much resistance" numbers)
      now show `Math.abs(...)` — sign is direction, not resistance
      magnitude, and resistance itself isn't negative. Left signed in the
      Developer diagnostics panel and the calibration points table (the
      raw, as-recorded measurement is exactly what belongs there).
      `TorqueModelDiagnostics.jsx`'s equation walkthrough updated to
      describe the sign/magnitude split explicitly.
- [x] New tests: `core/tests/test_torque_calibration.py` (magnitude-fit
      recovers a positive scale from the real negative-raw bench data;
      sign-preservation and zero/near-zero edge cases for both correction
      directions) and matching cases in `cableGeometry.test.js`.

## Verified

- [x] Backend: `.venv/bin/python -m pytest core/tests -q` — 415 passed.
- [x] Frontend: `npx vitest run` — 82 passed, 2 skipped (unchanged
      baseline); `npx eslint src/` — clean (one pre-existing, unrelated
      warning in `AxisTelemetryCharts.jsx`, part of the user's own
      in-progress work, untouched here); `npm run build` — succeeds.
- [ ] **Not yet re-verified on the bench with the sign fix applied** — the
      screenshot that prompted this round predates the fix. The math above
      was checked by hand against that screenshot's numbers, but a fresh
      calibration run (with the corrected model) and a check of Control
      tab's now-calibrated Torque display/targets on real hardware are
      still open for the next bench session.

---

# Repetitive testing sub-tab, adjustable settle tolerance — 17 August 2026

Built ahead of upcoming endurance/brake-resistor thermal testing (open
items #2/#3, v1.9 §6): a way to run a defined sequence of position-mode
moves a chosen number of times without babysitting Configure Move's single
Start/Update button per rep.

## Item 1 — Repetitive testing sub-tab

- [x] New `RepetitiveTesting.jsx`, added as a second `TabPanel` inside a
      `Tabs` wrapper now around the Testing tab's "Configure move" card
      (`TestingTab.jsx`). Configure move's own content/behavior is
      byte-for-byte unchanged, just moved one level deeper into the first
      panel.
- [x] Move list (add/remove rows): each row has its own Move Distance
      (m/turns), Move Velocity, and Torque Limit (Nm/N/kg) — same field
      set and conversions as Configure Move, minus Known Weight (not a
      calibration workflow here).
- [x] Repetitions count, a user-adjustable Settle tolerance (turns,
      default 0.02 — see Item 2), and Start / Pause / Resume / Stop
      controls with a live "Repetition X/Y — Move A/B" readout.
- [x] Settle detection is client-side (no backend "move finished" signal
      exists — confirmed nothing in `core/control/modes.py` or
      `core/hardware/odrive_hw.py` exposes `trajectory_done`): live
      position within tolerance of the commanded target AND velocity below
      a threshold, sustained 3 consecutive polls, 20s per-move timeout as
      a safety net.
- [x] Pause stops the motor immediately (`stopControlSession()`) and
      remembers the current rep/move so Resume re-issues the same move and
      continues; Stop resets the whole sequence.

## Item 2 — Settle tolerance made adjustable

- [x] The position-tolerance half of "settled" was a fixed 0.02-turn
      constant in the first version; a tight tolerance can leave a real
      rig chasing the last fraction of a turn before a move is allowed to
      advance. Now a "Settle tolerance" input (turns), editable while
      idle, feeding the same settle check directly.
- [x] Velocity threshold isn't a separate field — it scales with the same
      input at the ratio the two were originally fixed at (1.5×), so one
      control loosens both halves of "settled" together.

## Item 3 — Bug found via an actual browser run

- [x] **Bug**: the "stopped externally" safety net (catches the top-level
      STOP button, another tab, or a hardware auto-stop) originally lived
      in its own `useEffect([running, busy])`, reading a `running` prop
      that only updates on the parent's ~150ms poll cycle. That lagged
      just behind this component's own start/resume call finishing, so
      the effect fired inside the gap and misread the sequence's own
      just-started session as an external stop — every run halted
      immediately after Start.
- [x] **Fixed**: folded the same check into the effect already gated on a
      *new* telemetry sample arriving (`status?.latest_sample?.t`
      changing) rather than its own independent trigger — guarantees
      `status` is at least as fresh as the render that caused it.
- [x] **Caught by**: launching the mock backend + frontend and driving it
      with a headless Chrome instance (Playwright against the system
      Chrome install, no project dependency added) — not by lint, the
      build, or the existing test suite, none of which exercise real
      telemetry timing.

## Item 4 — Mock-fidelity gap found while verifying a full run

- [x] **Found**: `ODRIVE_MOCK=1`'s `encoder.pos_estimate`
      (`backend/app/mock_odrive.py`) is driven purely by wall-clock time
      (`2.0 * sin(t * 0.5)`) — it never reads back
      `axis.controller.input_pos`, so it doesn't track a commanded
      position target at all. "Wait for position to reach target" (this
      feature's whole settle-detection basis) can never reliably succeed
      against the mock.
- [x] **Scoped correctly**: confirmed against the mock's actual source,
      not inferred from behavior alone. Pre-existing, not introduced here,
      and not specific to this feature (the same check against Configure
      Move's own moves would hit it too). No workaround exists in the mock
      today — verifying settle/advance behavior end-to-end requires real
      hardware.

## Item 5 — Brake-resistor question, answered from the actual regen path

- [x] Researched (not asked to implement) whether repeated automated
      lifting/lowering — no human pulling involved — can exercise the
      brake resistor at all, ahead of the project owner's planned
      endurance test. Confirmed from the 5 August DC-bus-overvoltage-ramp
      work (`core/hardware/odrive_hw.py`, `config/board_constants.py`):
      the brake resistor is driven by two independent mechanisms, a
      current-based path (`max_regen_current`, reacts to *sustained* regen
      current) and a voltage-ramp path (reacts to *fast* transients,
      added because a hard pull could outrun the current-based path
      alone). Repeated automated up/down motion under a hung weight
      generates sustained regenerative current during the lowering phase
      exactly like a real workout would — it exercises the current-based
      path with no yank required. Write-up for hands-on use in
      `docs/testing_tab_experiment_guide.md`.

## Verified

- [x] Backend: `.venv/bin/python -m pytest core/tests -q` — 415 passed
      (unchanged; no backend files touched this round).
- [x] Frontend: `npx vitest run` — 79 passed, 2 skipped (unchanged
      baseline); `npx eslint src/` — clean; `npm run build` — succeeds.
- [x] Live-verified against `ODRIVE_MOCK=1` in a real browser (Playwright
      driving the system Chrome install): sub-tab renders, Configure Move
      unchanged, move list add/remove works, Start/Pause/Resume/Stop cycle
      works end-to-end, Settle tolerance field renders/validates/disables
      correctly while running. The one thing NOT verified against the mock
      is a sequence completing *naturally* (advancing move-to-move via
      real settle detection) — see Item 4, a mock limitation, not a gap in
      this testing pass.
- [ ] **Not yet run on real hardware.** Everything above is mock-verified
      only; the settle/advance behavior this whole feature depends on
      needs a real bench session to confirm.

---

# Direction-aware torque calibration, run-based data collection — 21 August 2026

Prompted by a real bench observation: the raw torque estimate commanded to
hold a known weight was ~110 Nm while accelerating up, ~105 settling, ~100
static, then noticeably lower moving down. The old workflow (`items 6 & 7`
above, 5 August 2026) only ever recorded a single static-hold snapshot —
right for none of the regimes that actually matter during a rep, since
friction opposes whichever way the motor is turning (adds going up,
subtracts going down). User's own proposal: keep the existing rep-based
Testing tab tests exactly as they are, and derive calibration points from
that telemetry afterward instead of a manual static hold, at a few known
weights (5/10/15 kg).

## Item 1 — `TorqueCalibration` becomes direction-aware

- [x] `core/cable/torque_calibration.py`: `TorqueCalibrationPoint` gained a
      required `direction` field (`"up"`/`"down"`). `TorqueCalibration` now
      fits TWO lines (one per direction) instead of one, selected at
      correction time by the CABLE-frame velocity's sign
      (`corrected_torque_nm`/`raw_torque_nm_for_corrected` both gained a
      `cable_velocity_turns_s` parameter). Near-zero velocity (isometric
      holds, calibration holds) falls back to a "static blend": the average
      of both directions' scale, with offset forced to 0 — Coulomb friction
      is direction-indeterminate exactly at zero velocity, so applying
      either direction's signed offset while not moving would be a guess.
- [x] `describe()` now returns a `directions: {up, down}` breakdown plus
      the static blend, AND still mirrors flat top-level `scale`/`offset`/
      `equation`/`points` (= the static blend) for every existing caller
      that only ever wanted a single no-direction-context conversion
      (`ControlTab.jsx`, `useControlTelemetry.js`,
      `useTestingTelemetry.js`, `RepetitiveTesting.jsx`'s torque-limit
      unit conversion) — none of those needed to change.
- [x] Every live call site updated to pass its own velocity:
      `core/control/modes.py`, `core/cable/train_mode.py`,
      `core/cable/exercise_mode.py` (display/estimate sites use
      `CABLE_SIGN * sample.velocity`; the three static calibration-hold
      command sites — max-extension/spool-growth calibration holds — pass
      no velocity at all, correctly landing on the static blend since
      they're deliberately not-moving holds).

## Item 2 — New `core/cable/torque_calibration_run.py`

- [x] Pure-math module (same "zero project-specific imports" convention as
      `geometry.py`/`torque_calibration.py`) that turns one run's ordered
      telemetry samples into up to two calibration points: splits into
      contiguous same-direction "rep legs" above a moving-velocity
      threshold, keeps only each leg's steady-state plateau (samples within
      90% of that leg's own peak |velocity| — the cruise portion of the
      trapezoidal move profile, excluding accel/decel transients), averages
      each leg's own raw torque and r_eff first, then averages those
      per-rep numbers again across every leg in that direction — so one
      long/noisy leg can't outweigh a short one.

## Item 3 — Backend: analyze-then-insert, not auto-calibrate

- [x] Matches the user's explicit ask ("the tool doesn't automatically
      calibrate it, it just provides the repetitions, then we make sure we
      have the correct data, then we insert it"): new
      `POST /api/exercise/analyze_torque_calibration_run { known_weight_kg }`
      reads back the CSV log of the most recently STOPPED run (new
      `ControlSession._last_log_path`/`status()["last_log_path"]`, since
      the existing `log_path` goes back to `None` once a session ends) and
      returns a read-only preview (per direction: point, rep count, every
      per-rep raw torque value) — nothing is saved. `record_torque_
      calibration_point` (existing route) now takes explicit
      `known_weight_kg`/`raw_torque_nm`/`r_eff_m`/`direction` (normally
      copied straight from one direction's preview) instead of grabbing a
      live snapshot — the "insert" step.
- [x] `core/cable/state.py`'s sidecar loader tolerates old-format points
      (no `direction` key, from the pre-21-Aug static-hold era): skipped
      individually with a log warning rather than failing the whole file,
      since they can't be migrated to a model that has no static line
      anymore.

## Item 4 — Frontend

- [x] `TestingTab.jsx`'s calibration card rewritten for analyze → review →
      insert (per direction, with an "Inserted" state once committed);
      `TorqueModelDiagnostics.jsx`'s developer panel now shows both
      directions' fitted equations/points plus the static blend actually
      in effect. `api/exercise.js` gained `analyzeTorqueCalibrationRun`;
      `recordTorqueCalibrationPoint`'s signature changed to the explicit
      point shape.

## Verified

- [x] Backend: `.venv/bin/python -m pytest core/tests -q` — 428 passed
      (28 net new: full rewrite of `test_torque_calibration.py` for the
      per-direction API, new `test_torque_calibration_run.py`, 3 pre-
      existing call sites in `test_exercise_mode.py`/`test_train_mode.py`
      updated to the new signatures).
- [x] Frontend: `npx vitest run` — 79 passed, 2 skipped (unchanged);
      `npx eslint` — clean.
- [x] End-to-end route smoke test (Flask test client, in-process, a
      synthetic CSV shaped like a real trapezoidal "up" rep leg): analyze
      correctly extracted a plateau-only point with the transient samples
      excluded from the average, insert correctly persisted it and refit
      the "up" line, `down` correctly came back `null` (no down-direction
      samples in the synthetic run).
- [ ] **Not yet run on real hardware** — the whole point of this change was
      a real-bench observation, but re-verifying against real reps (not
      just the synthetic smoke test above) still needs a bench session.
      **Also**: this rig already had 6 real calibration points on disk
      (`config/torque_calibration.json`, 5/10/15 kg from earlier bench
      work) — those are old-format (no `direction`) and will be silently
      skipped on next backend start per Item 3 above, reverting live
      torque correction to identity until recollected under the new
      workflow. Flagging explicitly since it's a real behavior change to
      already-collected bench data, not just new-code coverage.
