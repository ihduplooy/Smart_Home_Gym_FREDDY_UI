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

## Removed odrive_api_references/ and scripts/ (regeneration tooling, unneeded)

Spec §4 asked to decide the fate of the (old-named) `odrive_docs_local/` doc mirror —
the actual current directory is `odrive_api_references/` (three .txt files, ~296K:
official ODrive API docs for 0.5.6 and 0.6.12, plus a changelog). Confirmed zero
runtime dependency: nothing in `frontend/src` or `backend/app` reads this directory.
Its only consumer is `scripts/generate_api_reference.py` (regenerates the runtime
`odriveApiReference0{5,6}x.json` files from these .txt docs when a new ODrive firmware
release ships) and `scripts/check_api_reference.py` (a coverage-gap sanity check for
that regeneration) — both purely manual dev tools, referenced only from README's own
"how to regenerate" instructions, not from CI or any test/build script.

Removed both `odrive_api_references/` and `scripts/`: this project is permanently
locked to firmware v0.5.1 (never upgrading — v0.5.6 breaks motor activation on this
board, per spec §0), so the capability to regenerate references against some future
ODrive release has no use here. The load-bearing runtime files themselves
(`frontend/src/utils/odriveApiReference05x.json` / `06x.json`, read directly by both
frontend and backend) are untouched — only the regeneration source/tooling is gone.
README's rebrand pass (step c) drops the now-dangling "regenerating the reference"
section accordingly.

## Rebranding

App title/header changed to "Smart Gym Control" everywhere (`frontend/index.html`
`<title>`, sidebar `<Heading>` in `App.jsx`). Left literal "ODrive" strings that
describe the connected *hardware* rather than upstream software branding
(`DeviceFooter`'s "Device: ODrive" value, the Inspector's "ODrive Properties"
heading) — those are accurate technical labels, not attribution to strip. Backend
`VERSION` constant (`backend/app/constants.py`) changed from upstream's
`Titanium_2.0.0` to `smart-gym-control-1.0.0` (this was only ever consumed by the
now-deleted `UpdateChecker`; the `/api/backend/version` route itself is harmless to
keep). `frontend/package.json` name/version updated to match (lockfile
regenerated). README fully rewritten: spec §0's project context, real repo layout,
dev-mode setup/run instructions, architecture notes — no upstream release badges, no
Windows/standalone instructions, no "Contributing"/star solicitation (this is a
personal one-way fork). Did not restyle the UI (explicitly out of scope per spec §4).

## Config wizard: pre-loaded with project defaults (spec §5)

Added `config/board_constants.py` — the single source of truth for every project-
specific constant (firmware version, motor, encoder, axis, bus limits), values taken
verbatim from `config/odrive_config.py` (the moved 1B script). Deliberately plain
data with zero dependency on the `odrive` package or any hardware, so it's safe to
import broadly (unlike `odrive_config.py` itself, which is a top-level script that
calls `odrive.find_any()` at import time — never import that module, only run it).

Wired into the backend:
- `GET /api/board-constants` (`backend/app/app.py`) serves `board_constants.as_dict()`
  — per spec §5, these values are never duplicated into frontend code; the frontend
  fetches them from this one route.
- `device_manager.serialize_device()` now calls `board_constants.check_firmware()`
  and attaches a `firmware_warning` string (or `null`) to every device's JSON, plus
  logs a backend warning — never raises. Verified against the mock device (which
  reports 0.5.6): warning fires correctly, connection still succeeds
  (`GET /api/devices` still 200s). Verified against a 0.5.1-matching board (also via
  mock, `ODRIVE_MOCK_FW=5`... note the mock's own revision is hardcoded to 6 for line
  5 — see below): the "no warning" path was exercised indirectly by confirming
  `check_firmware()` returns `None` when major/minor/revision all match via direct
  reasoning about the function, since the mock always reports revision 6 regardless
  of line and can't simulate an exact 0.5.1 match. Both branches of the function are
  simple equality checks; both are covered by code reading + the mismatch-path live
  test.
- `backend/start_backend.py` inserts the repo root onto `sys.path` so `config/` (a
  namespace package, no `__init__.py`, consistent with `backend/app` itself) is
  importable regardless of the process's working directory.

Wired into the frontend (`frontend/src/hooks/useConfigWizard.js`): on `pullConfig`,
`desired` is now seeded as `{ ...deviceSnapshot, ...expandValues(boardDefaults,
selectedAxis) }` — board-constant defaults take priority over the raw device
snapshot for the small, curated set of fields we have a project opinion on; every
other field (measured values, thermal limits, etc.) still shows the actual device
value. `frontend/src/utils/boardDefaults.js` holds only the *structural* mapping
(which `board_constants` key belongs at which template path) — the numeric values
themselves always come from the `GET /api/board-constants` fetch, never duplicated
into this file.

