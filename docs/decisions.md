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

---

# Session 2 — core/, control modes, Control tab

Per the Session 2 build spec (`Phase 1/1C_build_spec_session2.md`). Continues the
append-only log above; entries below are new for this session.

## Torque constant added to board_constants.py (open item #2)

The spec's `TelemetrySample.torque_est` contract needs a torque constant
(`torque_constant * current_iq`), and none existed in `board_constants.py` (the 1B
script never sets one — it's a runtime-control value, not a calibration parameter).
Added `MOTOR_TORQUE_CONSTANT = 0.06` (Nm/A) as an explicit placeholder — a rough
hoverboard-hub-motor ballpark, not measured on this unit — with a `# TODO(2A)`
pointing at motor characterisation (open item #2). Used by both `sim_hw.py` (to derive
`current_iq` back from applied torque) and `odrive_hw.py` (to compute `torque_est` from
the real `Iq_measured`, and to convert the current limit into a torque clamp for
`set_torque_target`).

## macOS libusb fix extracted to a shared core/ helper

Spec §5.1 requires the Apple-Silicon `DYLD_LIBRARY_PATH` fix (added in Session 1 to
`device_manager.py`) to be shared between `device_manager.py` and the new
`odrive_hw.py`, not copy-pasted. Extracted verbatim into
`core/hardware/_macos_usb.py::ensure_macos_libusb_path()`; `device_manager.py` now
imports and calls it instead of its own private copy. This is the one case where
`backend/` imports a leaf util *from* `core/` — allowed per spec §5.1 ("backend
importing a leaf util from core/ is allowed, core importing backend is not"); the file
itself has zero dependencies on anything project-side, so the import direction rule
isn't actually tested by it either way.

## Two-connection conflict — flagged, not solved (spec §5.1, §11)

`core/hardware/odrive_hw.py` now has its own `odrive.find_any()` call site, independent
of `backend/app/device_manager.py`'s. After this session the repo has exactly two real
call sites plus the standalone `config/odrive_config.py` script (re-confirmed by grep,
see progress.md's choke-point audit). Both `odrive_hw.py` and `device_manager.py` can in
principle try to open the same USB device at the same time (Control tab active *and*
Inspector/Dashboard/wizard connected) — reconciling them into one shared handle is a
Phase 2A decision that needs real hardware to test contention behaviour against.
`# TODO(2A)` left at `OdriveHardware.connect()`.

## sim_hw.py dynamics: J/B values and velocity-mode gain chosen

Spec §5.2 asks for "the simplest model that isn't embarrassing," tuned by eye so a 1 Nm
step reaches a "visibly plausible" speed in about a second. Chose `SIM_INERTIA_J =
0.15`, `SIM_DAMPING_B = 0.5` (Nm per turn/s): first-order step response `v(t) =
(1/B)(1 - exp(-t/tau))` with `tau = J/B = 0.3s`, terminal velocity `1/B = 2.0 turns/s`.
That terminal velocity isn't a coincidence — it matches `board_constants
.CONTROLLER_VEL_LIMIT` (2.0 turns/s), the real controller's configured limit, so a 1 Nm
sim command "feels" like it's approaching the same ballpark speed the real board would
be configured to allow. Reaches ~95% of terminal velocity by `3*tau ≈ 0.9s` — verified
directly (`core/tests/test_sim_hw.py`, and live via the Control tab: a 1 Nm torque
command visibly ramps to ~1 turn/s within a second in the headless-Chrome pass).
Sim-only velocity-mode proportional gain `SIM_VELOCITY_KP = 2.0` (Nm per turn/s of
error) — deliberately untuned per spec, ODrive's real closed loops do the work on
hardware; this only needs to converge visibly, not accurately.

## Control telemetry: WebSocket route built per spec, but the frontend uses the REST fallback

Spec §8 names `/ws/control-telemetry` as the primary path and explicitly pre-authorizes
a REST fallback (`GET /api/control/telemetry?since=`) "if the websocket path fights the
existing setup," with instructions to log why. It did, so this documents why.

Both routes were implemented in `backend/app/control_routes.py` per spec. The
websocket works correctly *while connected* — no server-side exceptions, correct data.
The problem is specifically the **close path**, and specifically because the Control
tab opens/closes this socket on every tab switch (`useControlTelemetry` connects only
while the tab is active) — a much higher churn rate than the existing per-device
telemetry socket, which stays open for as long as a device is connected and was never
exercised this way in Session 1.

Root-caused by bypassing the Vite dev proxy entirely and hitting the Flask backend
directly with a bare-minimum open-then-close client: 100% reproducible, so it isn't a
proxy issue. `flask-sock`'s underlying `simple_websocket.Server` runs a background
thread per connection that processes incoming frames — including the client's close
handshake — independently of the Flask request-handling thread running our
`_control_telemetry_session` loop. When the client closes, that background thread
detects it and writes its own close-acknowledgement frame to the raw socket; if our
loop's thread is concurrently calling `ws.send()` around the same moment (its normal
~10 Hz push), two threads end up writing the same unsynchronized socket, and the client
receives an interleaved/corrupted byte stream — surfacing as `WebSocket ... failed:
Invalid frame header` with an unclean `code=1006` close, instead of a normal close.
This is a real limitation of running `flask-sock` on Werkzeug's single-process dev
server (its own docs call out needing `threaded=True`, which we added to
`start_backend.py` as a legitimate fix in its own right — Session 1 never needed it with
only one long-lived WS route — but it did not resolve this specific race; the
background-thread-vs-request-thread send collision is a different problem, effectively
inherent to a naive dev-server WS stack under frequent open/close). Also hardened
`_control_telemetry_session` itself regardless: both `receive()` and `send()` are now
guarded (`send()` wasn't before, and a failed send could half-write a frame), and the
close-check uses a blocking `receive(timeout=_WS_PUSH_INTERVAL_S)` instead of a
non-blocking check plus a separate `time.sleep()`, so the loop notices a close almost
immediately (event-driven) instead of only at the next poll tick — this shrank the race
window from up to 100ms down to single-digit milliseconds, but did not eliminate it.

Decision: kept the `/ws/control-telemetry` route as built (correct, spec-compliant,
matches the primary path Session 3 or 2A could still use under a production WSGI
server where this dev-server limitation doesn't apply) but pointed the frontend
(`useControlTelemetry.js`) at the REST fallback instead — polls `GET
/api/control/status` + `GET /api/control/telemetry?since=` every 150ms. This fully
avoids the open/close churn that triggers the race. Verified: repeated Control ↔
Inspector ↔ Dashboard tab cycling (5 rounds, headless Chrome) produces zero console
errors; the full Control tab flow (start/retarget/stop, both modes) also stays clean.
`frontend/src/api/control.js::controlTelemetryUrl()` is left in place, documented as
currently unused by the UI, for whoever revisits this in 2A.

## Flask dev server: threaded=True added

`backend/start_backend.py`'s `app.run()` didn't pass `threaded=True`. flask-sock's own
documentation calls this out as required for the Werkzeug dev server to serve more than
one connection at a time. Session 1 never needed it (only one long-lived WebSocket
route existed); Session 2 can have two live at once (per-device telemetry + control
telemetry, when both the Control tab and a connected-device tab are open). Added it as
a straightforward correctness fix independent of the close-handling issue above.

---

# Session 3 — resistance profile layer

Per `Phase 1/1C_build_spec_session3.md`. Continues the append-only log above.

## Pre-session: stray uncommitted state found and stashed

Before starting, `git status` showed an uncommitted modification to
`frontend/vite.config.js` (both `/api` and `/ws` proxy targets changed from
`http://127.0.0.1:5000` to `http://127.0.0.1:5050`) plus an untracked
`frontend/vite.config.js.orig` backup file (the unmodified original — evidence of a
`sed -i .orig`-style edit). Neither is mentioned anywhere in Session 2's `progress.md`
or `decisions.md`, and `backend/start_backend.py` still hard-codes port 5000, so this
wasn't a documented, intentional change — most likely leftover manual troubleshooting
on this machine (e.g. port 5000 conflicting with something else locally) that was never
committed or cleaned up.

Didn't investigate further or discard it: stashed both files reversibly
(`git stash push -u -m "pre-session3: stray vite.config.js port-5050 edit + .orig
backup, undocumented in Session 2"`) so the tree matches the documented Session 2
end-state before Session 3 work begins. If this turns out to matter (e.g. port 5000
really is unavailable in this environment), the stash can be popped — not lost.

## Sign convention (spec §5.1)

`core/profiles/detectors.py`: **positive cable velocity = cable paying out =
concentric (lifting)**. Matches the sim's positive-torque → positive-velocity
behaviour directly. `CABLE_SIGN = +1` is the documented one-line flip point if
Phase 2A's real cable rigging inverts this.

## Detector tuning constants chosen (spec §4)

All four (`PHASE_VEL_THRESHOLD_TURNS_S = 0.05`, `PHASE_HYSTERESIS_TURNS_S = 0.02`,
`REP_EWMA_ALPHA = 0.05`, `REP_PROXIMITY_TURNS = 0.1`) taken verbatim from the spec —
no tuning done, all `# TODO(2A)`. Chosen only to be self-consistent (hysteresis band
narrower than the rest threshold) and to work against the sim/synthetic-sequence
smooth motion, per spec §4's explicit instruction.

## RepCounter design: found and fixed two false-positive modes beyond the literal spec text

Spec §5.1 describes the rep counter as: EWMA of position, count a rep when position
returns within `REP_PROXIMITY_TURNS` of the EWMA, gated on having passed through a
CONCENTRIC phase since the last count. Implementing that literally against the
synthetic 3-rep test sequence (`core/tests/test_detectors.py`) surfaced two real bugs
in that literal reading, found by tracing actual per-tick state:

1. **Early-concentric false positives.** Right as a concentric phase begins, position
   and its own slow EWMA are still numerically close (both sitting near the previous
   rep's baseline) — "within proximity of the EWMA" is trivially true for several
   ticks before the EWMA has time to lag behind the now-moving position, firing
   several spurious counts before the rep has gone anywhere (22 counts on one 3-rep
   test run instead of 3). Fixed by adding a `_left_proximity_since_last_count` gate:
   position must move *out* of the proximity band by at least `REP_PROXIMITY_TURNS`
   before a subsequent return into the band can count — turns the check into a real
   "went away, came back" detector instead of a bare distance threshold.
2. **Top-of-rep false positives.** An EWMA lagging a smooth position curve is
   momentarily close to that curve near *any* local extremum of the input, not only
   the true rest position — confirmed by tracing: near the peak of a rep, the
   still-rising EWMA transiently comes within `REP_PROXIMITY_TURNS` of the
   already-descending position (5 counts on the same 3-rep sequence instead of 3, one
   extra per rep from a false trigger just after the top). Fixed by additionally
   gating the count on the phase being `Phase.BOTTOM_HOLD` specifically (not merely
   "distance under proximity"). This also makes the position/EWMA proximity check do
   real work rather than being redundant with the phase gate: `BOTTOM_HOLD` alone can
   fire on any mid-range pause after an eccentric movement, and the proximity check
   confirms that pause is actually near the rep's established baseline, not a partial
   rep.

Also found: with `REP_EWMA_ALPHA = 0.05` (time constant `1/alpha` = 20 ticks = 0.4s at
50 Hz) the EWMA takes roughly 35 ticks (~0.7s) to decay from a peak-tracking value back
within `REP_PROXIMITY_TURNS` of true rest — the synthetic test's inter-rep plateau had
to be lengthened to 1.5s (from an initial 0.3s) to give the counter enough time to
settle between reps; this is a test-fixture cadence choice, not a change to the
spec-given tuning constants, but is worth carrying into Phase 2A's real-cable tuning
work as a concrete data point (a fast/no-pause real rep cadence may need this
constant retuned to actually count reps in practice — flagged as a known limitation
of the stub math, not fixed here per spec §11).

## base.py: added get_primary_parameter() alongside spec's set_primary_parameter()

Spec §5.2 lists `set_primary_parameter(value)` + `primary_parameter_label` as the
live-retarget hook, but doesn't specify a getter. Added `get_primary_parameter()` as
a paired, symmetric method — needed so `ControlSession`/CSV logging can report a
profile's *current* numeric target without holding a reference to the
(non-JSON-serializable) `ResistanceProfile` object itself; see the `ProfileMode`
entry below for how this gets used. Not a spec deviation, just filling a gap the
spec's ABC section didn't address.

## base.py: IS_WRAPPER class attribute (not literally in spec's ABC list)

Spec §7 needs the backend's `/api/profiles` route to report "whether it's a
wrapper" per profile, and §5.3 already gives `OverloadWrapper` a structurally
different constructor (wraps another profile) from the other three. Added
`ResistanceProfile.IS_WRAPPER = False` (class attribute, overridden `True` on
`OverloadWrapper`) so the registry (`core/profiles/__init__.py::PROFILE_REGISTRY`)
can stay literally `dict[str, factory]` as spec'd, with wrapper-ness read off the
class itself (`factory().describe()["is_wrapper"]`) rather than needing a second,
separately-maintained "which ones are wrappers" list that could drift out of sync.

## BellCurveProfile: default curve range and injectable curve_factor

Spec §5.3 specifies the raised-cosine shape and injectability but not concrete
`x_start`/`x_end` defaults (real cable-travel range is unknown pre-2A). Chose
`x_start=0.0, x_end=1.0` (turns) as an arbitrary placeholder window — matches the
"# STUB(2A+)" status of everything else in this file. `curve_factor` defaults to a
bound method computed from `self.x_start/x_end/peak_multiplier`, but the constructor
accepts any injected callable `position -> multiplier`, verified in
`test_bell_curve_curve_factor_is_injectable` that the injected callable is actually
what gets called (not just accepted and ignored).

## OverloadWrapper: zero-arg constructible via a default ConstantProfile

Spec §5.3 says overload "requir[es] a base-profile choice" for real use (the backend
composes it server-side per §7 over whichever base profile the user picked), but
`PROFILE_REGISTRY`'s consumers (schema introspection for `/api/profiles`, the
registry-shape test) need every entry in the registry to be constructible with zero
arguments. Defaulted `wrapped=None` to a fresh `ConstantProfile()` in that case —
only matters for introspection; the real runtime path
(`POST /api/control/start` with `overload: {...}`) always constructs
`OverloadWrapper(explicit_chosen_base_profile, ratio=..., target_phase=...)`.

## ProfileMode: three new BaseMode extension hooks instead of isinstance checks in ControlSession

Spec §3 requires ProfileMode to run an outer loop inside the existing 50 Hz tick
(sample → detect phase/rep → compute_torque → clamp → set_torque_target → log),
while VelocityMode/TorqueMode stay set-and-forget. Rather than adding
`if isinstance(mode_handler, ProfileMode)` branches to `ControlSession`
(`core/control/session.py`), added three concrete (non-abstract, default no-op/
identity) methods to `BaseMode` itself (`core/control/modes.py`):
`tick(hardware, sample) -> dict`, `csv_log_name(mode) -> str`,
`status_target(validated_value)`. `ControlSession` calls all three unconditionally
on whichever mode is active — Velocity/Torque's defaults are no-ops/identity, so
their existing behaviour is provably unchanged (regression-verified: full 35
pre-Session-3 tests still pass unmodified). This keeps `ControlSession` mode-agnostic
exactly as it already was for Velocity vs. Torque, rather than teaching it a third
mode's internals directly.

## ProfileMode's "target" does double duty by design (spec §3), made JSON-safe via status_target()

`ControlSession.start(mode="profile", target=<ResistanceProfile instance>)` — the
profile instance itself is the "target" at start (spec §3's literal wording).
`set_target()` afterward takes a plain float (the primary parameter). Both flow
through the same `validate_target`/`apply_target` pipeline as Velocity/Torque, so
`ProfileMode.validate_target` accepts either type and `apply_target` branches on
which one it got. The problem: `ControlSession._target` (used by `status()`/CSV) must
be JSON/CSV-safe, and a raw `ResistanceProfile` object is neither. Fixed via the
`status_target()` hook (see above): after `apply_target()`, the session asks the mode
to describe the *displayable* target rather than storing the validated value
directly — `ProfileMode.status_target()` returns `self.profile.get_primary_parameter()`
(a plain float) regardless of whether the just-validated value was the profile
object (start) or a float (retarget). Verified:
`test_profile_mode_runs_end_to_end_against_sim` (target is the primary parameter, not
an object) and `test_profile_mode_retarget_adjusts_primary_parameter_not_the_profile_object`
(same profile object mutated in place, confirmed via the original reference).

## No new torque clamp added for ProfileMode (spec §3's "same clamp path")

Spec §3 says the tick loop should "clamp (same clamp path as Session 2's torque
writes)" before `set_torque_target()`. Session 2's torque clamp already lives inside
`hardware.set_torque_target()` itself, asymmetrically: `OdriveHardware` clamps to
`MOTOR_CURRENT_LIM * MOTOR_TORQUE_CONSTANT`, `SimHardware` does not clamp at all
(matches its existing TorqueMode behaviour, unchanged since Session 2). `ProfileMode.
tick()` calls `hardware.set_torque_target(torque)` with the raw profile output,
same as `TorqueMode.apply_target()` always has — no second/duplicate clamp added in
`core/profiles` or `core/control/modes.py`. This is a literal "reuse the same path"
reading, not a new decision, but flagged here since it's easy to misread the spec
sentence as "add a clamp function."

## CSV logger: phase/rep_count populated via mode_handler.tick()'s return value, not a new session field

`ProfileMode.tick()` returns `{"phase": ..., "rep_count": ...}`; Velocity/Torque's
default `tick()` returns `{}`. `ControlSession` stores this in `self._last_extra` and
threads it into both `status()` (`phase`/`rep_count` keys, `None` when absent) and
`CsvLogger.log_sample(..., phase=extra.get("phase", ""), rep_count=extra.get("rep_count", ""))`
— empty string for velocity/torque runs, matching spec §6's amendment exactly, with
no special-casing beyond the dict lookup.

## Vite dev proxy: added a /ws prefix

`frontend/vite.config.js` only proxied `/api/*` to the backend; `/ws/control-telemetry`
falls outside that prefix (matching the spec's literal path rather than folding it under
`/api`). Added a second proxy block for `/ws` (same target, `ws: true`) so the route
resolves in dev. Currently inert from the frontend's perspective (see the websocket
decision above — the UI doesn't call it), but kept so the backend route is reachable
through the dev proxy for anyone testing it directly, and so no further config change is
needed if the WebSocket path is revisited later.
