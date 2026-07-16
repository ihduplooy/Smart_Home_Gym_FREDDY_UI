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

- [ ] Create target top-level layout: `backend/`, `frontend/`, `core/` (placeholder +
      README stub with the GUI/core split rule), `config/`, `docs/`, README.md
- [ ] Strip multi-axis UI (axis1), hard-code axis0 in frontend; keep backend
      parameterisation if removing it is invasive
- [ ] Strip multi-device UI; leave backend discovery returning the first device
- [ ] Strip Windows packaging: `build.bat`, PyInstaller/tray-exe machinery,
      anything under `backend/dist`, `install.bat`
- [ ] Decide fate of `odrive_docs_local/` (or `odrive_api_references/`) — keep only
      if Inspector actually depends on it for tooltips, else replace with README link
- [ ] Check for v0.5.6-only property handling that would error against a v0.5.1 board;
      log any found in decisions.md (don't deep-dive without hardware)
- [ ] Verify/consolidate ODrive access to a single choke point per spec §6 (prep for
      step d's grep check)

## (c) Rebrand + wizard defaults (spec §4 rebranding scope, §5 constants)

- [ ] App title/header rebranded to "Smart Gym Control" everywhere (frontend title,
      package.json name, README)
- [ ] Strip upstream release/version badges from README; write new project README
      (context paragraph + dev-mode run instructions)
- [ ] No UI restyling (explicitly out of scope — functionality only)
- [ ] Create `config/board_constants.py` — single source of truth for firmware version,
      motor (pole_pairs=15, MOTOR_TYPE_HIGH_CURRENT), encoder (AS5047P, SPI ABS,
      abs_spi_cs_gpio_pin=7), axis0-only + axis1 CAN node id=63, `# TODO(2A)` on the
      torque-mode velocity-limit constant
- [ ] Move `odrive_config_1B.py` into `config/odrive_config.py` verbatim
- [ ] Pre-load config wizard defaults from the 1B script's values; verify generated
      command preview matches 1B script's settings
- [ ] Ship one preset generated from the 1B script (presets import/export kept)
- [ ] Backend warns (not crashes) if connected board reports firmware != v0.5.1

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
