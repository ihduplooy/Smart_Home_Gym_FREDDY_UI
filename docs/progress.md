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

- [ ] `SPOOL_RADIUS_M` placeholder + force↔torque conversion lives in exactly one
      function (`core/profiles/units.py`).
- [ ] `ECCENTRIC_OVERLOAD_RATIO_DEFAULT = 1.35`.
- [ ] Phase-detector tuning constants (`PHASE_VEL_THRESHOLD_TURNS_S`,
      `PHASE_HYSTERESIS_TURNS_S`, `REP_EWMA_ALPHA`, `REP_PROXIMITY_TURNS`), grouped
      under a "profile layer tuning" comment block, all `# TODO(2A)`.

## §5 — `core/profiles/` package

- [ ] Package layout created per §5 (`__init__.py`, `units.py`, `detectors.py`,
      `base.py`, `constant.py`, `bell_curve.py`, `overload.py`, `vbt.py`).
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

- [ ] `GET /api/profiles` — registry-driven list (name, parameter schema, is-wrapper
      flag).
- [ ] `POST /api/control/start` extended for `mode: "profile"` (+ optional
      `overload`), existing velocity/torque shapes untouched.
- [ ] `status()`/telemetry gain `phase` + `rep_count` when a profile runs.
- [ ] Frontend Profiles tab: registry-driven picker, schema-driven param inputs,
      overload toggle+ratio, Sim/Real banner, STOP, live phase badge + rep count,
      stub-math notice, reuses `useControlTelemetry`.

## §8 — Verification (all against sim)

- [ ] 1. Detector unit tests: 3-rep synthetic sequence → correct phase cycle +
      `rep_count == 3`; noise-at-threshold → zero flicker; no-CONCENTRIC → no reps.
- [ ] 2. Profile unit tests: constant exact `force*radius`; bell-curve peak/edges;
      OverloadWrapper multiplies only in target phase (both configs, never in
      holds); VBT steps down/up only on rep boundaries; `compute_torque` raising →
      session auto-stops.
- [ ] 3. End-to-end against sim: 5-line-snippet ConstantProfile run (no Flask), CSV
      gains phase/rep columns; API + headless-Chrome Profiles tab pass (constant +
      overload, phase badge changes, stop cleanly, zero console errors).
- [ ] 4. Regression: Control tab unchanged flows pass; all 6 tabs console-clean
      (`ODRIVE_MOCK=1`); eslint clean; vitest green; full pytest green (35 existing +
      new).
- [ ] 5. Choke-point audit: still exactly 2 `find_any` sites + the 1B script.

## §9 — Definition of Done

- [ ] 1. `core/profiles/` exists per §5, importable with no side effects, pytest
      green.
- [ ] 2. Phase detector + rep counter pass synthetic-sequence tests incl. no-flicker
      hysteresis.
- [ ] 3. All four stubs runnable end-to-end against sim through `ProfileMode`;
      OverloadWrapper composes over any profile and either moving phase.
- [ ] 4. Profiles tab works: registry-driven picker, schema-driven params, overload
      toggle, live phase badge + rep count, stub-math notice, STOP.
- [ ] 5. `core/README.md` gains a second snippet: ConstantProfile session against
      sim, no Flask.
- [ ] 6. Safety behaviours verified to cover ProfileMode (incl. `compute_torque`
      raising).
- [ ] 7. CSV extension in place; Session-2 modes' logs unaffected apart from the two
      new (empty) columns.
- [ ] 8. Regression + audits per §8.4–8.5; progress.md + decisions.md updated.