**Bug found and fixed during live verification**: the first version of this merge
put the device snapshot *after* the defaults (`{...defaults, ...snap}`), so any
property the mock/device reports *any* value for (which, for a mock or freshly-
erased board, is nearly every property — the mock seeds a type-appropriate 0/False
for its entire walked property surface) silently overwrote our defaults. Caught by
opening the Apply step with "Only changed parameters" off against the mock and
seeing `pole_pairs=7` / `abs_spi_cs_gpio_pin=0` instead of our `15`/`7`. Fixed by
flipping the spread order (`{...snap, ...defaults}`) — confirmed via the same
manual check afterward: all ~20 project fields now show the exact 1B-script values
(`pole_pairs=15`, `abs_spi_cs_gpio_pin=7`, `encoder.config.mode=257`, `cpr=16384`,
`control_mode=3`, `vel_limit=2`, bus limits `25/8/15/-3/0/2`, etc.) and three
previously-spurious validation warnings (CPR=0, vel_gain=0, vel_limit=0 — artifacts
of the un-seeded mock defaults) disappeared. This intentionally does *not* touch
`configDiff.js`'s "phantom command" bug-fix rule (never write a value for a field
whose device value is unknown *and* untouched) — that rule still applies to every
field we *don't* have a curated default for; we're only ever seeding our own small,
documented, project-specific set.

**Missing schema field, added**: `configSchema.js`'s encoder step had no field at
all for `abs_spi_cs_gpio_pin` — one of this project's most important constants (the
AS5047P's SPI chip-select pin). Without it, the value could never appear in the
wizard or its command preview no matter what defaults were injected. Added
`axis{n}.encoder.config.abs_spi_cs_gpio_pin` as a real field (confirmed present in
`odriveApiReference05x.json` as a `Uint16Property`).

**Mock fidelity fix**: the mock's line-5 (0.5.x) seed data didn't include
`axis{0,1}.config.can_node_id` at all (that path isn't in the auto-generated 0.5.x
reference JSON as its own scalar — see the CAN-schema fix above), so reading it
against the mock returned a non-scalar branch node, not `0`. Since the 1B script
relies on this exact flat property existing on the real board, added it explicitly
to `mock_odrive.py`'s `_SEED_BY_LINE[5]` (default `0` for both axes) so mock mode
matches confirmed real-hardware behaviour for this project.

## Shipped preset generated from the 1B script

Added a 4th factory preset to `frontend/src/utils/presets/factoryPresets.js`
("Smart Gym Cable — Hoverboard + AS5047P") containing every value above in the
existing preset JSON shape (template `axis{n}...` paths). Unlike the live
wizard-defaults injection, presets are static, exportable JSON snapshots by design
(matching how upstream's existing factory presets already work) — duplicating the
1B values into this one preset file is the correct, expected shape for "ship one
preset generated from the 1B script," not a violation of the single-source-of-truth
rule (which specifically targets the *live default-injection* mechanism, not
one-time preset generation).

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

## Real v0.5.1-incompatibility found + fixed: CAN Bus wizard fields

`frontend/src/utils/configSchema.js`'s Interface step had a "CAN Bus" group with
`axis{n}.config.can.node_id` and `axis{n}.config.can.heartbeat_rate_ms`. Checked both
against `frontend/src/utils/odriveApiReference05x.json`: `axis{n}.config.can` exists
there only as a non-scalar `ODrive.Axis.CanConfig` struct — there is no `node_id` or
`heartbeat_rate_ms` scalar leaf documented under it for 0.5.x (those paths are real on
0.6.x, per the 0.6.x reference JSON, which is where this schema entry was presumably
copied from). Effect on a real v0.5.1 board: reads back as unreadable/blank (handled
gracefully, no crash) but writes would silently no-op (backend catches the
`AttributeError` and reports a per-path error, doesn't crash) — a dead, misleading pair
of fields for our board.

Fixed the node ID field: `odrive_config_1B.py` (lines 178, 180) uses a **flat**
`axis{n}.config.can_node_id` — a real property on this exact board/firmware, straight
from the working 1B script, which is better evidence for this specific clone board than
an auto-generated reference JSON with incomplete struct coverage. Changed
`configSchema.js` to that path (confirmed safe: the wizard's form fields declare their
own `kind`/`unit` and don't require the path to appear in the reference JSON — only the
Inspector's dynamic tree-builder does that). This is also exactly the property the 1B
script uses to silence axis1 (`can_node_id = 63`, "Ghost Axis 1 fix", spec §5) — the
wizard can now actually apply that setting once a device is connected.

Dropped the heartbeat-rate field entirely rather than fix it: no confirmed 0.5.x
equivalent exists in the reference data, and it isn't part of this project's needs (the
1B script never sets one; it only sets `can_node_id` and calls
`odrv0.can.set_baud_rate(500000)` — a *command*, not a writable property, so it isn't
representable in this property-write-based schema at all and is out of scope for the
wizard; it'd be set via the console tab or `config/odrive_config.py` directly in Phase
2A). Not fixed (out of scope, doesn't affect this board): the 0.6.x path itself has a
second, independent bug — `configSchema.js` calls the field `heartbeat_rate_ms` but the
real 0.6.x property is `heartbeat_msg_rate_ms` — logged here per spec §8 rather than
fixed, since we never connect a 0.6.x device to this board.

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
