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

- [ ] Re-verify "no device connected" state still works after all changes (no crash
      loop, no unhandled console errors)
- [ ] DoD 1: `npm run dev` + backend start work in pyenv 3.9.18 env; GUI loads at
      localhost with project branding
- [ ] DoD 2: no-ODrive state clean (see above)
- [ ] DoD 3: config wizard opens pre-loaded with 1B values; command preview matches
- [ ] DoD 4: multi-axis/multi-device UI gone, no dead buttons
- [ ] DoD 5: noted as deferred to Phase 2A (real-hardware verification) — nothing to
      do now beyond acknowledging it
- [ ] DoD 6: `docs/decisions.md` lists every stripped feature with a one-line reason
- [ ] DoD 7: `core/` placeholder exists with split rule written down
- [ ] §6 choke point: grep for `odrive.find_any` / direct fibre calls in backend —
      confirm exactly one call site
