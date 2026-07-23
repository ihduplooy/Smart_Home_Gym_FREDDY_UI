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

## /api/control/telemetry (REST fallback) not extended with per-sample phase/rep_count

Spec §7 says "status()/telemetry responses gain phase and rep_count when a profile is
running." `status()` does (see above). The ring buffer behind `/api/control/telemetry`
stores raw `TelemetrySample` objects (position/velocity/current_iq/torque_est/t) with
no per-sample phase/rep_count history — only the *latest* tick's phase/rep_count is
tracked (`ControlSession._last_extra`). Adding historical phase/rep_count to every
buffered sample would mean carrying a second parallel array through the ring buffer
and CSV-adjacent code paths for comparatively little payoff: spec §7's own frontend
description only asks for a live badge + rep count (point-in-time values), not a
phase-over-time chart. Left the REST telemetry route unchanged; `status()`'s
`phase`/`rep_count` fields are what the Profiles tab polls for the badge — same
150 ms poll loop the Control tab already uses (`useControlTelemetry`), no changes
needed there either.

## Overload composed profile's CSV filename doesn't reflect the wrapped base profile's name

`ProfileMode.csv_log_name()` uses `self.profile.name`, which for an `OverloadWrapper`
is literally `"overload"` — so `telemetry_<ts>_profile-overload_sim.csv` regardless of
which base profile (constant/bell_curve/vbt) it wraps. Verified live via curl. Not
fixed: matches the spec's literal filename convention
(`telemetry_<ts>_profile-<name>_<sim|real>.csv`, one `<name>`), and the run's actual
parameters (including which base profile was chosen) are still in the CSV's `mode`/
`target` columns and the backend's own request log — just flagging that multiple
overload runs over different base profiles won't be distinguishable by filename alone
if someone's sorting a `logs/` directory later.

## Found: Session 2's own README snippet has an unstated race (not fixed there, avoided in the new one)

While verifying Session 3's new `core/README.md` snippet, re-ran Session 2's existing
one exactly as written (`session.start(...); print(session.status()["latest_sample"])`,
no sleep) three times: it printed `None` every time — `status()` is called before the
50 Hz telemetry thread has produced its first sample, a race that has nothing to do
with Session 3's changes. Session 2's `progress.md` DoD 5 claims it "printed a live
TelemetrySample," which doesn't reproduce as literally written. Not fixed in Session
2's snippet (out of this session's scope to rewrite prior claims), but the new Session
3 snippet added `time.sleep(0.1)` before reading status specifically so it doesn't
repeat the same unstated race — verified deterministic across multiple runs.

## Vite dev proxy: added a /ws prefix

`frontend/vite.config.js` only proxied `/api/*` to the backend; `/ws/control-telemetry`
falls outside that prefix (matching the spec's literal path rather than folding it under
`/api`). Added a second proxy block for `/ws` (same target, `ws: true`) so the route
resolves in dev. Currently inert from the frontend's perspective (see the websocket
decision above — the UI doesn't call it), but kept so the backend route is reachable
through the dev proxy for anyone testing it directly, and so no further config change is
needed if the WebSocket path is revisited later.

---

# Phase 2A hardware bring-up — bug found on the first live hardware run

## Bug: `erase_configuration()`/`save_configuration()` reboot mid-RPC, crashing the reconnect line

First real run of `config/odrive_config.py` against the actual board crashed right after
the "Erase existing configuration" confirmation prompt with
`fibre.protocol.ChannelBrokenException`. Root cause: on this board, both
`erase_configuration()` and `save_configuration()` reboot the ODrive *before* the RPC
call returns to the Python client, severing the USB/fibre channel mid-call. The script's
existing pattern was:

```python
odrv0.erase_configuration()
# erase_configuration() reboots the board and drops the USB connection — reconnect:
odrv0 = odrive.find_any()
```

The comment correctly described the reboot, but the reconnect line is unreachable —
`erase_configuration()` itself raises `ChannelBrokenException` (confirmed by reading
`fibre`'s transport/protocol source in this venv: `usbbulk_transport.py` translates a
`usb.core.USBError` from the dead connection into
`fibre.protocol.ChannelBrokenException`, which propagates out of
`remote_endpoint_operation()` uncaught) — so the script dies on that line before ever
reaching the reconnect. No motor was energized, nothing moved; the crash happens in
Section 1 (static config), before any calibration/motor step.

The same unreachable-reconnect pattern was present at all three `save_configuration()`
call sites too (bus-limits save, static-config save, post-calibration save) — not yet hit
live only because the script crashed on the first `erase_configuration()` call, before
reaching any of them.

## Fix: `call_and_reconnect()` helper, used at all four reboot-triggering call sites

Added one helper (`config/odrive_config.py`, above the "Connect" section) that wraps any
no-arg RPC known to reboot the board:

```python
def call_and_reconnect(odrv, method_name, timeout=REBOOT_RECONNECT_TIMEOUT):
    try:
        getattr(odrv, method_name)()
    except fibre.protocol.ChannelBrokenException:
        pass  # expected: reboot dropped the connection mid-call
    new_odrv = odrive.find_any(timeout=timeout)
    if new_odrv is None:
        print(...)  # clear message: board didn't reappear, check power/USB/isolator
        sys.exit(1)
    return new_odrv
```

Replaced all four sites with `odrv0 = call_and_reconnect(odrv0, "erase_configuration")` /
`"save_configuration"` — one at the erase call, three at the three saves (bus limits,
static config, post-calibration). Design choices, each deliberate:

- **Only `ChannelBrokenException` is caught.** Confirmed by reading `fibre`'s own source
  (`protocol.py`, `usbbulk_transport.py`) that this is the one exception class a
  reboot-severed USB connection surfaces as on this stack (`usb.core.USBError` gets
  translated to it inside the transport layer already). Any other exception from the
  wrapped call is a real error and is left to propagate — no broad `except Exception`
  that could hide an unrelated failure behind "oh, that's just the reboot."
