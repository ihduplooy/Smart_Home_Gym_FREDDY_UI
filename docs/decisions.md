# Decisions log — what was stripped/changed from upstream and why

Per spec §8: 0.5.1-incompatibilities found during the trim are logged here rather than
deeply investigated without hardware. This file is append-only during Session 1;
newest entries at the bottom.

## Path discrepancy (pre-work note)

- Spec §"Working directory" refers to the 1B script as `Developer/odrive_config_1B.py`.
  The actual file on disk is `Phase 1/odrive_config_1B.py` — there is no `Developer/`
  subfolder anywhere in the project. Treated as the same file (only one 1B script
  exists, contents match spec's description exactly: hoverboard motor, 15 pole pairs,
  AS5047P SPI CS pin 7). No action needed beyond noting it here.

## Upstream has moved far past the spec's "repo facts" snapshot

- Spec §2 describes upstream (verified "16 Jul 2026") as roughly matching the
  `lithium_1.4.9` tag (actual date 2025-07-26): heavier Windows/tray packaging
  (pystray, PyInstaller, `.spec` file all in `backend/requirements.txt`), no built-in
  mock mode, presumably richer multi-axis/multi-device UI.
- The actual current upstream `main` branch (commit `d905206`, version tag
  `Titanium_2.0.0`, dated 2026-06-29 — 11 months newer) has already been substantially
  refactored by the upstream author: a single generic property-tree backend (no
  per-axis/per-device routes at all), a built-in `ODRIVE_MOCK`/`mock_odrive.py` mock
  device seeded from the API-reference JSON, and firmware-line-aware (0.5.x vs 0.6.x)
  property resolution in both backend and frontend. Windows packaging
  (pystray/PyInstaller) was dropped from `backend/requirements.txt` itself, though the
  packaging *scaffolding* (`.spec` file, `run_standalone.py`, `lifecycle.py`, build
  scripts, CI workflow) was still present in the tree.
- Decision: forked from actual upstream `main` (not an older tag), per spec's own
  instruction to explore actual layout rather than trust the write-up. This
  significantly reduced the trim workload versus what the spec anticipated (no
  per-axis/per-device backend routes to consolidate — already a single choke point),
  but the concrete file/reference list in spec §4 no longer matches 1:1 — see the
  per-item entries below for what was actually found and removed.

## Windows/standalone packaging removed

Removed (dev-mode-on-macOS is the only deployment target for the whole skripsie, per
spec §4): `build.bat`, `build.sh`, `install.bat`, `install.sh`, `backend/odrive_gui.spec`,
`backend/run_standalone.py`, `backend/requirements-build.txt`, `backend/servo.ico`,
`backend/app/lifecycle.py`, `backend/app/paths.py` (PyInstaller-bundle/static-frontend
lookup), `.github/workflows/build.yml` (three-OS standalone-exe CI build — no CI/CD
needed for a personal one-way fork), `.github/copilot-instructions.md` (upstream's own
AI-agent guidance doc — described a Linux dev environment, dual 0.5.x/0.6.x support
as a project *goal*, and the now-deleted install scripts; would actively mislead future
AI-assisted work in this fork).

Also removed the frontend UI wired to that packaging: `/api/heartbeat` and
`/api/shutdown` Flask routes (`backend/app/app.py`), the static-frontend-serving route
block (also `app.py`, depended on the deleted `paths.py`), `QuitAppButton.jsx` (kills
the Flask process — a standalone-app affordance, not useful in dev where you just
Ctrl+C the terminal), `UpdateChecker.jsx` (GitHub-releases version-check widget;
hardcoded `MoonLighTingPY/odrive3.6_web_gui` as the upstream repo to check against,
meaningless for a diverged one-way fork), and the now-dead `isStandalone`/`heartbeat`/
`shutdownApp` helpers + `HeartbeatManager` in `frontend/src/api/backend.js` /
`frontend/src/App.jsx`.

## odrive Python package pinned to match board firmware

`backend/requirements.txt` pinned `odrive==0.6.10.post0` upstream (their default target
is now 0.6.x firmware). Our board runs firmware v0.5.1 only (per spec §0, and per
`odrive_config_1B.py`'s own header: "Python: odrive==0.5.1.post0 (must match
firmware)"). Changed the pin to `odrive==0.5.1.post0`. Verified: installs cleanly in
the pyenv 3.9.18 venv on this Mac, and the backend still starts and serves
`/api/devices` cleanly with it.

## Real bug found + fixed: Apple Silicon libusb resolution (not a v0.5.1 issue, a macOS-ARM issue)

While re-verifying the no-device state after the requirements.txt pin change, found
that every `/api/devices` poll logged an uncaught `usb.core.NoBackendError` traceback
from a background discovery thread (spawned internally by the `fibre` library's USB
transport, not something the existing `except Exception` in `_find_any()` can catch
since it's a different thread). Root cause: this Mac has a stale x86_64
`libusb-1.0.dylib` at `/usr/local/lib` (leftover from an old Intel/Rosetta Homebrew
install) that `ctypes.util.find_library('usb-1.0')` returns *before* ever reaching the
correct arm64 build Homebrew actually installs at `/opt/homebrew/lib` — pyusb 1.3.1
does have an Apple-Silicon fallback for exactly this, but it only triggers when
`find_library` returns nothing, and here it returns a (wrong-arch, unloadable) hit.
Fixed in `backend/app/device_manager.py` (`_ensure_macos_libusb_path()`, called from
`_find_any()` before the lazy `import odrive`): prepends `/opt/homebrew/lib` to
`DYLD_LIBRARY_PATH` in-process when running on `darwin`/`arm64`, which
`ctypes.util.find_library` reads at call time. Verified: 3 consecutive `/api/devices`
polls after the fix show clean `200` responses with zero backend-log tracebacks
(previously every poll threw). This is a real, confirmed environment fix (verified by
directly reproducing and fixing the exception), not speculative — logged here rather
than in the "don't investigate without hardware" bucket since it required no hardware,
only the "no device" path, to reproduce and fix. Did not touch the stray
`/usr/local/lib/libusb-1.0.dylib` itself — that's outside the project and could belong
to other software on this machine.

## Multi-axis UI stripped

Removed: the axis0/1 segmented toggle (`AxisSelector.jsx` + its two render call
sites), the "Apply to both axes" checkbox in the config wizard's Apply step (and the
matching duplicate-to-both-axes command-expansion logic in `useConfigWizard.js` +
"both axes" branch in `ConfirmationModal.jsx`), and axis1's branch in the Inspector's
property tree (`apiReference.js`'s tree builder now only ever constructs an `axis0`
section). Reason: axis1 on this board is a ghost node (CAN ID 63 from Phase 2B) —
only axis0 is ever driven, per spec §5.

Deliberately kept: `useMotorControl.js`'s `saveAndReboot` still idles axis1 alongside
axis0 before `save_configuration` (a real ODrive firmware constraint: all axes must be
idle before that call succeeds) — harmless on an unused axis, not worth the risk to
remove for zero user-facing benefit. Also kept all the `selectedAxis`-threading
plumbing in hooks (`useMotorControl`, `useCalibration`, `useConfigWizard`, etc.) — it
now permanently resolves to axis0 since there's no UI left to change it, exactly the
"keep the backend parameterisation if removing it is invasive" call the spec allows.

## Multi-device UI stripped

The backend never actually supported multiple simultaneous devices —
`device_manager.discover_and_index()` clears its index and inserts at most the one
handle `odrive.find_any()` returns, so "multi-device" was frontend-only scaffolding for
a case the backend couldn't produce. Simplified `DeviceList.jsx` from a
`.map()`-rendered card grid (built for N devices, always showing 0 or 1) to directly
rendering the single found device or a "no device" alert. Renamed the sidebar heading
from "ODrive Devices" to "ODrive Device" to match.