- **No silent retry loop.** `odrive.find_any(timeout=...)` is given one bounded timeout
  (`REBOOT_RECONNECT_TIMEOUT = 15`s); if the board doesn't reappear, the script prints a
  specific, actionable message ("check that the board actually rebooted... before
  re-running the script") and exits non-zero. Per the explicit ask: a silent retry here
  could mask a real problem (USB isolator knocked loose, board didn't actually reboot,
  wrong board enumerated) instead of surfacing it to the person standing at the bench.
- **Reconnects even if the call doesn't raise.** If a given firmware/timing variant lets
  the RPC ack squeak through before the disconnect (so no exception at all), the helper
  still calls `find_any()` afterward rather than trusting the pre-reboot handle — the
  board rebooted either way, and the old `odrv0` object's channel is dead regardless of
  whether Python noticed synchronously.
- **Confirmation gates and safety checks untouched.** Every `confirm()` call, every
  `check_errors()`/`check_motor_calibration_sane()`/`wait_for_idle()` call is in exactly
  the same place relative to the reboot-triggering calls as before — only the
  call+reconnect line itself changed, per the explicit instruction not to restructure
  anything else.

Audited every call site of the three known reboot-triggering methods on this board
(`erase_configuration`, `save_configuration`, `reboot()`) across the whole repo
(`grep -rn "erase_configuration\|save_configuration\|\.reboot(" --include="*.py" .`,
excluding `.venv`): the only four Python call sites are the ones just fixed in
`config/odrive_config.py`; no `.reboot()` call exists anywhere. The frontend also invokes
`save_configuration`/`erase_configuration` (Presets tab, calibration hook, config wizard,
erase-config modal) but through `backend.invokeCommand` → the Flask backend's
`device_manager`, a fundamentally different, already-resilient architecture: every route
handler calls `device_manager.attach_or_get(serial)` fresh per request (Session 1's
choke-point finding) rather than holding one long-lived handle across a reboot the way
this standalone script does, and the frontend's own polling cycle already treats a
device that drops off as "reconnect on next poll." Confirmed no equivalent bug there —
out of scope for this fix regardless, since the reported crash is specific to this
script's linear, single-`odrv0`-variable structure.

**Verification (no real hardware touched):** `python -m pytest core/tests` — 69/69
still passing (this fix only touches `config/odrive_config.py`, which predates `core/`
and isn't imported by it or by any test). `python -m py_compile config/odrive_config.py`
— clean. Since the script executes `odrive.find_any()` at module scope (a bring-up
script, not wired into `core/`'s mock hardware), it can't be imported directly without
attempting a real USB connection — instead, `call_and_reconnect`'s actual AST node was
extracted straight out of the real file and exec'd in isolation against a fake `odrive`
module (scratch script, not committed, same throwaway-script precedent as the headless-
Chrome checks in prior sessions) to exercise: normal reboot-and-reconnect on both
`erase_configuration` and `save_configuration`; the board-never-reappears path (confirms
`sys.exit(1)` with a non-zero code, no hang, no retry loop); an unrelated exception from
the wrapped call propagating instead of being swallowed; and a non-raising call still
going through reconnect. All 7 checks passed. Real hardware verification is explicitly
deferred to the user's own session, per their instruction — this script is not to be run
against the physically-connected board from here.

## Bug: `odrv0.config.enable_brake_resistor` doesn't exist on this board's firmware (v0.5.1)

Found on the same live hardware run, right after the erase/reconnect fix above worked
correctly: the script crashed setting `odrv0.config.enable_brake_resistor = True` in the
bus-level-limits block. Confirmed live via `dir(odrv0.config)` on the actual board:
no `enable_brake_resistor` attribute anywhere in `odrv0.config`, `odrv0.axis0.motor.config`,
or elsewhere. On v0.5.1, the brake resistor is enabled implicitly by `brake_resistance`
being non-zero — there is no separate boolean flag on this firmware.

This is independently corroborated in-repo: `frontend/src/utils/configSchema.js`'s own
tooltip for `config.brake_resistance` already says "Set 0 to disable," i.e. the frontend
wizard was already written with the correct implicit-enable understanding — only this
standalone 1B script had the stale explicit-flag line.

**Fix:** removed the `enable_brake_resistor` line; updated the comment above
`brake_resistance` to state explicitly that setting it non-zero is what enables the
resistor on this firmware, so a future reader doesn't wonder where the enable flag went.

## Audit: cross-checked every other `.config.` attribute in the script

Per the request to catch any other stale attribute names in one pass rather than one at
a time on live hardware, grepped every `.config.` (and adjacent `.can.`/`.trap_traj.`)
reference in `config/odrive_config.py` and cross-checked each against
`frontend/src/utils/odriveApiReference05x.json` — the project's own bundled property
reference, generated from official ODrive docs (per its `version` field, actually
**v0.5.6**, not our exact v0.5.1 — see caveat below).

26 of 28 attribute references checked out clean against the reference (all of
`odrv0.config.*`, `odrv0.axis0.motor.config.*` incl. the read-only
`phase_resistance`/`phase_inductance` used by `check_motor_calibration_sane`,
`odrv0.axis0.encoder.config.*`, `odrv0.axis0.controller.config.*`) — every name exists
in the reference's `motor_config`/`encoder_config`/`controller_config`/`config` property
groups.

Two things the reference genuinely can't confirm either way, both **left unchanged**:

- **`odrv0.axis0.config.can_node_id` / `odrv0.axis1.config.can_node_id` /
  `odrv0.can.set_baud_rate(500000)`** — none of `can_node_id` or `set_baud_rate` appear
  anywhere in the reference JSON at all (checked via a full-text search, not just the
  `axis_config` property group). The reference only models a *nested*
  `axis{n}.config.can` object (`ODrive.Axis.CanConfig`, with a `node_id` leaf) and
  `odrv0.can.config.baud_rate` — the same 0.6.x-style shape Session 1 already identified
  and rejected in favor of the flat path (`docs/decisions.md`, "CAN Bus wizard fields"
  entry): Session 1 explicitly sourced the flat `can_node_id` from this exact 1B script's
  own "Ghost Axis 1 fix" comment as the confirmed-real 0.5.x pattern, not from this
  reference file, and even manually seeded `axis0.config.can_node_id`/
  `axis1.config.can_node_id` into `backend/app/mock_odrive.py` specifically because the
  auto-generated reference is missing it. Not flagged as a new bug — matches an
  already-documented, already-reasoned-through discrepancy — but also not yet
  live-confirmed on this exact board, since the crash on this run happened earlier in
  Section 1 (bus limits), before reaching the CAN config lines. Worth a specific glance
  on the next live run given this is now the *second* confirmed real gap in this exact
  reference file.
- **`odrv0.axis0.trap_traj.config.vel_limit`/`accel_limit`/`decel_limit`** — the
  reference has no `trap_traj_config` property group at all (its five groups are
  `config`/`motor_config`/`encoder_config`/`controller_config`/`axis_config` only), so
  there's nothing in this source to cross-check these three against, positive or
  negative. Left unchanged; flagging only as "unverifiable from this source," not
  "verified."

**Caveat on the reference itself:** `odriveApiReference05x.json`'s own `version` field
reads `"0.5.6"`, not `"0.5.1"` (our board's actual firmware) — and it already missed
`enable_brake_resistor`'s absence in the exact opposite direction (it *lists*
`enable_brake_resistor` as a real 0.5.6 property, which turned out to not exist on our
0.5.1 board either way — whether that's a 0.5.1-vs-0.5.6 difference or the reference
being wrong even for 0.5.6 can't be determined from here). So this cross-check is a
useful screen for names that are obviously wrong, not a substitute for what the live
board's own `dir()` says — consistent with why this bug was only caught by running on
real hardware in the first place, not by static analysis. No live hardware was
contacted for this audit; the reference-file cross-check above was a static JSON read,
not a mock-device connection (`ODRIVE_MOCK=1` mock is Flask-only and isn't wired to this
standalone script's `odrive.find_any()` — see the bring-up bug entry above).

**Verification:** `python -m py_compile config/odrive_config.py` clean;
`python -m pytest core/tests` still 69/69 (fix is isolated to this one script, outside
`core/`).

## Encoder offset calibration: bounded auto-retry added (21 July 2026, follow-up session)

Open item #14 in the project plan logged ~2 successes out of 10+ attempts at
`AXIS_STATE_ENCODER_OFFSET_CALIBRATION` in the prior live session, with no reproducible
trigger identified (CS pin, current, voltage, motor-calibration validity all ruled out
as variables) and a standing manual workaround: retry the state transition until
`axis0.encoder.is_ready` returns `True`, then save immediately. The plan's own next-step
note suggested automating exactly this as a bounded retry loop rather than continuing
to make the user re-invoke the whole script per attempt.

**Change:** Section 2 of `config/odrive_config.py` now loops up to 5 times on
`AXIS_STATE_ENCODER_OFFSET_CALIBRATION`. Success is judged by
`axis0.encoder.is_ready and axis0.encoder.error == ENCODER_ERROR_NONE` — checked
explicitly rather than relying on `wait_for_idle` + an exception, because the observed
failure mode (`ENCODER_ERROR_NO_RESPONSE`) doesn't raise; the axis just returns to idle
without the encoder actually ready. Between attempts, `odrv0.clear_errors()` (confirmed
as a real top-level, no-arg RPC via `odriveApiReference05x.json`, "clear all errors of
this device including submodules") resets error state so a failed attempt doesn't block
the next one. On the first clean success: `axis0.encoder.config.pre_calibrated = True`
is set and `save_configuration()` runs immediately, matching the existing manual
workaround. If all 5 attempts fail, the script exits without saving and points at the
next diagnostic step already identified in the plan (physical inspection of the
AS5047P chip's part markings/solder joints) instead of retrying indefinitely or leaving
the user to guess what to do next.

Also imported `ENCODER_ERROR_NONE` from `odrive.enums` for the success check — confirmed
it exists in the installed `odrive==0.5.1.post0` package (`ENCODER_ERROR_NONE = 0`,
alongside `ENCODER_ERROR_NO_RESPONSE = 4`, both queried live from the venv's own
`odrive.enums` module, not assumed from docs).

**Verification (no real hardware touched, per the same standing instruction as the two
bug-fix entries above):** `python -m py_compile config/odrive_config.py` clean.
`python -m pytest core/tests` not re-run this pass — the venv this session currently
has no `pytest` installed; unrelated to this change regardless, since this standalone
script predates `core/` and isn't imported by it. Real-hardware verification of the
retry loop is deferred to the user's own session — same reasoning as before: the
script's `confirm()` gates exist specifically for a human physically present at the
bench to verify safety conditions before each energizing step, so this assistant does
not run this script against real hardware directly.

## Encoder offset calibration: tier-2 diagnostic retry added — EMI-during-phase-switching theory (21 July 2026, second follow-up)

The bounded 5-attempt retry loop above didn't resolve `ENCODER_ERROR_NO_RESPONSE` on the
live board — consistent failure during `AXIS_STATE_ENCODER_OFFSET_CALIBRATION`. New
evidence narrows the theory considerably: motor calibration always succeeds cleanly, and
the SPI link is confirmed alive and correct at idle (`shadow_count`/`pos_estimate` track
correctly while hand-spinning the motor with no phases energized). The fault is specific
to the one state where motor phases are actively switching *and* the encoder is being
read continuously — pointing at EMI from motor drive current coupling into the SPI
lines during that step, not a dead/miswired encoder or a bad CS pin (both would also
break the idle-read case, which works fine).

**Change:** `config/odrive_config.py`'s retry loop is now two-tiered. The original
5-attempt loop (unchanged logic — same `is_ready`/`error` check, same per-attempt
individual-field error clearing since `clear_errors()` doesn't exist on v0.5.1) is now
"tier 1," extracted into `run_encoder_calibration_attempts(odrv0, tier_label)` so both
tiers share one implementation rather than duplicating the loop body. If tier 1 fails
all 5 attempts, tier 2 temporarily reduces two settings before running another 5
attempts at the same logic:

- `axis0.motor.config.calibration_current`: 5.0 → 3.0 A (less phase current during the
  calibration move → less EMI radiated/conducted toward the SPI lines).
- `axis0.encoder.config.bandwidth`: 3000 → 1000 (a lower-bandwidth filter on the
  SPI-derived position estimate is less susceptible to noise-induced glitches).

**On tier-2 success:** the reduced values are *not* reverted — they're kept as the new
working baseline and persist through the normal `save_configuration()` call at the end
of Section 2 (same call site as before, unchanged). Printed output explicitly names
which tier succeeded and at which settings, so this isn't silently indistinguishable
from a tier-1 success in the script's output or in a later `dir()` dump of the saved
config.

**On tier-2 failure (all 5 attempts, both tiers exhausted):** `calibration_current` and
`encoder.config.bandwidth` are explicitly restored to their original values (5.0/3000)
before `sys.exit(1)` — these remain the best starting point for the next diagnostic step
(physical inspection of the AS5047P chip), and a failed low-current experiment should
not silently become the new default that a future run or a live `dir()` dump picks up.

Added matching comments (not value changes — these are temporary experiment values, not
new project defaults) near `MOTOR_CALIBRATION_CURRENT` and `ENCODER_BANDWIDTH` in
`config/board_constants.py`, pointing at this tier-2 path, so a future reader isn't
confused if a live board dump ever shows 3.0/1000 there.

**Verification (no real hardware touched, same standing reasoning as every prior entry
in this section):** `python -m py_compile config/odrive_config.py config/board_constants.py`
clean. Real-hardware verification (which tier actually succeeds, if either) is deferred
to the user's own live session — reported back separately, to be logged here and in
`docs/progress.md` once known.

## Encoder offset calibration: tier-3 diagnostic added — "motor calibration right before encoder calibration" hypothesis, n=1 (21 July 2026, third follow-up)

The live diagnostic session that motivated tier 2 was actually run: ~15 manual attempts
at `AXIS_STATE_ENCODER_OFFSET_CALIBRATION`, only one success. That one success
immediately followed a fresh `AXIS_STATE_MOTOR_CALIBRATION` run in the same session,
with no reboot in between — every other attempt was encoder calibration alone (motor
already calibrated from earlier in the session, not re-run), and every one of those
failed. This is a new hypothesis for open item #14: something about a *just-completed*
motor calibration (rather than motor calibration having merely happened at some point
earlier in the session) puts the axis into a state where the encoder step is more
likely to succeed. **Explicitly not yet confirmed — n=1, a single data point, easily
confounded with unrelated time-varying factors** (thermal drift, EMI environment
changing between attempts, etc.). Tier 3 exists to actually test it with more than one
data point, not to assume it's correct.

**Change:** added a third tier to `config/odrive_config.py`'s retry system, gated
behind tiers 1 and 2 both exhausting all 5 attempts (tier 1/tier 2 code and behavior
untouched — verified by diff, only new code added after tier 2's existing block). For
up to 5 attempts, tier 3: clears axis/motor/encoder/controller errors, runs a fresh
`AXIS_STATE_MOTOR_CALIBRATION`, checks it succeeded by reusing the *existing*
error/sanity logic — factored `check_errors()`'s error-flag check into a new boolean
`axis_has_errors(axis)` and `check_motor_calibration_sane()`'s range check into a new
boolean `motor_calibration_is_sane(axis)`, both pure extractions with the original
exit-on-failure functions rewritten to call them (their external behavior/print output
at the original two call sites — Section 2's initial motor calibration, Section 3's
`check_errors()` calls — is unchanged; verified by reading, not just diffing, since
these are also relied on outside this retry loop). If motor calibration fails or isn't
sane, tier 3 logs it (matching tier 1/2's log format) and moves to the next attempt
without ever reaching the encoder step. If motor calibration succeeds, tier 3
immediately (no reboot, no extra delay beyond what `wait_for_idle()` already blocks on)
requests `AXIS_STATE_ENCODER_OFFSET_CALIBRATION`, waits for idle, then — after a brief
0.2s settle delay — checks `encoder.is_ready and encoder.error == ENCODER_ERROR_NONE`.
The settle delay is a direct response to something observed in the live session: reading
`is_ready`/`error` immediately after setting `requested_state` intermittently showed a
false-positive "no error, ready" before the state machine had actually run the attempt
— without the delay, tier 3 could wrongly declare success on a transition that hadn't
really happened yet.

A new `clear_axis_errors(axis)` helper holds the same four-field clear tier 1/2 already
does inline (`axis.error`/`motor.error`/`encoder.error`/`controller.error = 0`,
`clear_errors()` still doesn't exist on v0.5.1) — added as a separate helper rather than
refactoring tier 1/2's existing inline block to call it, specifically so tier 1/2's code
is untouched, not just behaviorally equivalent.

**On tier-3 success:** both `motor.config.pre_calibrated` and
`encoder.config.pre_calibrated` are set `True` (tier 1/2 only ever needed to set the
encoder flag, since their motor calibration was the original one-time run from earlier
in Section 2 — tier 3 is the first tier that re-runs motor calibration itself, so it
sets both). Reports which attempt succeeded; the existing post-loop
`save_configuration()` call (unchanged call site) persists it, and the final "Section 2
complete" message now names tier 3 specifically when it's the one that worked.

**On tier-3 failure (all 5 attempts):** the script exits the same way tier-2 exhaustion
already did (clean message, `sys.exit(1)`, nothing saved), with `calibration_current`/
`encoder.config.bandwidth` restored to their originals (5.0/3000) as a defensive
belt-and-suspenders step — tier 2's own failure branch already restores them before
tier 3 ever runs, so this is a no-op in the current control flow, not a second
independent revert of something still-reduced. The failure message now names all three
tiers and adds a new recommendation beyond "physical inspection of the AS5047P chip":
since software-side retries are now exhausted across all three tiers, next may be
direct measurement of the SPI lines during an active calibration attempt (oscilloscope
or logic analyzer) to check for external noise/EMI — tooling not currently on hand,
flagged explicitly rather than left implicit.

**Verification (no real hardware touched, same standing reasoning as every prior entry
in this section):** `python -m py_compile config/odrive_config.py` clean. Read through
the full tier-1/tier-2/tier-3 control flow to confirm `orig_calibration_current`/
`orig_encoder_bandwidth` (module-level names set inside tier 2's `if not
encoder_calibrated:` block) are in scope by the time tier 3's failure branch references
them — true in every reachable path, since tier 3 only runs when that block already
executed (tier 1 must have failed to reach it). Real-hardware verification (whether the
motor-recalibration hypothesis actually holds beyond n=1, and which tier ultimately
succeeds if any) is deferred to the user's own live session — reported back separately.

## New standalone diagnostic script: `config/diagnose_encoder_spi.py` (open item #14, fourth follow-up, 21 July 2026)

The three-tier retry system in `config/odrive_config.py` iterates on the calibration
state machine itself but never actually isolates *where* the `ENCODER_ERROR_NO_RESPONSE`
fault lives — retry, current, bandwidth, and motor-recalibration are all still shots in
the dark against the same one symptom. Added a new, separate diagnostic script instead
of another calibration-retry tier, using ODrive's own diagnostic states/tools rather than
more calibration attempts:

- **Step 1 — `AXIS_STATE_LOCKIN_SPIN` open-loop drive test.** Drives the motor without
  going through the encoder-offset-calibration algorithm at all, polling
  `encoder.spi_error_rate`/`pos_estimate`/`shadow_count`/`vel_estimate` at ~10 Hz for a
  few seconds. If the SPI link stays clean under drive here, the fault is almost
  certainly in the calibration state machine/logic, not raw SPI communication — a
  meaningfully different conclusion than anything the tiered retries in
  `odrive_config.py` could produce, since none of them isolate "driven, but not via the
  calibration algorithm" as its own condition. Confirmed `AXIS_STATE_LOCKIN_SPIN` exists
  in the installed `odrive==0.5.1.post0` package's `odrive.enums` (value 9) before
  writing this; the script still checks for it defensively at runtime (`getattr`, not a
  bare import-time assumption) and prints the full `AXIS_STATE_*` enum listing if it's
  ever missing, rather than crashing.
- **Step 2 — "slow lockin" calibration attempt.** One `AXIS_STATE_ENCODER_OFFSET_CALIBRATION`
  attempt with `axis0.config.calibration_lockin`'s `vel`/`accel` cut to 1/4 and
  `ramp_time` lengthened ~3.75x (scaled off whatever's currently configured, not
  hardcoded absolutes — these ratios happen to map ODrive's stock defaults 40/20/0.4 to
  the project's suggested 10/5/1.5). In-memory only, restored in a `finally` block
  regardless of outcome — nothing is saved. Success here would point at a timing-budget
  issue (SPI read competing with the control loop for cycles); the same
  `ENCODER_ERROR_NO_RESPONSE` at slow speed would suggest the slowdown isn't the
  relevant variable.
- Gated behind `confirm()` per step (Step 2's prompt shows Step 1's verdict text), same
  pattern as every energizing step in `odrive_config.py` — this assistant does not run
  either step against the real board; both are for the user's own bench session.
- **Never touches saved configuration**: no `erase_configuration()`/`save_configuration()`
  calls anywhere in the file, and `pre_calibrated` is never set on anything (Step 2's one
  calibration attempt is purely diagnostic — success there is reported, not persisted).
- **Reuse decision**: `config/odrive_config.py` can't be imported (it's a top-level
  script that calls `odrive.find_any()`/`confirm()` at import time — see the "Config
  wizard" entry above, "never import that module, only run it") and this task's
  instructions were explicit not to modify it. Extracted the three small reusable bits
  (`confirm()`, `wait_for_idle()`, individual-field error clearing since `clear_errors()`
  doesn't exist on v0.5.1) into a new tiny shared module, `config/odrive_diag_common.py`,
  rather than re-copying them inline or leaving `odrive_config.py`'s copies un-reused.
  `odrive_config.py` itself is unmodified and still carries its own inline copies — this
  doesn't retroactively deduplicate that file, only prevents the new script from adding a
  third copy. `odrive.utils.dump_errors(odrv0)` (confirmed present in the installed
  package) is used directly for the Step 0 reference dump rather than reimplementing it.
- **Verification (no real hardware touched)**: `python -m py_compile
  config/diagnose_encoder_spi.py config/odrive_diag_common.py` clean. Ran the actual
  script's `main()` against a hand-built fake `odrive` module (monkeypatched into
  `sys.modules`, `input()` stubbed to auto-confirm, `time.sleep` no-op'd — same
  fake-module precedent as the `call_and_reconnect()` AST-exec verification above) to
  exercise the full control flow end-to-end with no exceptions: Step 0's reference dump,
  Step 1's LOCKIN_SPIN poll loop and idle-return, Step 2's calibration_lockin read/slow/
  restore-in-`finally` cycle, and the final four-combination summary printer. Not a
  substitute for live SPI/error behavior (the fake stubs don't simulate real fault
  signatures), but it did catch and fix one real bug pre-verification: an f-string with a
  stray literal `{...}` (`SyntaxError: f-string: single '}' is not allowed`) that
  `py_compile` alone had already caught before the fake-hardware run.

Not yet done: running this against the real board — deferred to the user's own live
session, to be reported back and logged here + in `docs/progress.md` once known. Per the
task's own framing, this entry logs the script's existence and purpose only, not an
outcome.

---

## AS5047P "super-sulk" latched fault — root cause found (open item #14, resolved 21 July 2026)

Full live-bring-up session, same day as the four diagnostic follow-ups above, actually run
against the physically wired board. This closes open item #14 and is one of the most
significant findings of the project so far, so it's logged here in full rather than as a
one-line status change.

### The root cause

The intermittent/persistent `ENCODER_ERROR_NO_RESPONSE` on
`AXIS_STATE_ENCODER_OFFSET_CALIBRATION` was **not** caused by anything the earlier
diagnostic trail tested: not EMI, not wiring, not magnet alignment or magnet type, not the
CS pin, not calibration current, not encoder bandwidth. All of those were tested and ruled
out earlier (project plan open item #14's diagnostic trail; tiers 1-3 in
`config/odrive_config.py`'s retry loop, and the tier-2 EMI theory specifically). Those tiers
should now be understood as having tested the wrong layer of the problem entirely — they
retry/adjust the calibration *attempt*, but the fault isn't in any individual attempt.

The actual cause: the onboard AS5047P can enter a **latched fault state**. This matches a
failure mode other users have independently reported on the ODrive community forum as
"super-sulk" — see
[discourse.odriverobotics.com/t/clarification-on-spi-encoders/6451/18](https://discourse.odriverobotics.com/t/clarification-on-spi-encoders/6451/18),
posts by user "towen". In this state:

- The chip returns a **frozen position value** — confirmed on this exact board: with the
  axis idle, `shadow_count` stayed at exactly `0` even during confirmed physical hand-rotation
  of the motor shaft (previously-working idle-tracking behaviour, silently broken).
- `encoder.spi_error_rate` **misleadingly stays at `0.0`** — no transaction-level SPI errors
  are flagged, so the link looks superficially healthy. This is exactly why earlier diagnostic
  sessions (including `config/diagnose_encoder_spi.py`'s Step 1, if it had been run while the
  chip was already latched) could plausibly have read "SPI healthy" while the encoder was in
  fact non-functional — the error-rate counter simply doesn't see this class of fault.

Critically — confirmed directly on this board, matching the forum thread — the latch:

- Does **not** clear via `clear_axis_errors()` (setting `axis.error`/`motor.error`/
  `encoder.error`/`controller.error = 0`).
- Does **not** clear via `odrv0.reboot()`.
- Does **not** clear via `save_configuration()`'s own implicit reboot.
- **Only** clears via a full physical power cycle of the DC bus. Confirmed live: after fully
  switching the Manson HCS-3202 bench PSU's output off and back on (not just replugging
  USB), `shadow_count` immediately showed live, changing values again — both positive and
  negative, correctly tracking real shaft motion.

### How it was isolated

After the power cycle confirmed the encoder alive again, motor calibration and encoder
offset calibration were walked by hand in `odrivetool` (not via the script) specifically to
find out which step, if any, re-triggers the sulk state:

- Motor calibration was run first and confirmed **not** to kill the encoder — `shadow_count`
  was checked immediately after a completed motor calibration and was still live/tracking.
  This directly informs the tier-3 hypothesis logged in the entries above (motor
  recalibration immediately before an encoder attempt, n=1 success): tier 3's apparent
  success was very likely just a case of encoder calibration being attempted while the
  encoder happened to be un-latched, not because a fresh motor calibration does anything
  causal to the encoder. The one thing that actually correlates with success is "was the
  encoder latched at the time," not "was motor calibration just re-run."
- With the encoder confirmed alive, `AXIS_STATE_ENCODER_OFFSET_CALIBRATION` was attempted:
  it **succeeded cleanly on the first try**, immediately post-power-cycle
  (`encoder.error == 0`, `encoder.is_ready == True`) — so the encoder offset calibration step
  itself is not what triggers the sulk state either; the latch was pre-existing from earlier
  in the day's session (most likely from one of the many prior failed calibration attempts,
  though which specific earlier event triggered it isn't pinpointed and may not be
  reconstructable from the session's own logs).
- The successful calibration was saved (`odrv0.axis0.motor.config.pre_calibrated = True`,
  `odrv0.axis0.encoder.config.pre_calibrated = True`, `save_configuration()`) and confirmed
  durable across a subsequent `odrv0.reboot()`: `motor.is_calibrated == True`,
  `encoder.is_ready == True`, clean `dump_errors()` on both axes after the reboot.

### Practical takeaway for future sessions

If `ENCODER_ERROR_NO_RESPONSE`, or any frozen `pos_estimate`/`shadow_count` that doesn't
move during confirmed physical shaft rotation, is seen again on this board: **do a full DC
bus power cycle (PSU output off, wait ~10s, output back on) before attempting encoder
offset calibration again.** Not `clear_errors()`/individual-field error clearing, not
`odrv0.reboot()`, not another round of software retries. This is counterintuitive — a
config/software retry loop structurally cannot fix a hardware-latched fault state — and easy
to miss, which is why it's now called out directly at the top of Section 2 in
`config/odrive_config.py` (see that file) rather than left only in this log.

Tiers 1-3 in `config/odrive_config.py`'s retry loop were **not removed** — they're harmless,
and tier 3's motor-recalibration-immediately-before-encoder-attempt pattern may still have
incidental value for some other, unrelated transient failure even though it isn't what
explains today's n=1 success. But they should no longer be treated as the primary mitigation
for `ENCODER_ERROR_NO_RESPONSE`; a prominent comment pointing at the DC-power-cycle fix was
added ahead of them so a future run that hits this error is pointed at the right fix
immediately.

**Verification:** confirmed live and directly on the physical board this session (not
simulated/mocked) — this is a hardware bring-up finding, not something `core/tests` or a
mock device could exercise. `python -m py_compile config/odrive_config.py` clean after
adding the comment block.

## Live gain tuning at the bench (open item #7, resolved 21 July 2026)

Same live session as the root-cause finding above, immediately after. With a working saved
calibration (`motor.is_calibrated == True`, `encoder.is_ready == True`), closed-loop control
was exercised for the first time and the placeholder controller gains from `odrive_config_1B.py`
(carried into `config/board_constants.py`, open item #7) were tuned live at the bench.

Method: started conservative and increased each gain only once the previous step was
confirmed clean — no oscillation, no overshoot, smooth commanded moves observed physically
on the free-spinning wheel:

| Gain | Start | Intermediate | Final |
|---|---|---|---|
| `pos_gain` | 1.0 | 3.0 | **6.0** |
| `vel_gain` | 0.02 | — | **0.05** |
| `vel_integrator_gain` | 0.0 | 0.05 | **0.1** |
| `motor.config.current_lim` | 10.0 | — | **15.0** |

All four were saved live via `save_configuration()` and confirmed to persist. `config/
board_constants.py` updated to match (`CONTROLLER_POS_GAIN = 6.0`, `CONTROLLER_VEL_GAIN =
0.05`, `CONTROLLER_VEL_INTEGRATOR_GAIN = 0.1`, `MOTOR_CURRENT_LIM = 15.0`) — these are no
longer generic "conservative starting point" placeholders, they're the live-tuned baseline
as of this session.

**Important scope caveat, not yet resolved:** this tuning was done against a **free-spinning
wheel with no cable load** — real cable tension/inertia in the actual gym-cable rig (Phase
2A cable-rigging work, not yet done) will change the effective load on the controller and
these gains may need to be re-tuned once that's introduced. Also note open item #7 as
originally scoped in the project plan bundled a second, unrelated item — the 25V bench-only
`dc_bus_overvoltage_trip_level`, which **must still be raised before the battery phase**
(~42V) — that part is untouched by this session and remains a live TODO (already tracked via
the comment on `DC_BUS_OVERVOLTAGE_TRIP_LEVEL` in `config/board_constants.py`); only the
gain-tuning half of item #7 is resolved here.

Note also that `config/odrive_config.py`'s own hardcoded Section 1 gain values (used only if
the script is re-run from an erased board) were deliberately **not** updated to match — doing
so wasn't part of this session's scope, and re-running the script would currently reset gains
back to the old placeholders. Flagged here so a future erase_configuration()+re-run doesn't
silently undo this session's live tuning without someone noticing.

**Verification:** confirmed live and directly on the physical board — smooth, non-oscillating
response observed physically at each step, `save_configuration()` persistence confirmed. Not
independently verified by any automated test (there is no simulated closed-loop hardware
response to test this kind of tuning against; `core/hardware/sim_hw.py`'s dynamics are a
deliberately simple placeholder, unrelated to the real board's tuned gains).

## First real-hardware Freddy (web GUI) session — device-scan bugs found and fixed, 22 July 2026

First time the actual web GUI (backend + frontend, real hardware mode, no `ODRIVE_MOCK`) was
run against the live board rather than the mock or a standalone script. Route wiring itself
was audited first and found clean (every frontend call in `frontend/src/api/backend.js`
matches a real `backend/app/app.py` route 1:1; "Connect" in the UI is a pure Redux state
selection with no backend call, since the backend already discovers the device on every
`/api/devices` poll) — the actual problem was two real bugs in `backend/app/device_manager.py`,
both only reachable with live hardware attached, never exercised by `core/tests` or the mock.

**Symptom:** DeviceList kept showing "No ODrive device found" / stayed in a scanning loop
even with the board powered, wired, and healthy (independently confirmed via the user's own
`odrivetool` session in a separate venv: `dump_errors()` clean, `motor.is_calibrated=True`,
`encoder.is_ready=True`).

**Bug 1 — USB contention with a concurrent client.** The user's own `odrivetool` session was
still open in another terminal, holding an exclusive fibre/USB connection. `odrive.find_any()`
in the backend's process collided with it, raising `usb.core.USBError: [Errno 19] No such
device` from inside `fibre/usbbulk_transport.py`'s `bulk_device.init() -> dev.reset()`. Not a
bug in this project's code by itself, but exposed bug 2 below: this failure was completely
invisible — no log line anywhere, `/api/devices` just returned `[]`, identical to "genuinely no
device attached." Confirmed the root cause by bypassing `device_manager._find_any()`'s
`except Exception: return None` and calling `odrive.find_any()` directly in an isolated
script — reproduced the exact traceback, which disappeared once the user closed `odrivetool`.

**Bug 2 (the real fix) — self-contention between concurrent `/api/devices` polls.** Even after
`odrivetool` was closed, a single successful `discover_and_index()` was immediately followed
(~0.8s later, well inside the frontend's 3s poll interval) by a *second* discovery call failing
with the same `Errno 19`/`Errno 2` USB error. Root cause: `odrive.find_any()` performs a real
USB bus reset on every single call (`fibre.usbbulk_transport.discover_channels() ->
bulk_device.init() -> dev.reset()`), and the Flask dev server runs `threaded=True` (needed for
the websocket routes, Session 2), so nothing prevented two overlapping `/api/devices` requests
from both calling `_find_any()` at once — one request's bus reset yanked the device out from
under the other's in-flight open. Fixed by adding `_discovery_lock` (`threading.Lock`) around
the real (non-mock) `odrive.find_any()` call in `device_manager._find_any()`, serializing all
USB discovery/reset operations backend-wide. Also added a `log.warning(...)` in the
`except Exception` branch so a future USB-level failure shows up in the backend log instead of
being silently indistinguishable from "no device."

**Bug 3 (found incidentally, fixed alongside) — serial number format mismatch.** ODrive's raw
`.serial_number` attribute is a 48-bit int; `device_manager.serialize_device()` was doing plain
`str(ser)`, which prints the *decimal* value. Every other ODrive tool (odrivetool, the physical
board, the ODrive community/docs) displays it as lowercase hex with no `0x` prefix — confirmed
directly: the user's `odrivetool` session showed serial `367836843335`, which is exactly
`hex(59889938608949)` (the raw int backend was reading) with the `0x` stripped. Cosmetic on its
own, but the mismatched format would have made the connected board in the UI look like a
different device than the one confirmed via odrivetool. Fixed with a shared `_format_serial()`
helper (`format(ser, "x")`) used consistently in `serialize_device()` (the `/api/devices`
response), `discover_and_index()`'s internal cache key, and `attach_or_get()`'s serial
comparison — all three had to change together or the cache key/lookup would have mismatched
against the now-hex `serial_number` the frontend sends back on later `/api/devices/<serial>/...`
calls, silently forcing a full (and now-locked, so serialized-but-still-wasteful) re-discovery
on every single device request instead of reusing the cached handle. Affects the mock device
identically (`mock_odrive.py` also stores `serial_number` as a raw int, `0x123456789abc`).

**Not a bug, ruled out:** the board's `fw_version_major/minor/revision` reading `0.0.0` is
real and stable (re-checked with a 0.5s settle delay after connect, unchanged) — this board's
firmware wasn't tag-versioned at build time, a known ODrive quirk for source-built firmware.
Already handled correctly by `board_constants.check_firmware()` (warns, does not block the
connection) — no change needed.

**Verification:** `python -m py_compile backend/app/device_manager.py` clean. Live: backend
restarted with the fix, polled `/api/devices` 5+ times over 15s (with the real frontend also
polling concurrently in an open Safari tab, i.e. under the exact concurrent-access conditions
that caused bug 2) — 100% clean `200` responses, zero USB exceptions in the backend log,
`serial_number: "367836843335"` matching the user's `odrivetool` session exactly, `axis0.
current_state`, `motor.is_calibrated`/`encoder.is_ready` all read correctly from the same
connection. Not covered by `core/tests` (device_manager.py is backend-only, outside `core/`,
and this class of bug is inherently only reproducible with real concurrent hardware access —
the mock device has no USB bus to contend over). No motor movement, calibration, or axis state
change was performed at any point during this diagnostic session — read-only property reads
only (`vbus_voltage`, `serial_number`, `fw_version_*`, `axis0.current_state`, `motor.
is_calibrated`, `encoder.is_ready`).

## Two-connection conflict actually fixed (open TODO(2A) resolved), + one-click launcher, 22 July 2026

Follow-up to the same session above. Live testing of the Control tab surfaced the exact
scenario the `# TODO(2A)` comment in `core/hardware/odrive_hw.py` had been flagging since
Session 2: clicking Start opened a **second, independent** `odrive.find_any()` connection
(inside `OdriveHardware.connect()`) while the sidebar's per-device telemetry websocket
(`backend/app/telemetry.py`, via `device_manager`'s connection) was already open. Since
`odrive.find_any()` performs a real USB bus reset every call (same mechanism as the earlier
device-scan fix), starting a Control run reset the bus out from under the sidebar's
already-open connection, corrupting it. Symptom the user hit: after a run auto-stopped on a
real hardware error, the Control tab correctly showed "Session auto-stopped" + the decoded
errors (that panel reads `ControlSession`'s own, unaffected connection) — but the sidebar
showed `Axis 0 State: UNDEFINED` / `Error: None`, because *its* connection had silently broken.
The only workaround found live was physically disconnecting/reconnecting the board, since there
was no way to get the sidebar's connection working again short of a fresh discovery.

**Fix — dependency injection, not merging the two systems.** `core/` is not allowed to import
`backend/` (see `core/README.md`'s split rule; also the actual reason a fully-merged
single-connection-manager design was rejected here). Instead, `OdriveHardware.__init__` gained
two optional hooks, both no-ops by default so standalone/test usage
(`core/tests/`, `core/README.md`'s snippets) is unchanged:

- `find_any_fn(timeout) -> odrv | None` — how `connect()` obtains a handle. Default: the
  original `odrive.find_any(timeout=...)`.
- `lock_provider() -> context manager` — resolved fresh on every hardware call (never cached),
  wrapping `get_state`/`set_mode`/`set_velocity_target`/`set_torque_target`/`get_errors`.
  Default: `contextlib.nullcontext()`.

`backend/app/device_manager.py` gained two new functions to inject:

- `get_shared_handle(timeout)` — get-or-create: returns the already-cached device if
  `_device_index` has one (the common case, since the sidebar's own 3s poll usually already
  discovered it), with **zero** extra `find_any()`/bus-reset calls; only calls `_find_any()`
  (already serialized by the `_discovery_lock` from the earlier fix) if nothing is cached yet.
  Unlike `discover_and_index()`, it never clears an existing entry — it must never disturb an
  already-good connection.
- `get_shared_io_lock()` — returns `io_lock(serial)` for whatever's currently cached (or a
  no-op if nothing is), the same per-device `RLock` `backend/app/telemetry.py` already uses for
  the sidebar/Inspector's own reads/writes/commands. Resolved fresh each call, not cached by the
  caller, so it can't go stale if the underlying device changes.

`backend/app/control_routes.py` builds the real-hardware factory as a small closure injecting
both (`_real_hardware_factory()`), and constructs `control_session` with
`{**DEFAULT_HARDWARE_FACTORIES, "real": _real_hardware_factory}` instead of relying on
`ControlSession`'s own default (which is the plain unconfigured `OdriveHardware` class). Sim
mode (`SimHardware`) is untouched — pulled straight from `DEFAULT_HARDWARE_FACTORIES`.

**Deliberately NOT locked: `stop()`.** `core/control/session.py`'s `ControlSession.stop()` is
documented and tested (`test_stop_reaches_hardware_even_if_telemetry_thread_wedged`) to reach
`hardware.stop()` even if something else is wedged inside a `get_state()` call — that's the
whole point of calling it before the session lock. Gating `OdriveHardware.stop()` behind the new
shared lock would reopen that exact hole for real hardware: a stuck Inspector/telemetry read
holding the lock could block an emergency stop. Accepted tradeoff instead, documented in
`stop()`'s own docstring: it stays unlocked, so a stop() landing in the same instant as another
thread's locked read *could* interleave at the USB protocol level — narrow window (the other
side's critical sections are single scalar property reads/writes, not long operations), and
preferred over a stop() that can hang.

**Verification:** `python -m py_compile` clean on all three changed files. Full `core/tests`
suite still **69/69 passing** (nothing in it exercises the new injection hooks directly since
they're backend-only wiring, but confirms `OdriveHardware`'s default/standalone behaviour —
what those tests actually use — is unchanged). Backend restarted clean via the new launcher
(see below); `/api/control/status` (sim, default) still returns a clean idle state; `/api/devices`
still returns `200`/`[]` cleanly. **Not yet verified against the real board with an actual
Control run** — at fix time the ODrive was off the USB bus again (session started with the
board unpowered/disconnected; same raw-`pyusb`-VID-absent signature as the very first diagnostic
earlier in this session), so the live "does the sidebar now stay correct after a real auto-stop"
check is deferred to the next session with the board actually connected. Logged here rather than
left unstated so a fresh session knows exactly what's confirmed (code-level, sim-level) vs. still
open (one real-hardware end-to-end pass).

**One-click launcher.** Added `Start Freddy.command` (repo root, replaces the untracked, never-
committed `Start UI.command`, which defaulted to **mock** mode — `npm run mock_dev` — not real
hardware). Double-clickable from Finder: kills anything already on ports 5000/3000 (so it's
always a clean start, never layering on top of a stale backend from a previous session — which
is what had actually happened this session; the backend from ~11 hours earlier was still running
untouched), activates `.venv`, starts the backend in real-hardware mode (no `ODRIVE_MOCK`) and
the frontend, polls both until they respond, then opens Safari specifically (not the system
default browser) to `localhost:3000`. Verified live: ran it directly, confirmed both servers came
up with fresh PIDs (old ones killed first), backend `/api/backend/version` and frontend both
responding, `open -a Safari` exits cleanly. (Could not visually confirm the Safari window itself —
no display/AppleScript access in this sandboxed session — same limitation noted earlier this
session for screenshots.)

## `_find_any()` could hang forever after a mid-connection unplug — UI showed "connected" with no USB attached, 22 July 2026

Found immediately after the fix above, same session. User reported the UI showing the ODrive as
connectable/connected while the USB cable was physically unplugged. Traced live:

- Between ~11:48 and ~12:04 the board was genuinely connected — multiple real discoveries and
  three successful `POST /api/control/start` calls logged.
- At some point after 12:04:41 the board was physically unplugged (per the user). From then on,
  `/api/devices` stopped responding at all: `curl` with a 20s timeout got nothing back (confirmed
  the Flask process itself was still alive and answering non-USB routes like
  `/api/backend/version` instantly — this was one specific route hanging, not a crashed process).
- Root cause, confirmed by direct test: `odrive.find_any(timeout=1.0)` stopped respecting its own
  `timeout` argument entirely and hung indefinitely, specifically within that long-running backend
  process. Proof: killed the backend, called `odrive.find_any(timeout=2.0)` fresh in a brand-new
  process with the board in the exact same (still unplugged) physical state — returned cleanly in
  2.01s. So this was libusb/fibre-level state wedged inside the process (almost certainly from the
  board being yanked mid-connection, which is a known rough edge for libusb on macOS), not a bug
  in the timeout value itself, and not reproducible by physical state alone.
- Because `_find_any()` is called under `_discovery_lock` (the lock added earlier this session to
  stop concurrent scans from resetting the bus on each other), an unbounded hang inside it froze
  *every* other route needing device access too, backend-wide.
- **This is why the UI kept showing "connected":** `device_manager._device_index` still held the
  last real handle from before the unplug. `discover_and_index()` never got a chance to clear it,
  because it never completed. `attach_or_get()`/the new `get_shared_handle()` both return a cached
  entry without any liveness check by design (that's the whole point of avoiding a redundant
  bus-reset on every call) — so anything reading from the stale cache kept reporting success.

**Fix:** `device_manager._find_any()` now runs the actual `odrive.find_any()` call in a daemon
thread and joins it with a hard wall-clock ceiling (`_FIND_ANY_HARD_TIMEOUT_S = 5.0`), independent
of `find_any()`'s own internal timeout. If the thread is still alive after that ceiling, `_find_any()`
logs a clear warning and returns `None` — degrading to "no device found" (which correctly clears
the stale cache on the next `discover_and_index()`) instead of hanging the calling route, and
critically, releasing `_discovery_lock` promptly so the rest of the backend stays responsive. The
abandoned thread itself is a daemon and is simply left to finish or not — it doesn't block process
exit and doesn't touch `_device_index` itself (only `_find_any()`'s callers do that), so there's
nothing to clean up.

**Not fixed, and likely not fixable from this layer:** the actual libusb/fibre wedge itself. A
process restart reliably clears it (confirmed above); this fix only bounds the *symptom* (the app
hanging / lying about connection state) so a live wedge degrades to a clean, promptly-refreshing
"not found" instead of a silent, indefinite stale "connected".

**Verification:** `python -m py_compile backend/app/device_manager.py` clean. Full `core/tests`
suite still 69/69 passing. Live: restarted via `Start Freddy.command`, `/api/devices` now responds
in ~1-2s (matching genuine "no device" latency measured earlier this session) instead of hanging,
called twice in a row to confirm consistency, `/api/control/status` clean idle. Not independently
re-tested against an actual reproduced wedge (doing so would require physically yanking the USB
mid-connection again) — the fix's correctness rests on the thread/join/timeout logic itself
(standard, well-understood pattern) plus confirming the non-wedged path still behaves identically.

## The hang-fix's own lock could still pile up the whole backend under normal load — coalesced instead, 22 July 2026

Found immediately after the fix above, live, same session — worse than the original hang. The
user reported the UI showing the ODrive as connected/available with the USB physically unplugged,
the Dashboard tab frozen at all-zero values (`0.0V`, `Axis 0 State: UNDEFINED`) despite "Error
States: OK", "Enable Motor" doing nothing, and the Control tab's Start button freezing with a
"load failed" error. All four turned out to be **one cause**, not four:

- A real scan with the board actually present (plus 4 unrelated USB peripherals already on this
  Mac) legitimately takes a few seconds — `fibre`'s discovery probes *every* USB device on the
  bus, not just ODrive-vendor ones, and each unrelated device fails slowly
  (`usb.core.USBError: [Errno None] Other error` reading its config descriptor — harmless noise,
  unrelated to the board, present even during fully successful discoveries earlier this session).
- `_discovery_lock` (added earlier this session specifically to stop concurrent scans from
  resetting the bus on each other) makes every real discovery **strictly sequential**. With the
  frontend polling every 3s and a real scan sometimes taking longer than that, requests started
  arriving faster than they could drain — an ever-growing queue of blocked threads, until the
  backend stopped responding to *anything*, including `/api/control/status`, which touches zero
  USB hardware. Confirmed live: `/api/devices` timed out past 10s, `/api/control/status` also
  didn't return. This is what froze the Dashboard, no-op'd Enable Motor, and made the Control tab's
  Start button hang and eventually report "load failed".
- **This is also what caused the stale "connected with USB unplugged" display**: with `/api/devices`
  wedged in the pileup, `discover_and_index()` never got to complete a fresh scan, so it never
  cleared the stale cached device from before the unplug — the same failure mode as the hang fixed
  above, just triggered by pileup instead of a libusb wedge.
- **Compounding it further:** the backend process actually died during this. Root cause found by
  accident while diagnosing: macOS's own AirPlay Receiver (`ControlCenter`) listens on the wildcard
  `*:5000` by default. Our backend binds the more specific `127.0.0.1:5000`, and the two normally
  coexist fine — but the instant our listener goes away for *any* reason (crash, restart), every
  request silently falls through to AirPlay instead of a clean "connection refused": confirmed live,
  `curl http://127.0.0.1:5000/api/backend/version` returned a real HTTP 403 with
  `Server: AirTunes/950.7.1` — a response that looks like a live (if broken) server, not a dead one,
  making the actual failure much harder to spot. **This exact issue was already discovered and
  half-fixed once before and never finished**: `git stash list` in this repo has an untouched entry,
  `"pre-session3: stray vite.config.js port-5050 edit + .orig backup, undocumented in Session 2"` —
  someone (an earlier session) hit this same port conflict, edited `vite.config.js`'s proxy target
  to 5050 as a fix, but never updated `backend/start_backend.py` to match or documented why, so it
  was stashed as unexplained stray state rather than applied. Left untouched in the stash (not
  dropped) — this session's fix supersedes it via the proper, documented path instead of popping old
  half-applied state.

**Fixes, three parts:**

1. `device_manager.py`: split `_find_any()` into `_find_any_raw()` (the actual bounded call, no
   locking) and `_find_any()` (blocking: acquires `_discovery_lock`, for callers that need a
   definitive answer — `attach_or_get`, `get_shared_handle`). `discover_and_index()` — the sidebar's
   high-frequency poll entry point — now takes `_discovery_lock` **non-blocking**
   (`acquire(blocking=False)`): if a scan is already in flight, it returns the current cache
   immediately instead of queueing. Only one real scan is ever running at a time (still correctly
   serialized against bus-reset collisions), and every other concurrent poller gets a cheap
   snapshot instead of piling up. Bounded staleness (at most one in-flight scan's duration) instead
   of the previous unbounded queue.
2. `backend/start_backend.py` moved off port 5000 to **5050**; `frontend/vite.config.js`'s `/api`
   and `/ws` proxy targets, `frontend/src/utils/__tests__/integration.live.test.js`'s default
   `BACKEND_URL`, and the port mentioned in `README.md`/`docs/user_manual.md`/`docs/manual.html`
   all updated to match.
3. `Start Freddy.command`: updated to port 5050, and backgrounding changed from bare `&` to
   `nohup ... &` (bare `&` plus a bash-job-control `disown` was tried first and failed —
   `disown: current: no such job` — because `.command`/non-interactive shell contexts don't
   reliably have job control active; `nohup` doesn't depend on it). Matters because the backend
   dying (whatever the original cause) is exactly the failure this session hit, and the launcher
   should make backgrounded servers durable against the invoking shell's own lifecycle, not just
   against a clean intentional restart.

**Verification:** `python -m py_compile` clean on all changed Python files. `core/tests`: 69/69
still passing. Live, in order: (a) stress test — 8 overlapping `/api/devices` polls 1s apart, all
returned in ≤1.1s, `/api/control/status` answered in 23ms throughout, no pileup; (b) killed the
backend process directly and confirmed the relaunched one (via the fixed `Start Freddy.command`)
survives independently of the launching shell (checked in a separate, later command — process
still alive, port 5050 still listening, `/api/backend/version` still responding); (c) 6 more
overlapping polls against the new port, all ≤1.0s; (d) direct property read through the fixed
backend — `vbus_voltage: 14.71V`, `axis0.current_state: 1` (a real IDLE state, not "undefined"),
`axis0.error: 0`, `motor.is_calibrated: true`, `encoder.is_ready: true` — confirming the earlier
"0.0V / UNDEFINED / errors mysteriously OK" Dashboard symptom was entirely downstream of the
pileup/crash, not a separate bug in the property-read path itself; (e) confirmed through the
frontend's own Vite proxy (`localhost:3000/api/devices`), not just the backend directly.

## Real root cause of the recurring "connected but frozen at zero" Dashboard, 22 July 2026

The three fixes above (non-blocking coalescing, port 5050, `nohup`) were real and necessary, but
didn't fully explain a hard-reloaded, genuinely fresh page still showing `Axis 0 State: UNDEFINED`
/ all-zero values while a direct backend read of the exact same cached connection returned real
data (`axis0.current_state: 1`, `vbus_voltage: 14.89V`) moments later. Found the actual cause in
the backend log: `fibre.protocol.ChannelBrokenException`, 16 occurrences.

**Root cause:** `discover_and_index()` was calling `_find_any_raw()` — a real, unconditional USB
bus reset — on *every single poll*, even when a device was already connected and healthy. The
sidebar polls every 3s; each of those polls reset the bus regardless of whether the per-device
telemetry websocket or a Control session was actively mid-conversation with the board at that
exact moment. Enough resets in a row eventually kill the *other* connection's `fibre` channel
outright. Once dead, the same broken Python object stayed cached in `_device_index` forever (never
detected, never replaced) — so the Dashboard kept showing a "connected" device that could never
return live data again. Worse: `getattr(obj, name, default)` (used throughout `serialize_device()`)
only swallows `AttributeError` — `ChannelBrokenException` isn't one, so instead of degrading
gracefully the request crashed with an uncaught 500. This was largely self-inflicted during this
session's own diagnosis: repeatedly curling `/api/devices` to check state was itself resetting the
bus and killing whatever the frontend had open at the time — the debugging process was reproducing
the bug.

**Fix:** `discover_and_index()` now tries to answer from the cache first, with **zero** bus access
— it calls `serialize_device()` on whatever's cached and returns immediately if that succeeds, no
reset, so it can never disturb a connection something else is actively using
(`_serialize_cache_if_alive()`, wraps each cached entry's serialization in its own try/except,
dropping and logging any entry that raises rather than crashing or resurrecting a dead one). Only
if nothing's cached, or what's cached just turned out to be dead, does it fall through to a real,
resetting scan — so a genuine "no device"/unplugged/dead-connection state still self-heals on the
next poll (preserving the original "shows connected when unplugged" fix from earlier this session),
it just no longer resets a *healthy* connection for no reason. The pileup fallback path
(`_discovery_lock.acquire(blocking=False)` failing) now goes through the same dead-handle-safe
helper instead of the old bare list comprehension that crashed.

**Verification:** `python -m py_compile` clean, `core/tests` 69/69 passing. Live: 10 rapid repeat
polls (0.5s apart) against an already-connected device now return in ~4ms each (down from 1-5s+
when every poll reset the bus) with zero `ChannelBrokenException` in the log afterward; a direct
property read immediately after that polling burst still returns real live values
(`vbus_voltage: 14.86V`, `axis0.encoder.pos_estimate: -0.054`, `axis0.error: 0`) — proving the
connection survived the repeated polling instead of being reset out from under itself.

## Sim/Real toggle removed from the GUI; controller gains now tunable from the Control tab, 22 July 2026

Direct user feedback after enough hands-on time with real hardware: the Control/Profiles tabs'
sim/real switcher is never used (hardware's wired up and working now — sim served its purpose
during Sessions 2/3 before that), and it was actively in the way. Separately, the user wanted to
adjust the controller's PID gains (pos_gain/vel_gain/vel_integrator_gain) directly from the
Control tab with sliders, rather than reopening the Configuration wizard each time — described as
"very much connected to controlling the device."

**Sim/Real removal — what stayed vs what went.** The GUI toggle (colored banner + Sim/Real
buttons, identical in `ControlTab.jsx` and `ProfilesTab.jsx`) is gone, and
`backend/app/control_routes.py`'s `ControlSession` now constructs with `hardware_source="real"`
instead of `"sim"` — previously a fresh backend process silently defaulted to sim with no GUI
affordance left to notice or change it, which would have been a confusing trap the moment this
GUI change shipped. Deliberately left the backend/`core/` capability itself alone:
`core/hardware/sim_hw.py`, `ControlSession.set_hardware_source()`, and the
`/api/control/hardware-source` GET/POST route are all still there, still tested, just not wired to
any button — removing them outright would have been a bigger, riskier architectural change than
what was actually asked for (a GUI simplification), and they cost nothing left in place if a future
session ever wants scripted/headless sim runs again.

**A genuinely useful side effect, not something separately built:** `core/control/session.py`'s
`"real"` hardware factory (`backend/app/control_routes.py`'s `_real_hardware_factory`) resolves
through `device_manager.get_shared_handle()`, which itself calls the same `_find_any()` that
already transparently returns the `ODRIVE_MOCK` mock device when that env var is set. So under
`npm run mock_dev`, the Control/Profiles tabs' now-permanent "real" path drives the mock device
exactly the same way every other tab already does — `mock_dev` remains fully useful for
hardware-free UI development, it just no longer has its own separate, simpler dynamics simulator
backing it for Control/Profiles specifically. One consequence worth flagging: CSV log filenames'
`_real`/`_sim` suffix (`core/telemetry/csv_logger.py`, keyed off `hardware_source`) will now always
read `_real`, even when the underlying device is the `ODRIVE_MOCK` mock — the suffix reflects which
internal hardware factory the session used, which is now permanently the real one, not whether the
handle underneath happens to be a physical board. Documented in both user-facing manuals rather than
"fixed" (there's nothing broken to fix — the filename is accurately describing which code path ran,
just in a way that reads confusingly against the removed sim/real framing).

**Controller Gains card.** Added directly to `ControlTab.jsx`, below the existing mode/target
controls — three Chakra `Slider`s for Position Gain, Velocity Gain, and Velocity Integrator Gain,
reading/writing `axis0.controller.config.{pos_gain,vel_gain,vel_integrator_gain}` through the
existing generic `readProperties`/`writeProperties`/`invokeCommand` client in `api/backend.js` (the
same one the config wizard and Inspector already use) — no new backend route was needed, this is
exactly the single-choke-point property access the project has kept clean since Session 1 §6 paying
off for a new feature. Gains load once a device connects (via the same `s.device` Redux slice
`useConfigWizard.js` already reads from); slider drag updates the shown number continuously
(`onChange`) but only writes to the device on release (`onChangeEnd`) — dragging is many events per
second and writing on every one of them would flood the USB connection for no benefit, a pattern
already established in the Inspector's own setpoint sliders (`PropertyTree/PropertyItem.jsx`).
Slider ranges (0–20 / 0–0.3 / 0–0.5) are centered around the values already live-tuned at the bench
21 July 2026 (`config/board_constants.py`: 6.0 / 0.05 / 0.1) with headroom either side, not
arbitrary defaults. Added a "Save to NVM" button (`save_configuration`) since a live-tuned gain with
no way to persist it would just revert on the next power cycle — disabled while a Control or
Profiles session is running, since `save_configuration` reboots the board and would otherwise kill
an active run out from under the user.

**Verification:** `npx eslint .` clean across the whole frontend (zero warnings). `npx vitest run`:
40/40 passing, 2 skipped (live-hardware-only integration tests, expected, unaffected by this
change). Live: the user's own dev servers were already running against a connected real board at
the time of this change — deliberately **not restarted**, to avoid disturbing whatever state the
live session was in; Flask's debug reloader and Vite's HMR picked up the backend/frontend edits
automatically (confirmed via the backend log: `GET /api/control/hardware-source` returned
`{"hardware_source": "real"}` post-edit, proving the reload took effect). A separate, passive
headless-Chrome tab (new browser process, isolated from the user's own open tab — never touched
Start/Stop/sliders, only navigated between tabs and read the DOM) confirmed: no "SIM" or "REAL
HARDWARE" text anywhere on Control or Profiles, the Controller Gains card renders on Control and
correctly shows a "no device" state in that fresh tab's own unconnected session, and zero
console/page errors.

**Docs updated to match**, `docs/user_manual.md` and `docs/manual.html` (its styled HTML twin,
kept in sync by hand — not auto-generated): intro reframed from "Session 3, no hardware wired" to
reflect that real hardware is now wired and primary; §2.4 Control rewritten (three modes, no
sim/real step, new Controller Gains subsection); §2.5 Profiles' sim/real line trimmed; §3's CSV
filename note updated per the `_real`-always point above; §4 renamed from "Sim vs Real" to "Running
with vs without hardware" and rewritten to distinguish the two independent sim mechanisms
(`ODRIVE_MOCK`/`mock_dev`, backend-level, untouched here, vs. the now-removed per-tab `ControlSession`
simulator) so a future reader doesn't conflate them. Left alone (out of scope for this change,
pre-existing drift from other sessions, flagged for a future pass rather than silently fixed here):
both manuals' "seven tabs"/"Session 3" framing predates Position mode and the sidebar's
Reset/Restart-backend buttons, and §5's "two-simultaneous-connection" rough edge in both manuals was
already resolved by the two-connection-conflict fix earlier in this same log (22 July 2026) but
still reads as unresolved.

---

## Exercise tab, Layer A (cable-attached positioning & safety) — 23 July 2026

Built per `exercise_tab_build_spec_layerA.md` (source WHAT doc:
`exercise_tab_WHAT_plan.md`). Layer A only — no force feedback, no
concentric/eccentric logic, no isokinetic mode. Full detail (states,
constants, test coverage) already reported at the mid-session checkpoint;
this entry is the durable record.

### Architecture deviations from spec §2

The spec was written without the codebase in front of it and said so
explicitly (§0). Four real deviations from its proposed §2 architecture,
each forced by something only visible in the actual code:

1. **Home/max live in a new `core/cable/state.py::CableState`, not inside
   `ExerciseMode`.** `core/control/session.py::ControlSession.stop()` sets
   `self._mode_handler = None` on every stop — destroying whatever a
   `BaseMode` instance owns (this is exactly how `ProfileMode`'s phase
   detector/rep counter are meant to work: fully rebuilt on every `start()`).
   But spec §3.5 requires "Reset Position" to be available *while idle*,
   which only makes sense if a still-valid home reference can survive a
   Stop — contradicting the mode-handler-owns-everything model. `CableState`
   is constructed once in `backend/app/control_routes.py`, the same process
   lifetime as the `control_session` singleton, and injected into
   `ExerciseMode`.
2. **`ControlSession` gained an optional `mode_factories` constructor
   parameter** (`core/control/session.py`), mirroring the existing
   `hardware_factories` injection precedent exactly, so `CableState` can be
   threaded into a fresh `ExerciseMode()` on every `start()` without
   `ControlSession` needing to know `CableState` exists. Default
   (`MODES_BY_NAME`) preserves velocity/torque/position/profile exactly as
   before — confirmed via full regression, not just by inspection.
3. **`ExerciseMode` calls `hardware.set_mode()` itself, from
   `apply_target()`/`tick()`, whenever the action changes**, rather than
   `ControlSession` calling it once at `start()` as every other mode
   assumes. Exercise is the first mode that needs to move between ODrive
   control modes *within* one session (velocity for homing, torque for
   max-extension hold, position for length moves) — the existing contract
   (`hardware.set_mode(mode_handler.hardware_mode)` called exactly once in
   `ControlSession.start()`) never had to support that. No change to
   `ControlSession` was needed for this part specifically — `apply_target()`/
   `tick()` already receive the live `hardware` reference.
4. **`calibrate_k` and `reset_position` bypass `ControlSession`/`ExerciseMode`
   entirely** — implemented as direct `backend/app/exercise_routes.py`
   operations against `CableState` (`calibrate_k` also reads the last
   `ControlSession` telemetry sample for the current position, but doesn't
   route through `set_target()`). Neither needs the motor moving (spec
   §3.3, §3.5), and `reset_position` specifically *must* work when nothing
   is running at all — routing it through `ControlSession.set_target()`
   would be impossible in that state (`set_target()` raises if
   `not self._running`).

One thing the spec got right that turned out load-bearing: §2.3's
instruction to use REST polling, not the websocket, wasn't a new decision
this session had to make — `frontend/src/hooks/useControlTelemetry.js` had
already abandoned `/ws/control-telemetry` for exactly the reason the spec
anticipated (Werkzeug/flask-sock's close-path race). `useExerciseStatus.js`
follows that same precedent directly.

### A gap the spec couldn't have seen: no runtime current-limit control

Nothing in `core/hardware/interface.py` let any existing mode change the
ODrive's current limit at runtime — `OdriveHardware`'s torque clamp
(`_TORQUE_LIMIT_NM`) is computed once at import time from
`board_constants.MOTOR_CURRENT_LIM` and never touches the live
`axis.motor.config.current_lim` register. Homing needs exactly this (spec
§3.1, §4 item 4: a reduced current limit during the blind reel-in, restored
after). Added `HardwareInterface.set_current_limit(amps)` (+ `OdriveHardware`
writing `axis.motor.config.current_lim` directly, `SimHardware` storing the
value for interface conformance/test assertions only — deliberately **not**
fed into the sim's dynamics, since `ProfileMode`'s own docstring already
documents the sim's `TorqueMode` as intentionally unclamped, and adding a
second clamp there for this one caller would be new sim behaviour nothing
else expects, not something Layer A actually needs).

**Restore-on-every-exit-path, with a backstop.** `ExerciseMode` restores the
limit on all three homing exit paths (success, fault, abort) — each covered
by its own test in `core/tests/test_exercise_mode.py`. But a global Stop
mid-homing (the always-available safety path, spec §4 item 7) tears the
whole `ControlSession` down — `hardware.stop()` then `disconnect()` — before
`ExerciseMode`'s own cleanup would run, so on **real** hardware the lowered
limit stays live in the device's RAM (not a hazard: a *lower* limit is
strictly more conservative, and every write is a live-only, not a
`save_configuration()`, register) until something else touches it. Fixed
with a reassert-on-connect backstop: `OdriveHardware.connect()` now writes
`MOTOR_CURRENT_LIM` unconditionally on every fresh connection, so the very
next Control/Profiles/Exercise session — regardless of what a previous one
left the board at — starts from the documented default. This is a real,
intentional behaviour change to `connect()`, which every tab shares; flagged
per the task's "verify Control/Profiles unchanged" instruction. In the
common case (nothing else ever changes `current_lim` away from
`MOTOR_CURRENT_LIM`) it's a no-op write, invisible in practice.

### Persistence split (spec §6) — confirmed by test, not just by design

`CableState.home_turns` / `max_turns` / `marked_max_turns` are plain Python
attributes, never written to disk — a freshly-constructed `CableState` (i.e.
every backend process start) is un-homed by construction, not by a separate
"reset on boot" step that could be forgotten. `k` persists to
`config/spool_calibration.json` (gitignored — bench/physical-spool-specific
runtime state, not source; `SPOOL_CORRECTION_K_DEFAULT` is the fallback when
it's absent or corrupt). `core/tests/test_cable_state.py::
test_k_persists_across_a_fresh_instance_simulating_backend_restart` is the
test that actually exercises this: constructs a second `CableState` against
the same sidecar path and asserts `k` survives while `home_turns`/`max_turns`
do not — the closest a hardware-free test can get to simulating an actual
backend restart.

### Constants chosen (spec §5) — reasoning

All derived from this board's live config as of 23 July 2026:
`MOTOR_CURRENT_LIM=15.0A`, `CONTROLLER_VEL_LIMIT=2.0 turns/s`,
`TRAP_TRAJ_VEL_LIMIT=1.0 turns/s`, `SPOOL_RADIUS_M=0.05m` (still a
placeholder — open item #2, unaffected by this session).

- **`HOMING_CURRENT_LIMIT_A = 3.0`** — ~3.75x above the 0.8A detection
  threshold (comfortable margin against noise), ~5x below the 15A operating
  limit (a snag during the blind reel-in phase can't develop meaningful
  torque).
- **`HOMING_VELOCITY_TURNS_S = 0.15`** — well below both
  `CONTROLLER_VEL_LIMIT` and `TRAP_TRAJ_VEL_LIMIT`; at `SPOOL_RADIUS_M`
  this is ~4.7 cm/s of cable, chosen to be slow enough to watch and abort by
  hand on the first live attended run (spec §10), not tuned against any real
  cable dynamics yet.
- **`HOMING_DEBOUNCE_SAMPLES = 5`** (100ms at 50Hz) and
  **`HOMING_STARTUP_GRACE_S = 0.3`** (15 ticks) — both "tens of ms" as the
  spec suggested, sized to filter single-sample transients / clear BLDC
  inrush without materially delaying a real detection.
- **`HOMING_MAX_TRAVEL_TURNS = 50.0`** and **`HOMING_TIMEOUT_S = 90.0`** —
  the time bound is the practically tight one (covers a generous 3m
  worst-case reel-in at `HOMING_VELOCITY_TURNS_S` with margin); the travel
  bound is a deliberately loose backstop (~15.7m) since real cable machines
  run well under 3m.
- **`CALIB_HOLD_FORCE_N = 3.0`** — single-digit Newtons per spec, trivially
  overcome by hand, enough to keep lightweight cable/webbing taut.
- **`MAX_EXTENSION_SAFETY_MARGIN_M = 0.05`** — 5cm, as suggested.
- **`MAX_EXTENSION_MIN_TRAVEL_TURNS = 0.5`** (new, not in the spec's table —
  needed to make §3.2's "implausibly close to home" rejection concrete) —
  ~15.7cm of cable.
- **`POSITION_GUARD_TOLERANCE_TURNS = 0.05`** (new — needed to make §3.4's
  runtime-guard tolerance concrete) — ~1.57cm of cable; small enough to
  catch real problems quickly, larger than ordinary position-control
  settling/overshoot. Also reused as the length-move completion tolerance in
  `ExerciseMode`, rather than inventing a second small-position epsilon.
- **`SPOOL_CALIBRATION_MIN_THETA_M_RAD = 1.0`** (new) — below this, `k`'s
  contribution to the length calculation is small enough relative to
  measurement error to be unreliable to back out (spec §3.3's guard).
- **`SPOOL_CORRECTION_K_BOUNDS = (-0.0005, 0.0005)`** — **tightened from an
  initial `(-0.01, 0.01)` guess.** The round-trip property test in
  `core/tests/test_geometry.py` caught that a `k` *within* that looser bound
  (e.g. `-0.01`) makes `r_eff = r0 + k*theta` hit zero within about one turn
  of travel — a legitimately "plausible-range" value would have silently
  broken length calculations almost immediately. Re-derived from keeping
  `r_eff` comfortably positive across ~16 turns of travel (`r0 / 0.0005 =
  100 rad`), well beyond any realistic run. This is the one place the
  synthetic tests changed a chosen value, not just validated it.
- **`MOTOR_TORQUE_CONSTANT`: `0.06` → `0.516875`** (`8.27 / 16`, ODrive's
  published hoverboard-motor KV fallback) — spec-mandated (§5, carried over
  from Layer B WHAT planning) regardless of Layer A scope, since Layer A's
  §3.2 force→torque conversion depends on it. **This is not
  Exercise-tab-local**: `_TORQUE_LIMIT_NM` in `core/hardware/odrive_hw.py`
  (`MOTOR_CURRENT_LIM * MOTOR_TORQUE_CONSTANT`) is Control/Profiles'
  `TorqueMode`/`ProfileMode` clamp ceiling too — it raises from ~0.9 Nm to
  ~7.75 Nm, and every `torque_est` reading/CSV column changes for the same
  measured current. No existing test hardcoded the old value (checked), so
  nothing broke, but this is a real, visible, spec-required behaviour change
  on Control/Profiles, not an Exercise-tab side effect. Commented in
  `board_constants.py` as a fallback estimate, not a bench-measured value —
  the hand-spin KV measurement (open item #13) remains the trustworthy path.

### Safety-model choices not explicit in the spec

- **Manual reset's idle-gate** (spec §3.5: "no session running, no homing in
  progress") is implemented in `exercise_routes.py` as: reject if an
  Exercise session is running at all (`control_session.status()['running']
  and status['mode'] == 'exercise'`), regardless of sub-action. The spec's
  parenthetical reads as two conditions; treating "session running" as the
  single, simpler gate is stricter (blocks reset even while merely "armed/
  idle" mid-session) and avoids a second, redundant sub-action check.
- **Re-homing invalidates a previously-set max** (`CableState.latch_home()`
  clears `max_turns`/`marked_max_turns`). Not explicit in the spec, but
  follows directly from its own stale-reference rationale (§4): a max marked
  against the old home reference can't be trusted once that reference is
  gone, since re-homing only happens because something about the physical
  setup may have changed.
- **Runtime guard violations reuse the existing "raise inside `tick()`"
  auto-stop path** (`ProfileMode.compute_torque()` raising already goes
  through this — `ControlSession`'s telemetry loop try/except treats a
  raising mode identically to a hardware read failure: auto-stop, `errored`,
  `error_message` surfaced). Reused rather than adding new plumbing;
  satisfies spec §4 item 6 with an already-tested mechanism.

### What the DoD's "backend routes" item didn't get: formal pytest coverage

`backend/app/exercise_routes.py` (like `control_routes.py` before it) has no
dedicated pytest file — this project has no established backend-level test
infrastructure at all (`find backend -iname "test_*"` returns nothing; the
existing split is "core/ is unit tested, backend/ is a thin, manually
verified adapter," per `control_routes.py`'s own docstring). Verified
instead via the Flask test client end-to-end (start → home → abort → stop →
reset) and, separately, in a real browser against the running dev servers
(see `docs/progress.md`). Every route beyond argument parsing and two
idle-gate checks delegates to `core/cable/`/`core/control/session.py`, both
already covered there.

### Housekeeping: pre-existing uncommitted diffs

Several files this session needed to touch (`config/board_constants.py`,
`core/hardware/odrive_hw.py`, `core/hardware/interface.py`, etc.) already
had uncommitted changes sitting in them from earlier bench sessions (gain
tuning, the 10A→15A current-limit bump — all already narrated earlier in
this log and in `docs/progress.md`, just never committed). Asked the user
how to handle this rather than deciding unilaterally; chosen: fold together
rather than surgically split hunks. Commits from this session may therefore
contain both Layer A work and carried-forward bench-session content in the
same commit — called out explicitly in each affected commit message.

---

## Exercise tab, Layer B Session B1 (concentric force feedback) — 23 July 2026

Built per `exercise_tab_build_spec_layerB.md`. Session B1 only — concentric
resistance (constant force + isokinetic) and the safety machinery around it.
Eccentric (B2) is explicitly out of scope and gated behind B1 being
validated on real hardware with a real person, not merely behind B1 being
merged.

### §2 preconditions — resolution

All four were unmet when this session started; reported to the user and
stopped rather than working around them (per explicit instruction). Result:

- **§2.1 (Layer A validated live with a cable attached): still unresolved.**
  The user explicitly authorized proceeding with the build/sim-test path
  anyway, deferring the live validation itself to their own bench session —
  this is *not* the same as the precondition being satisfied, and the DoD
  checklist below reflects that honestly rather than marking it done.
- **§2.2 (KV/torque-constant measurement, open item #13): still
  unresolved.** Per the spec's own carve-out, B1 was built and sim/unit-
  tested anyway; the UI's uncalibrated-estimate label (§10.3) is the
  mitigation, not a substitute for the measurement.
- **§2.3 (spool radius) and §2.4 (regen configuration): resolved**, with
  real, user-provided values — `SPOOL_RADIUS_M = 0.035` (ruler measurement),
  `BRAKE_RESISTANCE = 2.0` (confirmed against the physical resistor, 50W
  rated), `DC_MAX_NEGATIVE_CURRENT = -0.5` (tightened from an unjustified
  -3.0 placeholder), `MAX_REGEN_CURRENT = 0` (confirmed correct as-is). Full
  reasoning for each in `config/board_constants.py`'s comments and repeated
  below.

### Architecture deviations from spec

1. **Separate `ForceMode` (`core/cable/force_mode.py`), not an `ExerciseMode`
   extension — the §8 decision.** `ExerciseMode` is already ~250 lines
   dedicated to Layer A's brief, one-shot calibration actions and switches
   ODrive control modes within a session. `ForceMode` is structurally
   different: fixed to torque control for its *entire* lifecycle (spec §3,
   the load-bearing decision of the whole layer) but runs a sustained,
   continuous, multi-component computation every tick (governor, let-go
   detector, power limiter, ramps). Folding the second shape into the first
   class would have mixed two different design shapes in one file. `ForceMode`
   registers as a sixth mode name (`"force"`) on the same shared
   `control_session`, mutually exclusive with `velocity`/`torque`/`position`/
   `profile`/`exercise`, sharing `CableState` via the same `mode_factories`
   hook Layer A added. Its live status reuses `/api/exercise/status`
   unchanged (already generic).
2. **FAULT is deliberately NOT the raise-inside-`tick()` auto-stop path**
   Layer A's runtime guard uses. Spec §4.6 frames "resume" as lighter than
   re-homing, returning "the state machine" — not a fresh session — to
   ARMED. So a let-go event calls `hardware.stop()` directly from inside
   `tick()` (immediate, not ramped) while `ControlSession` keeps running;
   only Layer A's runtime guard (a more severe, position-is-wrong failure)
   triggers the existing full-session-stop mechanism. Both coexist in
   `ForceMode.tick()`.
3. **Ramps implemented as a fixed slew rate, not a fixed duration
   re-normalized per target.** Spec §4.2's literal text is "force ramps from
   zero to target over `FORCE_RAMP_IN_S`." Implemented instead as
   `rate = FORCE_MAX_N / FORCE_RAMP_IN_S` (N/s), applied every tick via
   `core/cable/ramps.py::slew_toward()`. This handles engage, disengage, and
   a live mid-`ENGAGED` retarget with one mechanism — no ramp-start
   timestamp to track, no special-casing a target that changes mid-ramp —
   and a target smaller than `FORCE_MAX_N` always ramps in *faster* than the
   literal `FORCE_RAMP_IN_S`, never slower. Strictly safer than the literal
   reading, never less safe.
4. **Hold detection composes with `PhaseDetector` rather than extending
   it.** `ForceMode` watches for `PhaseDetector`'s existing `TOP_HOLD`/
   `BOTTOM_HOLD` classification and adds a duration timer
   (`HOLD_DURATION_S`) on top, rather than re-implementing threshold/
   hysteresis logic a second time. The interface fit cleanly — no changes
   needed to `core/profiles/detectors.py`. Per the spec's own instruction,
   noting this here since it was worth confirming explicitly rather than
   silently duplicating detection logic.
5. **`velocity_m_s_from_turns_s()` (`core/cable/geometry.py`) deliberately
   ignores the k-corrected effective radius**, using the fixed `r0` only —
   consistent with `force_to_torque()`/`torque_to_force()`
   (`core/profiles/units.py`), which already ignore `k` entirely
   (`SPOOL_RADIUS_M` is the only radius either function ever sees). Velocity
   does the same for consistency: `k`'s spool-wrap correction only ever
   applies to *length* (position), not to the force/velocity/torque
   conversions this layer's safety math depends on.
6. **HOLDING is terminal-ish in B1, by design, not by omission.** Per spec
   §4.1's own framing, `HOLDING` does not automatically transition back to
   `ENGAGED_CONCENTRIC` if the user resumes pulling — it stays at
   `FORCE_MIN_N` until an explicit disengage. B2 is where this becomes the
   eccentric launch point; building any automatic exit now would be scope
   creep ahead of that gating.
7. **`_force_n_param` serves double duty** (constant mode's flat target,
   isokinetic's `F_base`) rather than two separate fields. An earlier draft
   had two fields; the isokinetic one was never updated from the `engage`
   action's `force_n` parameter, silently stuck at the `FORCE_MIN_N`
   default forever regardless of what was requested. Caught by
   `test_no_windup_on_sustained_hold_still` (expected 20N, got 5N) before
   it shipped — see `docs/progress.md` for the fuller account. Fixed by
   unifying into one field, which is also the conceptually correct model:
   both are the same user-facing "how much resistance" input.

### §3.1 — `enable_torque_mode_vel_limit`, open item #8 closed

Disabled (`ENABLE_TORQUE_MODE_VEL_LIMIT = False`), replaced by the software
governor (`core/cable/governor.py`), reasoning exactly as spec §3.1 lays
out: ODrive's default torque-mode velocity limiter directly fights a
constant-force profile (pull faster, get less force), and disabling it
removes ODrive's own last-resort protection against a runaway torque
command in an unloaded direction — software (the let-go detector, the
velocity ceiling it enforces) now owns that entirely.

**Applied as a runtime-owned property, not a one-time NVM write via
`config/odrive_config.py`.** `OdriveHardware.set_mode()`'s `TORQUE` branch
writes it on every torque-mode entry — the same relationship `connect()`
already has with `current_lim` (Layer A). This means it applies uniformly to
Control tab's `TorqueMode`, Profiles' `ProfileMode`, and Layer B's
`ForceMode` alike, resolving the open item project-wide rather than
Force-mode-locally, which matches how the item was originally framed in
`core/control/modes.py`'s own TODO (against Profiles, before Layer B
existed). Deliberately not written into `config/odrive_config.py`: that
script is the frozen "erase and reconfigure from scratch" script (its own
`dc_max_negative_current`/`brake_resistance` values are still the old
pre-Layer-B placeholders, confirmed not auto-synced from live bench tuning)
— adding a second, potentially-drifting copy of this property there would
recreate exactly the kind of two-places-that-can-disagree risk that caused
the `enable_brake_resistor` confusion in the first place.

**Live-board confirmation — action item, not yet done.** The property path
(`axis{n}.controller.config.enable_torque_mode_vel_limit`, BoolProperty, rw)
is corroborated only by the bundled `odriveApiReference05x.json` (labeled
v0.5.6, not this board's exact v0.5.1) — unlike `brake_resistance`/
`dc_max_negative_current`/`max_regen_current`, which are confirmed via
`config/odrive_config.py`'s own live-run comments, nothing in this codebase
has exercised this specific property against the real board yet. It is
written unconditionally on every torque-mode entry (`OdriveHardware.
set_mode()`), so if the name is wrong on this firmware it will raise loudly
the very first time *any* mode enters torque control — Control tab's Torque
mode included, not just Layer B. **Action item for the bench session:**
confirm this property exists via `dir(axis0.controller.config)` before or
during that first torque-mode entry, the same live-`dir()` discipline
already used to catch the `enable_brake_resistor` mistake.

### §5.2 — break-even power analysis, real constants

Formula: `v_breakeven ≈ 1.5 · F_cable · r_spool² · R_phase / Kt²`, at
`r_spool = 0.035` (measured), `R_phase = 0.38` (measured, consistent across
every calibration run), `Kt = 0.516875` (**still the open-item-#13
estimate**).

| F | v_breakeven | P_copper (velocity-independent) |
|---|---|---|
| 50N | 0.131 m/s | 6.5W |
| 100N | 0.261 m/s | 26.1W |
| 150N | 0.392 m/s | 58.8W |
| 200N | 0.523 m/s | 104.5W |

**Correction made during this session, before reporting it:** the first
pass at "does the software power limiter ever actually activate" used
`CONTROLLER_VEL_LIMIT` as the achievable-velocity ceiling. That was wrong,
independent of an unrelated external bench re-tune that happened to change
that constant's value (2.0 → 10.0 turns/s) partway through this session.
`CONTROLLER_VEL_LIMIT` governs ODrive's position/velocity control loops;
Layer B runs in torque mode with `enable_torque_mode_vel_limit=False`, so
**constant-force mode has no software velocity ceiling of any kind** —
velocity is bounded only by the user's own strength/speed. Recomputed
correctly:

- **Constant force**: `REGEN_POWER_BUDGET_W=30` is exceeded once cable speed
  passes roughly **0.56–0.73 m/s** (varies with force) — a fast but
  plausible rep speed for lighter/explosive movements. Below ~0.3–0.5 m/s
  it mostly stays inactive. The power limiter is therefore a **real, active
  behaviour during fast reps**, not a dormant formality — in constant-force
  mode it is the only thing standing between a fast rep and exceeding the
  brake resistor's budget.
- **Isokinetic**: self-limiting by construction. The governor's rising
  resistance above `ISOKINETIC_VELOCITY_TARGET_TURNS_S` keeps estimated
  regen power under ~10W even a full turn/s over target — comfortably under
  budget. The limiter essentially never needs to intervene here; the
  governor already does that job structurally.

### Constants chosen (spec §9) — reasoning

Full comments live in `config/board_constants.py`; summarized here per the
Layer A entry's standard.

- **`FORCE_MAX_N = 150`** — well below the ~221.5N structural ceiling
  implied by `_TORQUE_LIMIT_NM` (`MOTOR_CURRENT_LIM * MOTOR_TORQUE_CONSTANT
  / SPOOL_RADIUS_M`); at 150N continuous, `P_copper≈59W` regardless of
  velocity — a thermal, not regen, concern this software cannot sense
  (open item #1, no thermal sensing).
- **`FORCE_MIN_N = 5`** — the HOLDING floor and, reused, isokinetic's
  default `F_base` (one field, not two — see architecture deviation #7
  above). Same order of magnitude as Layer A's `CALIB_HOLD_FORCE_N=3.0N`,
  slightly higher since this hold happens under a real workout load.
- **`FORCE_RAMP_IN_S = FORCE_RAMP_OUT_S = 0.5`** — symmetric; see
  architecture deviation #3 for the rate-vs-duration interpretation.
- **`HOLD_DURATION_S = 0.75`** — long enough to distinguish a deliberate
  pause from a quick rep turnaround, short enough not to feel laggy.
  **Untested against a real rep** — see the first-live-run watch items
  below.
- **`ISOKINETIC_VELOCITY_TARGET_TURNS_S = 1.0`** (~22cm/s) and
  **`ISOKINETIC_GOVERNOR_GAIN = 150`** (N per turn/s above target) — a
  moderate default cap with a firm, quickly-felt wall.
- **`ISOKINETIC_VELOCITY_FILTER_ALPHA = 0.3`** — EWMA smoothing before the
  governor (spec §4.3's "filtering is likely necessary; check"). Much
  lighter than `REP_EWMA_ALPHA=0.05` (tuned for rep-boundary detection, not
  live force control) — needs to stay responsive, not just smooth.
- **`LETGO_VELOCITY_TURNS_S = 0.1`** (2x `PHASE_VEL_THRESHOLD_TURNS_S`) and
  **`LETGO_DEBOUNCE_SAMPLES = 5`** (matches `HOMING_DEBOUNCE_SAMPLES`, per
  spec's explicit suggestion). **The 100ms debounce window's real
  travel/speed budget is unvalidated against real inertia** — see the
  first-live-run watch items below.
- **`REGEN_POWER_BUDGET_W = 30`** — 50W rated, derated to 60% for sustained
  continuous duty with no forced cooling (open item #1).
- **`MAX_EXTENSION_FORCE_TAPER_M = 0.15`** — 3x `MAX_EXTENSION_SAFETY_
  MARGIN_M`, a gentle, perceptible ease-off zone starting well before the
  enforced limit. **Interaction with a fast, hard pull is unvalidated** —
  see the first-live-run watch items below.
- New, not in the spec's own §9 table: **`MOTOR_PHASE_RESISTANCE_OHM =
  0.38`** (the spec's own stated measured value) and
  **`ENABLE_TORQUE_MODE_VEL_LIMIT = False`** (open item #8, closed above).
- Two §9 table rows intentionally *not* added as separate constants:
  hold-threshold reuses `PHASE_VEL_THRESHOLD_TURNS_S`; isokinetic's force
  floor reuses `FORCE_MIN_N`. Per the spec's own reuse suggestions.

### First-live-run watch items — named, for whoever is at the bench

These are not implementation bugs — they're places the design is only as
good as an assumption about real dynamics that only live testing with a
real person can check. Cross-referenced against `exercise_tab_build_spec_
layerB.md` §14's escalation steps below; they need to survive to whoever
runs that session, which may not be this conversation.

1. **HOLDING creep at `FORCE_MIN_N`.** The let-go detector is gated to
   `ENGAGED_CONCENTRIC` only (spec §4.4) — during `HOLDING`, force drops to
   5N and nothing is actively watching for a slow, undetected reel-in the
   way concentric's dedicated debounce does. The only backstop is Layer A's
   position runtime guard, which is coarser and slower. **Watch for this
   starting at §14 step 3** (handle attached, lowest force — the first
   point `HOLDING` becomes reachable at all) **and keep watching through
   step 4** (escalating force) — HOLDING's own force stays fixed at 5N
   regardless of the engaged force level, but surrounding conditions
   (motor already warm, higher pre-hold momentum) change as force
   escalates. Watch during any *extended* hold specifically, not just the
   moment of transition into `HOLDING`.
2. **Let-go debounce at increasing force.** `LETGO_VELOCITY_TURNS_S`/
   `LETGO_DEBOUNCE_SAMPLES` (100ms) are reasoned by analogy to homing's
   debounce, not from real cable/handle inertia — there's no way to compute
   how much the spool actually accelerates in that window at higher
   commanded force without real mass/inertia data. **Validate low-force
   triggers at §14 step 3 before trusting the window at `FORCE_MAX_N`** —
   this is precisely what step 4's "escalate force gradually" is for;
   don't skip straight to high force and assume the debounce window that
   worked gently also works hard.
3. **Taper behaviour at faster pull speeds.** `MAX_EXTENSION_FORCE_TAPER_M`
   correctly solves the problem it was designed for (an abrupt full-force-
   to-fault transition at the limit) but easing off resistance *removes*
   some of the deceleration that was helping keep a fast-pulling user in
   range — plausible, not certain, that at high pull speed the taper makes
   reaching the position guard's fault *easier* to hit, not harder. **§14
   step 4 escalates force but has no dedicated step for pull *speed*** —
   noting that gap explicitly rather than assuming force escalation alone
   covers it. Test the taper deliberately at faster pulls, not just the
   first slow, careful one, and not only at the force level where it was
   first tried.

### Testing summary

`core/cable/{ramps,governor,letgo,power_limiter}.py` — 40 synthetic tests,
pure/hardware-free, written alongside the modules. `core/cable/force_mode.py`
— 29 tests (`test_force_mode.py`), covering all ten spec §6 safety
behaviours individually, including sign correctness (§6 item 10 — asserted
the sign, not just the magnitude) and an end-to-end `ControlSession` test
for global Stop mid-`ENGAGED` plus the Layer A current-limit-restore
backstop surviving it. 242/242 core tests passing throughout.

### First live run against the real board — two bugs found and fixed, 23 July 2026

The user's own first live session (real hardware, Exercise tab) surfaced two
real bugs, both fixed the same day.

**`enable_torque_mode_vel_limit` confirmed absent on this board's
firmware.** Exactly the risk flagged as unconfirmed in this file's earlier
entry — `axis.controller.config.enable_torque_mode_vel_limit` raised
`AttributeError` on the very first live torque-mode entry
(`start_max_calibration`). Because the write lived unconditionally inside
`OdriveHardware.set_mode()`'s `TORQUE` branch, this broke **every** mode
that enters torque control — not just Layer B, but Control tab's Torque
mode and Profiles' `ProfileMode` too, both of which the task explicitly
required to stay unaffected. Root cause of two symptoms the user reported
that looked separate: (1) "start max extension calibration... nothing
actually happens" — `axis.controller.config.control_mode`/`input_mode` had
already been set to torque control by the two lines *before* the crash
(so the axis did briefly enter torque control, which is why pulling the
cable felt like something happened), but the exception then aborted
`_apply_start_max_calibration` before it ever set `self._action =
"max_calibrating"` or applied the hold torque — so the backend's state
never advanced and the frontend correctly kept showing "Start Max-Extension
Calibration" instead of "Set Max Here"/"Cancel"; (2) homing worked
perfectly throughout, because homing uses `ControlMode.VELOCITY`, which
never touches this property at all.

**Fix**: the write is now wrapped in `try/except AttributeError`, logging a
warning and continuing rather than crashing the caller — the same "warn,
never crash" precedent this file already uses for a firmware property that
turns out not to exist (see the `enable_brake_resistor` entry above).
**This means open item #8 is NOT actually resolved on this board** — ODrive's
own torque-mode velocity limiter may still be live and fighting the
software governor (Layer B) or a resistance profile (Session 3), the exact
symptom the item was originally about ("pull faster, get less force").
Restoring torque mode to a working state took priority over root-causing
the correct property name/whether v0.5.1 supports this feature at all;
that remains open.

**`ControlTab.jsx` mode-sync bug**, exposed by (but not caused by) Layer A/B
adding two new modes to the shared `ControlSession`. Its own `useEffect`
synced local UI state to *any* `status.mode` the backend reported, including
`"exercise"`/`"force"` (and, latently, `"profile"` — the same class of bug
already existed before this session, just never triggered) — modes
Control's own `<Select>` has no target shape for. Symptom: after running an
Exercise session and returning to Control tab, clicking Start submitted
whatever numeric value was in Control's own target field under the wrong
mode name, producing `"Exercise target must be a dict, got 0.5"`. Fixed by
scoping the sync (and the tab's own `running` flag) to the three modes
Control's UI actually understands, with an "another mode running" warning
banner matching the precedent already used in Profiles/Exercise — the same
fix class, not new UI.
