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

### "More control" feature phase, same day (23 July 2026)

After the two bugs above were fixed, the user's next message was one long,
itemized "I want control" request — reproduced in full in `docs/progress.md`'s
matching entry. The design decisions worth recording separately from the
implementation log:

**Persistence: extend, don't duplicate.** Every new live-adjustable value
(homing threshold/velocity/current-limit, spool radius `r0`, max-extension
calibration hold force) went through the exact same mechanism the spool
correction factor `k` already used — `CableState` + the gitignored JSON
sidecar — generalized from a single hardcoded value to a `_PERSISTED_DEFAULTS`
key -> `board_constants` fallback dict. The alternative (a second config
file, or per-value ad hoc persistence) was rejected outright: these are all
the same *kind* of thing — bench/physical-spool properties the user tunes
once real hardware tells them the `board_constants.py` defaults are off —
and `k` already proved the pattern works.

**Where live-adjustability stops.** `HomingStateMachine` gained *optional*
constructor overrides (`velocity_turns_s`, `current_threshold_a` — default
`None` falls back to `board_constants`), but its other four constants
(debounce samples, startup grace period, travel-bound, timeout) deliberately
did **not** become adjustable. Neither the user's request nor the failure
mode motivating them (accidental over-travel, a homing run that never
terminates) named these; they're safety margins around the detection logic,
not calibration values the physical bench setup changes. Scope was drawn at
exactly what was asked, not "the whole homing state machine now takes a
settings object."

**Consistency gap caught before shipping: r0 in `ForceMode`.** Making `r0`
live-adjustable via `CableState.set_r0()` is only correct if everything that
converts using it actually reads the live value. `ForceMode` still called
`board_constants.SPOOL_RADIUS_M` directly in six places (torque conversion,
two velocity conversions, power limiter, regen estimate) — the setting would
have persisted correctly and displayed correctly, while every force number
the motor actually produced stayed silently wrong. Fixed by threading
`self.cable_state.r0` through all six call sites and adding an optional `r0`
parameter to `force_to_torque()`/`torque_to_force()` (default: still
`board_constants.SPOOL_RADIUS_M`, so Profiles-tab callers — which have no
`CableState` — are unaffected). A dedicated regression test
(`test_commanded_torque_uses_cable_state_r0_not_board_constants`) asserts the
actual commanded torque changes with a live-adjusted `r0`, not just that the
value is stored.

**Force Feedback range: taper both edges, but not always the start edge.**
The user's approved design (`AskUserQuestion`, "Taper off near the range
edges, like the max-extension taper") reuses the existing pure
`taper_factor()` at both the configured start and end boundaries rather than
adding a second pure function — `min()` of the two edge tapers. The one
non-obvious call: when the range's start defaults to `home_turns` (i.e. the
caller never set `start_length_m`), that edge does **not** taper, even
though it's still "an edge" of the active range in the same sense the end
edge is. Reasoning: the end-edge taper is a *safety* behaviour (easing off
before the enforced/physical limit, present since the original Layer B
build, independent of this feature) — it makes sense unconditionally,
default range or not. The start edge's taper is purely a UX smoothing
behaviour for a range the user explicitly carved out away from home; home
itself was never a "soft" zone needing deceleration (there's nothing on the
other side of it to crash into within concentric operation — homing itself
already handles that boundary), and applying it by default would have
silently made every existing caller's first few centimetres of pull
force-free. This was not a hypothetical concern — it broke seven existing
tests immediately (`test_force_ramps_in_not_instant` and siblings, which
engage and tick from a stationary position at `home_turns`, going from
"full commanded force" to "zero, taper stuck at the edge" once the first,
naive two-edge-always-tapers implementation landed) before the
`math.isclose(range_start_turns, home_turns)` guard was added. Left as an
explicit named comment at the guard site (`core/cable/force_mode.py`,
`_tick_engaged`) since the reasoning isn't derivable from the code alone.

**Move/Force layout: `AskUserQuestion`, not a guess.** Three points in this
feature phase had genuine design ambiguity affecting safety-relevant
behaviour or a real UX trade-off rather than a literal, named request:
Force Feedback's range-edge behaviour (above), whether Move and Force
Feedback should merge into one card with a mode toggle or stay separate
cards placed side by side, and whether the max-extension calibration hold
force should become a live setting at all (vs. staying a fixed constant,
since it's a safety-adjacent tension value, not just a UX number). All three
came back as the offered "Recommended" option — separate cards side by side
(they remain genuinely mutually-exclusive modes on the shared
`ControlSession`; merging would have blurred that), and yes, expose the
calibration hold force the same way homing settings already are. Recorded
here because these were decisions with real alternatives, not
straightforwardly implied by what was literally typed — unlike the homing/
r0/cable-position/collapsible-Homing items, which were named explicitly
enough to just build.

## Train tab — build spec §0 research pass, 25 July 2026

`train_tab_build_spec.md` was written from memory and said so explicitly,
asking for its §0 assumptions to be checked against real code before
building anything. They were checked; several were stale. Recorded here
per the spec's own instruction.

### §0 discrepancies found

**`ForceMode` no longer exists.** The spec assumes a standalone
`core/cable/force_mode.py`/`ForceMode` class to leave untouched. In the
actual (uncommitted) working tree it was deleted and merged into
`ExerciseMode` as of the "more control" feature phase entry directly above
this one — force feedback is now `ExerciseMode`'s `_force_state`/
`_FORCE_ACTIONS` side, gated against `_action` so Layer A positioning and
force feedback can interleave without a session stop/restart. `force_mode.py`
and `test_force_mode.py` are gone; `backend/app/force_routes.py` still
exists but is now a thin dispatcher onto the same shared `control_session`
Exercise routes use (`_status_dict()` literally calls `exercise_routes.
_cable_status_dict()`). This merge is documented only in code docstrings
(`core/cable/exercise_mode.py` lines 1-8, `backend/app/force_routes.py`,
`frontend/src/api/force.js`) — **not** in this file or in `progress.md`,
which is itself a gap worth flagging: the docs this spec was written from
were already behind the working tree before this session started.

**`MODES_BY_NAME` has four entries, not six.** `core/control/modes.py`'s
registry is `velocity`/`torque`/`position`/`profile` only. `"exercise"` is
not in it — it's injected at the `mode_factories` override passed to
`ControlSession`'s constructor in `backend/app/control_routes.py`
(`{**MODES_BY_NAME, "exercise": lambda: ExerciseMode(cable_state)}`), the
same hook this spec already correctly says Train should use. There is no
`"force"` entry at all; force feedback dispatches onto the running
`"exercise"` mode's actions, it was never a separate `ControlSession` mode.
Train follows the `"exercise"` precedent exactly: a `mode_factories`
override in `control_routes.py`, not an edit to `MODES_BY_NAME` itself.

**`core/profiles/` is not a stub.** It's Session 3's real, working
resistance-profile system (`base.py`, `bell_curve.py`, `constant.py`,
`detectors.py`, `overload.py`, `units.py`, `vbt.py`), genuinely driving
`ProfileMode`. Irrelevant correction for Train's own purposes (Train's
`train_profiles.py` was always meant to be an independent, simpler pure-math
module per spec §2, not built on this layer) but the spec's premise for
*why* it's independent ("Session 3's stub layer") was wrong — it's
independent because Train's shape (segments keyed by cable *position in
metres*, no phase/rep detection, no wrapper composition) doesn't fit
`ResistanceProfile`'s contract, not because there was nothing there to reuse.

### Design decisions this pass had to make (spec asked for reasoning, not silence)

**Move/jog torque parameter: built inside `TrainMode`, not added to
`ExerciseMode`.** Spec §3 literally says to extend `ExerciseMode`'s Move
action with an optional torque parameter. But spec §6/DoD are more specific
and more binding: "Any change to Exercise... tabs... — verify unchanged at
the end," and the DoD checkbox is "Exercise/Control/Profiles tabs confirmed
unchanged (behaviour **and files**)." Editing `core/cable/exercise_mode.py`
— the file backing the Exercise tab — to add a Train-motivated parameter
fails that checkbox even if `ExerciseTab.jsx` itself is never touched, and
makes a "confirm unchanged" DoD step meaningless. Treating §6/DoD as the
stronger constraint, `TrainMode` gets its own self-contained move/jog
action instead: a trapezoidal position move via
`hardware.set_position_target(..., torque_limit=...)`, using the *hardware
interface's* already-existing optional `torque_limit` parameter
(`core/hardware/interface.py`) that the standalone `PositionMode`
(`core/control/modes.py`, unrelated to Exercise) already validates and
passes today — `ExerciseMode._apply_move` just never wired it through. This
gives Train the same ODrive-semantics capability the spec asked for
(bounded jogging, not a raw unbounded torque command) with zero lines
changed in `exercise_mode.py`. Torque *limit* on a position move was chosen
over a raw separate torque jog because Move's stated purpose is "manual
jogging while testing" — a bounded, closed-loop trapezoidal move to a
chosen length is the safer and more conventional fit; an unbounded torque
jog is what Train's actual running mode already does every tick once a
profile is active, so a second raw-torque path in the jog panel would add
risk without adding capability.

**Max-extension guard: reuses the existing two-tier tolerance, no new
threshold.** `TrainMode`'s tick reuses `core/cable/limits.py`'s existing
`check_runtime_guard()` against `cable_state.position_guard_hard_turns` —
the same tolerance `ExerciseMode` already enforces — rather than inventing a
second, Train-specific tolerance setting. A guard violation raises inside
`tick()`, which `ControlSession`'s telemetry loop already treats as a
hardware-stop-worthy failure for every mode (`core/control/session.py`'s
module docstring: "this also covers Session 3's ProfileMode... a profile
that raises is indistinguishable from a hardware read failure") — no new
safety plumbing needed, only a new persisted boolean
(`train_max_extension_enforced`, default `True`) gating whether the check
runs at all, per spec §3's explicit instruction, added to `CableState`
alongside a `train_telemetry_buffer_s` graph-buffer-duration setting (spec
§1's own named example of a numeric default that must be persisted, not
hardcoded).

**Graph time-window bug — real root cause, for the record.** Not a
seconds/milliseconds mismatch as the spec guessed. `filterByRange()`
(`frontend/src/utils/chartDisplay.js`) is correct. The bug is upstream: both
`useControlTelemetry.js` and `useExerciseStatus.js` cap their client-side
series buffer at `MAX_CHART_POINTS = 300` **by point count**, and
`ExerciseMode`/`ControlSession` tick at 50 Hz — so the buffer holds at most
~6 seconds of real history (300 ÷ 50) no matter how long a session runs.
`MiniChart`'s `60s`/`All` range buttons silently show whatever ≤6s is
actually buffered, indistinguishable from each other, with no indication
the requested window was never really available. Train's telemetry hook
fixes this at the cause: the rolling buffer evicts by **sample age**
(against `cable_state.train_telemetry_buffer_s`), not by a fixed point
count, so the buffer's real duration is independent of tick/poll rate and
actually matches what the range selector offers.

**Numeric defaults NOT persisted, and why.** Per-jog transient parameters
(move target length, move velocity, accel/decel, torque limit) follow the
existing `ExerciseMode` Move panel precedent: live text inputs with a
sensible in-component or `board_constants`-derived default, not
`CableState`-persisted settings — they're typed fresh per action already,
the same as Exercise's own Move panel today. Only standing configuration
switches (the max-extension enforcement toggle, the graph buffer duration)
went through `CableState`. Profile *content* itself (segments/shapes/params
the user is actively authoring) is also not persisted to `CableState` —
nothing in the spec asked for saved/named profiles surviving a restart, and
the editor is itself the user-editable surface the standing rule cares
about.

## Train tab refinements, 25 July 2026

First round of user feedback after using the tab: mostly usability, one
real removal, one deferred investigation.

**Manual jog removed from Train entirely, not just decoupled.** The user's
first ask was to stop coupling Move to "Start Train session"; on reflection
they asked to remove Manual Jog from Train altogether and use the Control
tab's own Position mode instead (already has PI tuning, velocity control).
Since the jog UI was the only caller of `TrainMode`'s `"move"`/`"stop_move"`
actions, kept them around would have meant dead-but-reachable backend code
— `_apply_move`/`_apply_stop_move`/`_tick_moving`, the `"moving"` action
state, `/api/train/move`+`/api/train/stop_move`, `moveTrainCable`/
`stopTrainMove` in the API client. All removed together. `TrainMode` is
single-state again as a result (no more `"running"`/`"moving"` split) —
a genuine simplification, not just a UI change. `core/hardware/interface
.py`'s `set_position_target(torque_limit=...)` and the standalone
`PositionMode` it already fed are untouched; nothing else depended on the
jog path.

**Position mode's metres option: frontend-only, no backend change.** The
user's ask was narrow — "Position Control should be able to control the
cable position as well [as] the number of turns" — and they explicitly
said the existing Position mode behaviour (PI tuning, trapezoidal move)
already works well and shouldn't change. `PositionMode` (`core/control/
modes.py`) is generic, hardware-turns-only, with no `CableState` awareness
by design (Control tab's `ControlSession` never injects one into it, unlike
Exercise/Train). Giving it real cable-awareness server-side would have been
a much bigger change than asked for. Instead, `ControlTab.jsx` gained a
`turns`/`m` unit toggle on the Move Distance field: metres are converted to
turns client-side (`turnsDeltaFromLength()`, new in `frontend/src/utils/
cableGeometry.js` — the file was `trainGeometry.js`, renamed since it's now
genuinely shared between Train and Control) using the live `cable.r0`/`k`
read once from `/api/exercise/status`, purely for the conversion — the
turns value actually sent to `PositionMode` is identical to what a user
typing turns directly would have sent. Zero backend changes. `turns_delta_
from_length()`'s sign convention (unsigned magnitude, caller reapplies
direction) is preserved in the JS mirror for the same reason it exists in
the Python original — a negative relative move must still convert
correctly.

**Graph axes: independent per-quantity Y axes, not just adjustable ranges.**
The user asked for "adjustable axis scaling" using Position/Torque as an
example of two quantities on very different scales. Adjustable min/max
alone (`AxisRangeControl.jsx`, an `{auto, min, max}` selector shared by both
Train graphs) would still have left them sharing one axis by default. Gave
each quantity its own `yAxisId`'d Y axis instead (Position/Velocity/Torque
on the time-series chart; Planned/Actual on the force-vs-position chart) —
this alone fixes the root complaint (a small-magnitude line unreadable next
to a large-magnitude one) even with every axis left on Auto; the manual
override is the additional control the user explicitly asked for on top.
Only axes for currently-*enabled* lines render, so with just the default
line on, each chart looks exactly like a single-axis chart — no visual
regression for the common case. Found and fixed one real layout bug from
this during browser verification: a second axis stacked on the same
(`right`) side had its ticks/label clipped at the chart's edge because the
`LineChart`'s own `margin.right` didn't grow to make room for it — fixed by
computing `marginRight` from how many right-side axes are actually active,
not a fixed constant.

**Force calibration: flagged, not touched.** The user reported a real
discrepancy — displayed force (~7N) far below what's physically felt, and
planned-vs-measured force on the graphs differing by roughly an order of
magnitude (~7N planned vs ~-80N measured) — but explicitly asked to
investigate a proper calibration procedure later rather than patch it now.
No code changed for this. Worth recording the shape of the problem for
whoever picks it up: `torque_est` (and everything derived from it —
`estimated_force_n`, the "Actual (live)" curve on Graph B) is computed from
`current_iq * board_constants.MOTOR_TORQUE_CONSTANT`, and `MOTOR_TORQUE_
CONSTANT`'s own comment in `config/board_constants.py` already says it's a
"FALLBACK ESTIMATE, NOT a bench-measured value" pending a hand-spin KV
measurement (open item #13). A wrong torque constant would produce exactly
this symptom — a large, roughly-constant-factor error between commanded/
planned force (which goes through `force_to_torque()`, not `torque_est`)
and *measured* force (which does). Sign (-80N vs +7N) is a separate
question from magnitude and shouldn't be assumed to be the same root cause.

**Homing settings duplicated into Train's Settings section, not linked
out to Exercise.** Spec's original build deliberately left homing-tuning
inputs out of Train (reasoning: "editing those belongs to Exercise tab").
The user asked for them back, specifically velocity and current threshold
(not the third Exercise-tab field, current limit) — direct evidence that
"reuse Exercise's routes, don't duplicate the settings UI" was the wrong
call for this specific pair. Uses the same `updateHomingSettings()`
API call and persisted `CableState` fields Exercise's own homing settings
UI already does — no new backend surface, just a second frontend caller
gated the same way, prefilled from the same live status.

## Frontend consolidation to four tabs, 28 July 2026

*This entry, like its `progress.md` counterpart, was written by reading the
working tree rather than transcribed from a live build session — the
changes it describes were already made and sitting uncommitted, with no
prior `decisions.md`/`progress.md` entry covering any of them. Recorded now
so the reasoning that could be reconstructed from the code is captured
before it's lost, and so the reasoning that *couldn't* be reconstructed is
flagged as genuinely unknown rather than silently invented.*

**Why remove Exercise/Dashboard/Presets/Profiles as standalone tabs
instead of leaving them alongside Train?** Not stated anywhere in code
comments, so this is inferred, not confirmed: `TrainSettingsSection.jsx`
had already absorbed homing, max-extension calibration, and spool
calibration from `ExerciseTab.jsx` during the "Train tab refinements" pass
(documented above), which left the standalone Exercise tab as a near-total
duplicate of a section of Train — same routes, same `CableState`, same
UI controls, just in a second place. Deleting the now-redundant tab is
consistent with that trajectory. `DashboardTab.jsx` and `PresetsTab.jsx`
were leftover from the original upstream fork
(`MoonLighTingPY/odrive3.6_web_gui`) and were never wired into
`MainTabs.jsx` for this project in the first place (confirmed via
`git log` — both files only ever appear in the pre-rebrand `Init`/`[WIP]
Deep-refactor` commits), so removing them is closer to dead-code cleanup
than a feature decision.

**What this reasoning does *not* explain, and is flagged as a real gap
rather than papered over: why Force Feedback and the Session-3 resistance
profiles lost their UI along with Exercise/Profiles, with no replacement
and no tab-level deprecation notice.** Unlike homing/calibration, neither
`TrainMode` nor any other current tab exposes an equivalent to
`ExerciseMode`'s Engage/Disengage force-feedback state machine
(constant/isokinetic torque resistance, ARMED/ENGAGED/HOLDING, let-go
detection) or to `ProfileMode`'s phase/rep-aware profiles (bell-curve,
VBT, eccentric-overload wrapper) — both remain fully implemented, tested,
and reachable only via raw `/api/force/*` and a `mode: "profile"`
`ControlSession` start, with zero UI. Two explanations are consistent with
what's in the repo and can't be distinguished from the code alone: (a)
Train's simpler position-based segment profiles were judged to have made
Force Feedback and `ProfileMode` genuinely redundant for this project's
actual use case, and their removal from the UI was intentional even though
undocumented; or (b) this was an oversight during the tab cleanup — the
files got deleted as part of a broader "old tabs" sweep without a separate
check for whether their backend capabilities still needed a home. Given
the amount of Layer B design/debugging effort documented above (governor,
let-go detector, power limiter, the full concentric/eccentric split) went
into Force Feedback specifically, (b) seems at least as likely as (a).
Recorded as a new open item in the master plan doc rather than silently
assumed away in either direction — worth an explicit decision next
session: restore a Force Feedback UI surface (even a minimal one inside
Train or its own small tab), or make the removal official and consider
deleting the now-unreachable backend code too instead of carrying tested-
but-unreachable capability indefinitely.

**Train profile save/load uses `localStorage`, not `CableState`.** Named
profiles are a frontend-only convenience (avoid re-typing a segment layout
every session) rather than project state that needs to survive a different
browser/machine or be inspectable from the backend — so `localStorage`
(`trainProfilesManager.js`, same pattern as the old `presetsManager.js`)
was reused rather than adding a new persisted `CableState` field or backend
route. Consistent with the standing rule (every *tunable default* must be
a persisted, editable setting) without stretching that rule to cover
user-authored content, which was already the call made for the profile
editor's draft state in the "Train tab — build spec §0 research pass"
entry above.

**Sidebar-level Go Home / Reset, independent of any tab.** `DeviceList.jsx`
is mounted for the app's entire lifetime regardless of which tab is
active, so it's the one place a "jog cable home" and a "forget this
connection" control can live without needing a Train or Control tab open —
useful if a cable is left extended mid-task or a USB reconnect glitch
(§5's standing macOS `Errno 19` note) needs clearing without a full
`Restart Freddy`. Go Home reuses `ExerciseMode`'s existing move action
directly rather than adding a new one, deliberately not touching the
homing current threshold so it can never be mistaken for a homing run.

## Train tab — calibration overhaul, 29 July 2026

Six change requests against the Train tab, worked from a numbered list the
same shape as a build spec (no separate `train_tab_calibration_overhaul.md`
file was ever committed, matching how `train_tab_build_spec.md` itself was
never committed either despite being cited constantly in code comments —
apparently these specs have always lived in chat, not in the repo). Full
investigation preceded any code change; two of the six turned out not to be
what they first looked like.

**Item 2 (guard toggles) — investigated, no code bug found.** The report
was that `train_home_guard_enforced`/`train_max_extension_enforced`
toggling off didn't disable the guard. Read `TrainMode.tick()`
end-to-end and re-ran all 21 pre-existing `test_train_mode.py` guard tests
(including the both-disabled and split-independence cases) — all passed
unmodified, and the toggle logic reads exactly as documented: each side
gates independently, correctly. The much more likely explanation: these
two toggles only ever scope `TrainMode`'s own guard (by design, stated in
the UI itself — "Neither toggle affects Exercise's own runtime guard") and
have zero effect on `ExerciseMode`'s separate, always-on two-tier guard.
Since `ControlSession` holds exactly one mode handler at a time, the two
guards are structurally exclusive — `ExerciseMode`'s can't be "still
firing during a Train session." If the toggling that prompted the report
happened during an Exercise setup session (homing/calibration — the normal
state to be in while these controls are visible, right next to "Start
setup session"), that would look exactly like "toggling does nothing,"
while actually being Exercise's own guard behaving as designed. Fix
shipped was UI-clarity only (`TrainSettingsSection.jsx`): moved the
"only takes effect during a running Train session" caveat to sit directly
under each `Switch`, not trailing below both. No logic change — if a real
Train-session repro turns up later, it directly contradicts the passing
test suite and needs a live-hardware capture before any code changes.

**Item 3 (spool radius compensation) — the open question resolved,
two real bugs found, one of them not in the original report.** The
question was whether the existing (uncommitted, unused-in-anger) "spool
growth calibration" feature was blocked or solved a different problem.
Neither: `SpoolGrowthCalibration.jsx`'s "Start" button is gated by the
same ordinary precondition flow as "Start max calibration" right next to
it (Start setup session → Home) — nothing structurally blocks it. It
already correctly feeds cable *length* computation
(`SpoolGeometry.length_from_turns_delta`). What it never fed is the
force→torque conversion: `TrainMode.tick()` computed
`force_to_torque(force_n, r0=self.cable_state.r0)` — the bare, uncorrected
r0, every tick, regardless of k or an active piecewise growth calibration
— so commanded torque (and therefore delivered force) silently drifted
across the travel range even on a rig with a fully calibrated spool model.
Fixed to `r0=self.cable_state.spool_geometry.r_eff_at_turns_delta(...)`,
floored at `SPOOL_MIN_EFFECTIVE_RADIUS_M` (see below for why the floor is
load-bearing, not defensive filler). A second instance of the identical
bug class was found, not reported: `frontend/src/utils/cableGeometry.js`
(the pure-JS mirror `useTrainTelemetry.js` uses to convert live-chart
samples) only ever mirrored the flat r0/k model, never the piecewise
growth model — so even after the backend fix, the Train tab's own chart
would have kept silently showing a stale, uncorrected force/position line.
Added a piecewise mirror (`createSpoolGeometry`), cross-checked against
`core/cable/geometry.py`'s `SpoolGeometry` with reference values generated
by actually running the Python class (not hand-derived) —
`cableGeometry.test.js`.

**Why the `SPOOL_MIN_EFFECTIVE_RADIUS_M` floor on `r_eff` is required, not
optional, for this fix:** `build_growth_segments()`'s final segment
extrapolates its fitted slope indefinitely past the last calibration
point, with no floor check of its own (that check only covers segments
*between* measured points). Item 2's own guard toggles exist specifically
so a session can travel beyond the calibrated envelope on purpose. Combine
the two: a negative-slope growth model (exactly the user's own
thicker-strap scenario — effective radius *shrinks*, ~0.06m at home to
~0.04m at max extension, as more strap pays out) plus a disabled guard
plus enough travel, and the unclamped extrapolation goes through zero and
negative. Feeding that into `force_to_torque` would have made this fix
*more* dangerous than the bug it replaced, not less — so the floor clamp
landed in the same change, not as a follow-up. Mirrored client-side too
(`createSpoolGeometry`'s `minREffM` param, sourced from the already-exposed
`cable.spool_model.min_effective_radius_m`), so the display can't imply a
radius the backend would never actually command.

**Item 1 (hard reset) — reused the existing `reset_position` route, found
and fixed an unrelated gating gap while doing it.** `CableState.reset()`
already did exactly the right thing (home/max only, leaves r0/k/growth/
homing settings untouched) with a route already wired
(`/api/exercise/reset_position`) — no new backend mechanism needed, just a
Train tab UI surface (confirm modal, `TrainResetModal.jsx`, same
self-contained shape as `EraseConfigModal.jsx`) and local React state to
clear (draft profile via a remount key, action errors, an active telemetry
freeze). While tracing the route's idle-gate (`_exercise_action_running`,
renamed `_any_session_running`), found it only ever blocked the reset
while `status['mode'] == 'exercise'` — a live **Train** session (a
different mode string) didn't block it at all. Failed safe either way
(`is_homed` flips False, `TrainMode.tick()` just zeroes torque and
returns) but was never the intent, so widened the check to any running
session rather than leaving a narrower, Train-shaped hole next to the
tab that now calls this route directly.

**Item 6 (telemetry) — audited before reusing, and *what* got reused was
deliberately scoped to the buffering/windowing strategy, not the
transport.** `useTrainTelemetry.js` was already correct (evicts by sample
age against `cable.train_telemetry_buffer_s`, previously fixed for exactly
this reason — see "Train tab" entry above). Extracted its merge/cutoff
logic verbatim into `utils/telemetryBuffer.js::appendAndTrimByAge()` and
pointed both `useTrainTelemetry.js` and `useControlTelemetry.js` at it —
Control's hook had the exact older bug (`MAX_CHART_POINTS = 300`, silently
~6s of real history at the 50Hz tick rate no matter what its range buttons
claimed). Inspector's `LiveCharts.jsx` is **not** on the same REST-poll
hook — it's WebSocket→Redux (`telemetrySlice.js`, ~10ms rate, arbitrary
per-property selection, its own 1000-sample ring-trim) for reasons that
are still valid (Train/Control poll a small fixed set every 150ms;
Inspector needs arbitrary per-leaf selection at a much higher rate) —
replacing that transport to force literal hook-sharing wasn't worth
risking a regression in the property-tree's selection model for a
consistency the user didn't actually ask for. What Inspector *did* share
was the same class of fix at its own display layer: `WINDOW_POINTS = 240`
was the same fixed-point-count bug one level up, replaced with
`chartDisplay.js::filterByAgeMs()` (new, epoch-ms counterpart to the
existing relative-seconds `filterByRange()`) at an equivalent default
duration (2.4s, matching the old cap at the nominal 10ms rate) — no new
range-selector UI added, since the ask was for one consistent *strategy*,
not three coordinated new controls.

**Item 5 (pause/freeze) built as its own hook
(`useFreezableSeries.js`) rather than baked into `TrainTimeSeriesChart.jsx`
or `useTrainTelemetry.js` directly** — wraps any `liveSeries` array, so
reusing the same freeze behavior for Control/Inspector later (if wanted)
is a one-line addition rather than a second implementation. Wired into the
Train tab only for this pass, matching the request's own wording ("Train
tab's live telemetry view"); Reset (item 1) clears an active freeze so it
never leaves the chart pinned to stale data after a state wipe.

**Item 4 (segment editor) split-in-place is deliberately modal-free.**
Splitting a segment always cuts at the numeric midpoint; both halves start
as full copies of the original (fresh ids) and are immediately editable
like any other segment, so retyping the exact boundary happens in the
existing Start/End fields rather than through new UI surface for a value
that's trivially adjustable right after — matches the request's own "keep
this simple." Bell segments get their `peak_pos_m` recentered to each
half's own sub-range midpoint on split (params otherwise copied unchanged)
so both halves pass `TrainSegment`'s `start < peak < end` validation
immediately rather than erroring until hand-fixed. Force continuity
(4b) reuses `addSegment()`'s existing position auto-continue pattern
verbatim for force: a new segment's `force_n` now seeds from the previous
segment's own end-force (`constant`'s `force_n`, `linear`/`bell`'s
`end_force_n`) instead of a hardcoded `50`.

## Same graphs everywhere: Control/Inspector get Train's chart style, 29 July 2026

Follow-up request after the calibration-overhaul pass above: the user liked
Train's telemetry chart (axis scaling, pause, per-line smoothing, bigger
graphs) enough to want the same style and configurability on the Control
and Inspector tabs, which still had the old small/fixed charts
(`MiniChart.jsx`'s three separate cards, `LiveCharts.jsx`'s fixed-smoothing
`PropertyChart` grid).

**Resolved via `AskUserQuestion` rather than guessed, since the two tabs
have genuinely different data shapes:** Control charts the same 3 fixed
quantities Train does (Position/Velocity/Torque) — same shape, so it
became "make it exactly like Train's, one combined chart." Inspector
charts an arbitrary, user-picked number of properties from the property
tree (could be 1 or 10, wildly different units) — forcing all of those
onto one shared multi-axis chart the way Train's 3 known quantities do
would get crowded fast for no benefit, so it kept its one-card-per-property
layout, with each card individually upgraded to the same *controls* Train
has (axis range, invert, smoothing, a shared duration control, and a
shared pause) rather than merged into a single chart.

**Extracted `TrainTimeSeriesChart.jsx` into `components/shared/
TelemetryTimeSeriesChart.jsx`** (along with its `AxisRangeControl.jsx`
dependency, also moved to `components/shared/`) — generalized from a
hardcoded 3-quantity `LINES` array to a `lines` prop, so Control's
`ControlTab.jsx` can reuse the identical component with its own line
config (`position`/`velocity`/`torque_est`, matching
`useControlTelemetry.js`'s raw sample field names directly — no unit
conversion needed the way Train's cable-length keys require). Added one
capability neither original chart had: an `axisKey` per line lets two
lines share one Y axis instead of each getting its own — used for
Control's "Target position" overlay (previously `MiniChart.jsx`'s
bespoke `secondaryKey`/`secondaryLabel`/`secondaryColor` prop trio,
generalized away since it's really just "a second line on the same axis,"
not a fundamentally different concept) — `axisKey: 'position'`, `dashed:
true`, `lineType: 'stepAfter'` reproduces the old dashed-step look without
a separate mechanism. `MiniChart.jsx` had no other callers once Control
stopped using it (Profiles tab, its other intended reuse point per its own
old header comment, no longer exists — see "Frontend consolidation to
four tabs" above) — deleted rather than left as dead code.

**Pause/freeze moved from a tab-level button (Train's original shape) into
the shared chart component itself**, via `useFreezableSeries` used
internally rather than by each caller. Once the same chart is reused by
two tabs, keeping pause external would mean every caller re-wires the
hook and renders its own matching button — self-contained is what makes
"the same everywhere" actually hold. The one wrinkle: Train's Reset (item
1 from the calibration-overhaul entry above) used to call the hook's own
`reset()` to drop an active freeze; with pause now internal, Reset instead
bumps a `key` prop to remount the chart (same remount-for-a-full-reset
pattern already used for `TrainProfileEditor`'s draft state) — no
imperative API needed on the chart itself.

**A real bug, caught only by an actual browser render, not the test
suite:** wiring the Reset remount pattern onto *two* sibling components at
once (`TrainProfileEditor` and the chart, both direct children of
`TrainTab`'s one top-level `VStack`) used two separate `useState(0)`
counters (`profileEditorKey`, `chartKey`) as their `key` props directly.
Both are bumped together in the same `handleReset`, so they're *always*
numerically equal — React saw two sibling elements sharing key `"0"` (then
`"1"`, then `"2"`, forever) and warned "two children with the same key."
`vitest`'s unit tests never render this component tree, so nothing in the
test suite caught it; a Playwright smoke pass against the actual running
dev app (mock hardware backend) did. Fixed by string-prefixing each key
(`` `profile-editor-${profileEditorKey}` ``, `` `telemetry-chart-${chartKey}` ``)
so the two stay distinguishable regardless of their numeric values —
recorded here as the specific reason this codebase's "test the real app,
not just unit tests, for UI changes" convention exists.

**Inspector's per-property upgrade, `LiveCharts.jsx`:** `PropertyChart`
gained the same `AxisRangeControl` + Invert Y + per-property smoothing
dropdown Train's lines have (previously a single hardcoded
`SMOOTHING_WINDOW = 5`, always on — now defaults to Off, matching the
other two tabs' convention, since smoothing became a user choice rather
than a fixed default). Duration is one shared control in the header
(`1s`/`2.5s`/`5s`/`10s`/`All`, ms-based since Inspector's raw samples
carry epoch timestamps) rather than per-card — a "how much history am I
looking at" view setting is naturally one shared choice across every
displayed property, the same way Train/Control have one range-button-group
for their whole chart rather than one per line. `chartDisplay.js`'s
`filterByAgeMs()` gained `ms == null` meaning "no filter" (matching
`filterByRange()`'s existing `seconds == null` convention) so "All" could
reuse it. Pause is similarly one shared button freezing every property's
data at once (`useFreezableSeries` wrapping the whole `{path: [...]}`
samples map as a single unit) rather than per-card, for the same reason.
Card height bumped 220px → 320px ("bigger graphs" was part of the
original ask). The underlying WebSocket→Redux transport
(`telemetrySlice.js`) was deliberately left untouched — see the
calibration-overhaul entry above for why forcing it onto Train/Control's
REST-poll shape would cost more (risking the property-tree's per-leaf
arbitrary-selection model) than it would gain.

---

# Testing tab — controlled experiments (Static Weight Hold)

Per the "Testing Tab — Build Spec" (30 July 2026). Continues the append-only
log above.

## Home/max persistence is in-memory only — flagged, not a new gap

Spec §1/§8 open item #1 assumes homing/max-extension/spool calibration are
"saved." Reading `core/cable/state.py::CableState` confirms `home_turns`/
`max_turns` are in-memory only, by explicit existing design (a fresh backend
process always comes up un-homed — see that file's own module docstring).
This is not a gap introduced by this feature: Train/Exercise already live
with it (a session re-homes after every backend restart), and the Testing
tab gates on the exact same `cable_state.is_homed`/`has_max` Train's own
`TrainMode._apply_run` already gates on. Flagged explicitly here per the
spec's own instruction to raise this rather than silently assume it's fine,
but not treated as a blocker — it doesn't regress anything Train doesn't
already require. "Spool calibration" has no separate boolean either — `r0`
always holds a value (bench-default or calibrated); the Testing tab displays
`r0`/`k` read-only rather than gating on a third condition.

## Sign convention: no CABLE_SIGN flip on the experiment's own torque

`StaticWeightHoldExperiment` commands torque exactly as configured
(`initial_torque_nm`, ramp rate) with no `CABLE_SIGN` flip applied — unlike
`TrainMode`'s tension-resisting logic, this experiment's torque is a direct
user-facing config value (the spec literally calls it "starting torque
command"), not a force derived from cable tension. Whether a positive
`initial_torque_nm` actually lifts (vs. lowers) the attached weight is
bench-rig dependent and **unconfirmed until the first live run** — same
"flag it, verify at the bench" treatment `CABLE_SIGN` and
`enable_torque_mode_vel_limit` already got in this project. Worth a specific
glance in the first supervised session with Ivan.

## Spec self-contradiction: COMPLETE vs. ABORTED on a max_duration_s timeout

The spec's own §2.2 defines COMPLETE as "user-initiated stop or timeout
elapses," but its ABORTED bullet separately lists `max_duration_s` among the
safety limits that trigger ABORTED — directly contradicting COMPLETE's own
definition for the identical event. Resolved in favor of COMPLETE's more
specific, literal definition: a `max_duration_s` timeout ends the run as
COMPLETE (a graceful, planned end), while a `max_torque_nm` breach (an
active fault, not a planned end) triggers ABORTED. Documented in
`core/experiments/static_hold.py`'s module docstring rather than silently
picking one. Worth confirming with Ivan which reading was actually intended.

## HOLDING's 0-floor torque clamp is spec-literal, flagged as a real v1 limitation

`clamp(torque_command, 0, max_torque_nm)` (spec §2.4, implemented exactly)
means an overshoot above target can only be corrected by torque decaying
toward zero (letting gravity pull the weight back down), never by commanding
negative torque. This is the spec's own explicit v1 formula, not something
this implementation invented or could silently improve on — flagged in-code
and here since it's a real, likely-visible behavior once this runs against
an actual weight (a fast overshoot may sag noticeably before the ramp climbs
back up), not a subtle edge case.

## Bus voltage: a genuinely new read path, current is not

Grepped `core/hardware/` before assuming either channel needed new plumbing:
only phase current (`current_iq`, `Iq_measured`) was ever exposed via
`TelemetrySample` — no bus voltage or bus current read anywhere in `core/`
(the only `vbus_voltage` reference in the whole repo was in
`backend/app/mock_odrive.py`'s unrelated static property-tree mock). Added
`TelemetrySample.bus_voltage_v: float = 0.0` (defaulted specifically so the
~20 existing `TelemetrySample(...)` construction call sites across
`core/tests/` — written before this field existed — don't need touching),
populated from `odrv0.vbus_voltage` in `odrive_hw.py` (a real, confirmed
top-level 0.5.1 property per `config/odrive_config.py`'s own live-verified
usage) and a new `SIM_BUS_VOLTAGE_V = 24.0` placeholder constant in
`sim_hw.py` (matching the mock's own seed value, same "placeholder, not
embarrassing" bar Session 2 set for `SIM_INERTIA_J`/`SIM_DAMPING_B`).
`measured_current_a` needed no new read path at all — it's served straight
from the existing `current_iq_a` CSV column (labeled "phase current
(Iq_measured)"), not duplicated into a second column.

## estimated_power_w: mechanical power, not current*voltage

Spec §3 explicitly allows either `current * voltage` (electrical bus power)
or `torque * velocity` (mechanical power) and asks to document which.
Chose mechanical power (`core/experiments/telemetry.py::estimated_power_w()`,
`torque_est * velocity * 2*pi`) specifically because `current * voltage`
would double-count against the phase-current channel already logged
separately in its own column — the reader would see two power-adjacent
numbers derived from overlapping raw quantities with no clear reconciliation
story. `torque_est`/`velocity` are also already both per-sample fields with
no extra read path needed either way.

## ExperimentMode lives in core/experiments/, not core/control/modes.py

Followed `TrainMode`'s own precedent (`core/cable/train_mode.py`) directly:
a `BaseMode` subclass belonging to a sibling `core/` package, injected with
the shared `CableState`, rather than adding a fourth mode class to
`core/control/modes.py` itself. `core/experiments/` importing
`core/control/modes.BaseMode` and `core/cable/state.CableState` is a
core-to-core dependency, not a core→backend one, so this doesn't violate the
package's "must not import backend/" rule (confirmed by the same grep
convention every prior session has used:
`grep -rn "backend" core/experiments/` — zero matches).

## Experiment ABC is hardware-free, unlike TrainMode's own tick()

`core/experiments/base.py::Experiment.step()` is a pure function (reads a
`TelemetrySample`, returns a torque command + state) — it never calls
`hardware.set_torque_target()` itself. This mirrors `ResistanceProfile
.compute_torque()`'s shape, not `TrainMode.tick()`'s (which writes to
hardware directly). Chosen specifically so the RAMPING/LIFTING/HOLDING state
machine — the part most worth testing precisely — is unit-testable with
plain `TelemetrySample` construction, no `RecordingHardware` fake required
at all (`core/tests/test_experiments.py`, 20 tests, zero hardware fakes).
The actual `hardware.set_torque_target()` call happens one layer up, in
`ExperimentMode.tick()` (`core/experiments/mode.py`), covered separately by
`test_experiment_mode.py`'s `RecordingHardware`-fake tests and
`test_experiment_session.py`'s full `ControlSession`-against-`SimHardware`
tests.

## Motor-energization gate is structural, not just a UI convention

`ExperimentMode`'s two-phase action dispatch (`configure` then a separate
`confirm_start`) means the motor genuinely cannot move between the two Flask
calls — `apply_target`'s `"configure"` branch always commands
`hardware.set_torque_target(0.0)` and never calls `.start()`; only
`"confirm_start"` does. This mirrors `ExerciseMode`'s existing "arm with zero
motion, then a later explicit action" convention (`exercise_start`) rather
than inventing a new pattern for the same requirement.

## Same-tick hardware.stop() on COMPLETE/ABORTED, not a deferred frontend call

`ExperimentMode.tick()` calls `hardware.stop()` directly, in the same tick,
the instant `Experiment.step()` reports `COMPLETE` or `ABORTED` — satisfying
spec §5's "any breach forces immediate ABORTED + safe shutdown" literally,
rather than waiting for the frontend's next status poll to notice and call
the `/stop` route. `ControlSession._running` stays `True` for one more tick
after this (the session-level teardown only happens via `ControlSession
.stop()`, called either by the user's Stop button or the frontend noticing
`experiment_state` is terminal and calling it automatically) — the motor
itself is already safe (zero torque, idle) well before that.

## Hardware-error auto-stop is not special-cased for experiments

A hardware/encoder error mid-run is not handled inside `ExperimentMode` at
all — `ControlSession._telemetry_loop`'s existing generic `get_errors()` →
auto-stop path (used identically by every other mode) already provides
"transition to safe shutdown, don't try to recover." One caveat, documented
rather than solved: the CSV's last `experiment_state` row before such a stop
reflects whatever phase was active when the error was caught (not a literal
`"aborted"` label), since the error check happens *after* `tick()` returns.
The session-level `errored`/`error_message` fields (already surfaced on
every tab's UI) are what distinguish this case — exactly how Train/Profile
already behave on a hardware-error auto-stop, not a new inconsistency this
feature introduces.

## Removed: the spec's "Sim/Real banner" ask no longer matches the app

Spec §4 asks the Testing tab to mirror "the existing Control/Profiles tab
pattern," naming the Sim/Real banner specifically. That banner has since
been removed from the app entirely — `backend/app/control_routes.py`'s
`control_session` is hardcoded `hardware_source="real"` (the sim/real
switcher was pulled from the GUI once the project moved to running against
real hardware only; `set_hardware_source()`/the `/api/control/hardware-source`
route remain for scripting/tests). Built the Testing tab to mirror what
Train actually looks like *today* instead (connection/running/homed badges,
no sim/real switcher) — the literal reading of "mirrors the existing
pattern," since that pattern has moved on.

## Verification: homing cannot complete against SimHardware in reasonable time

Attempted a full live-browser pass (headless Chrome + a locally running mock
backend) of Configure → Confirm & Energize → RAMPING → LIFTING → HOLDING →
Stop. Blocked at the homing step: `core/cable/homing.py`'s detection
watches `current_iq` crossing `HOMING_CURRENT_THRESHOLD_A` (4.0 A default),
but `SimHardware` has no cable-load model at all (documented, pre-existing
limitation — "no noise/load/cable model" per `sim_hw.py`'s own module
docstring) — a free-spinning sim motor's steady-state current at the homing
reel-in velocity never approaches that threshold, so homing always ends in
`FAULT_TRAVEL_EXCEEDED`/`FAULT_TIMEOUT`, never `HOMED`. This is not a bug in
this feature; it's a limitation of the existing sim/mock stack that
pre-dates it (Train/Exercise's own homing is subject to the identical
limitation). Verified the *identical* code path a different way instead:
`test_experiment_session.py` drives `ExperimentMode` through a real
`ControlSession` against `SimHardware` with a directly-homed `CableState`
(bypassing the homing state machine's hardware-load requirement, not the
`ExperimentMode`/`ControlSession` code itself) — full RAMPING→LIFTING→
HOLDING cycle, Stop from all three states, `max_torque_nm`/`max_duration_s`
paths, all pass. The live-browser pass instead verified the un-homed
prerequisite-gating path (banner text, config form correctly hidden, zero
console errors) — the one part of this tab that genuinely needed a real
browser to confirm and that has no such blocker. Real-hardware verification
of the full cycle is deferred to a supervised session with Ivan present, per
the spec's own Definition of Done.

## Housekeeping: a pre-existing Vite dev server was inadvertently killed

While cleaning up after the headless-Chrome smoke pass, `pkill -f
"node.*vite"` was used to stop the dev server started for testing — this
pattern matched *any* Vite process, not just the one just started, and
killed a second, pre-existing Vite process (PID 66492, running since
5:40PM, well before this session's work began) that was not part of this
work. Flagged to the user directly rather than silently noted here only —
if that process was someone's own dev session, it needs restarting
(`npm run dev` / `npm run dev:frontend`). Lesson for next time: kill dev
servers started for a smoke test by their own captured PID, never a broad
process-name pattern.

---

# Anti-cogging calibration — added to Configuration → Motor Controls

## Frontend placement: moved from the Testing tab to Configuration → Motor Controls

Initially built the card inside the Testing tab (the most recently-discussed
GUI feature at the time). The user then explicitly asked for it in "the
Motor Controls tab" instead — a literal sub-tab within the Configuration
tab's own internal `Tabs` (`ConfigurationTab.jsx`: `Configuration | Motor
Controls | Command Console`, `subTabIndex === 1`), already rendering
`MotorControlsCard` (Enable/Disable Motor, Full/Motor/Hall-Polarity/Encoder-
Offset/Index-Search calibration, Clear Errors, Save & Reboot). That's a
better conceptual home regardless of who asked: anti-cogging calibration is
another axis-level calibration action, the same family as the buttons
already there, not a cable-load experiment (the Testing tab's actual
purpose). Moved the component from `frontend/src/components/tabs/testing/`
to `frontend/src/components/AnticoggingCalibrationCard.jsx` (same directory
level as `MotorControlsCard.jsx`) and dropped the `controlSessionRunning`
prop in favor of reading it from the card's own polled
`/api/anticogging/status` response (the backend already computed this field
for exactly this reason) — makes the card fully self-contained, with no
dependency on whichever tab happens to render it, which mattered here since
it moved once already.

## Architectural home: its own module, not a ControlSession mode

The task named `core/hardware/odrive_hw.py` as the wrapper to route through,
but that file's own docstring is explicit: "Only does runtime control. Never
writes config/calibration properties — that is the wizard's and the 1B
script's job." Anti-cogging calibration writes NVM config
(`pre_calibrated`), calls `save_configuration()`, and reboots the board —
squarely calibration/config territory, not runtime control. Read "route
through the existing choke point" as the actual constraint (no second
`odrive.find_any()` call site) rather than literally as "extend
`OdriveHardware`," and built `core/hardware/anticogging.py` +
`backend/app/anticogging_routes.py` instead — routing through
`device_manager.get_shared_handle()`/`get_shared_io_lock()`, the same shared
handle `OdriveHardware` itself is injected with. Confirmed no new discovery
call site: `grep -rn "find_any" --include="*.py" backend core config` still
shows exactly the same two real call sites as every prior session's
choke-point audit.

A second reason this doesn't fit `core/control/modes.py`/`core/experiments/`:
those both model a continuous per-tick loop (read state, compute/apply a
target, every 50 Hz tick). Anti-cogging calibration's actual motor motion is
entirely autonomous in firmware once `start_anticogging_calibration()` is
called — there is nothing for an outer tick loop to do except poll one
boolean. Modeling it as a `BaseMode` would mean either an idle `tick()` that
does nothing every 50 Hz cycle (wasteful, and would need
`ControlSession.start()`'s full connect/mode/target lifecycle for something
that isn't really "a control session"), or contorting the abstraction. A
small request-driven state machine, polled via `GET /api/anticogging/status`
itself (same REST-polling convention as every other tab, no websocket, no
background thread), fits the actual shape of the problem.

## Reboot handling: mirrors the live app's existing pattern, not odrive_config.py's

`config/odrive_config.py`'s `call_and_reconnect()` (catch
`ChannelBrokenException`, then block calling `odrive.find_any(timeout=...)`
until the board reappears) is the right shape for a linear, single-`odrv0`-
variable standalone script, but the live Flask app already has a different,
proven pattern for "a request triggers `save_configuration()`/reboot, and
other requests need to keep working afterward": per this file's own
"Phase 2A hardware bring-up" entry, the frontend's existing calls to
`save_configuration`/`erase_configuration` (Presets tab, calibration hook,
config wizard) go through `device_manager.attach_or_get(serial)` — a fresh
handle fetch per request — plus `device_manager`'s own ambient self-healing
(`_serialize_cache_if_alive()`, which drops a cached handle the moment a
property read on it raises, forcing the next access to rediscover). Rather
than block one HTTP request for up to 15s waiting for the board to
re-enumerate (the standalone script's approach — fine for a human watching a
terminal, bad for a Flask request/response cycle with a browser on the other
end), the finish sequence here catches the expected
`ChannelBrokenException` from `save_configuration()` inline and returns
immediately, then proactively calls `device_manager.forget_all()` so the
*next* access (this same status route on its next poll, or any other tab)
forces a fresh reconnect right away — deterministic and immediate, rather
than waiting on the ambient ~3s sidebar poll to notice a dead handle on its
own. `forget_all()` (not a new "forget one serial" helper) is reused as-is:
this project is single-device by design, so forgetting everything is
equivalent to forgetting the one board, and it's already the exact primitive
the sidebar's "Reset Interface" button uses for the same "something changed
under us, force a fresh look" need.

## Threshold/multiplier defaults are unmeasured placeholders

`ANTICOGGING_CALIB_POS_THRESHOLD_DEFAULT`/`_VEL_THRESHOLD_DEFAULT` (1.0/0.5)
have no documented factory default anywhere available to this repo:
`frontend/src/utils/odriveApiReference05x.json` confirms the property paths
exist but is schema-only (types/access, no default values), and nothing else
in this project has ever read these back from a live board. Chosen as
round, conservative starting points and flagged `TODO(bench)` — same
treatment as `MOTOR_TORQUE_CONSTANT`/`ENABLE_TORQUE_MODE_VEL_LIMIT` before
them. The two gain multipliers (6.0/6.0) are more solidly grounded: the task
explicitly suggested "4-8x" of the *live-tuned* `CONTROLLER_POS_GAIN`
(6.0)/`CONTROLLER_VEL_INTEGRATOR_GAIN` (0.1), so these are stored as
multipliers of those existing constants, not a second absolute pair — a
future re-tune of the normal gains can never leave this block silently
inconsistent with them.

## Gain multipliers/thresholds: per-run editable, not a CableState-persisted setting

The Testing tab's own build spec (an earlier session) used stronger wording
— "every numeric threshold... must be a user-editable, **persisted**
setting" — which that feature satisfied via `CableState`'s
`_PERSISTED_DEFAULTS`/`set_*_settings()` mechanism (survives a backend
restart, editable independent of any single run). This task's wording is
narrower: "editable settings in `config/board_constants.py`, not buried
constants." Read literally, that's satisfied by named constants alone.
Chosen middle ground: named `board_constants.py` defaults, editable
per-run from the GUI form (exactly like `ExperimentConfig`'s own fields),
but **not** added to `CableState`'s persisted-settings sidecar — avoids
building a second settings-persistence path for something not asked for at
that strength. Revisit (add `set_anticogging_settings()` to `CableState`,
same pattern as `set_force_settings`) if per-run editing turns out not to be
enough in practice.

## Live discovery: this session's backend is connected to the real physical board

Starting the backend (`python backend/start_backend.py`, no `ODRIVE_MOCK`
set) for a routes sanity-check unexpectedly connected to real hardware:
`GET /api/devices` returned serial `367836843335` — the exact serial number
`backend/app/device_manager.py`'s own module docstring already references
from a prior live session ("`odrivetool` showed '367836843335' for a board
whose raw `.serial_number` int is 59889938608949") — confirming this is
Ivan's actual bench-mounted board, not the `ODRIVE_MOCK` property-tree mock
(which has no seeded `anticogging` properties at all — its property surface
is generated from `odriveApiReference05x.json`'s schema at runtime, not a
hardcoded Python dict, so the presence/absence of mock seeding can't be
grepped for directly). `GET /api/anticogging/status` was called against it
once to verify wiring — a read-only property check
(`anticogging_enabled`/`pre_calibrated`/`anticogging_valid`, all `true` on
this board already, i.e. it's been calibrated before, in a session not
otherwise documented in this repo) — nothing written, no RPC calls, no
motor motion (`AnticoggingCalibration`'s `state` was freshly `IDLE`, so
`.poll()` short-circuited without touching hardware beyond those reads).

`POST /api/anticogging/start` was deliberately **never called** during this
session's verification, since it would have actually raised gains and
spun the real motor — that's exactly the kind of motor-energizing action
this project has consistently gated behind an explicit human present at the
bench (`config/odrive_config.py`'s `confirm()` prompts, the Testing tab's
own "Confirm & Energize Motor" gate). All calibration-logic verification
instead went through `core/tests/test_anticogging.py`'s fake `odrv`/`axis`
object tree (17/17 passing) and a headless-Chrome pass that opened the
confirmation dialog and clicked **Cancel**, never **Confirm**. Real-hardware
triggering of this feature is left for a supervised session with Ivan
present.

---

## 5 August 2026 — DC bus overvoltage ramp fix (Train mode hard-pull trips)

**Problem:** Hard/fast cable pulls in Train mode caused vbus to spike
toward the 25V overvoltage trip and fault, despite a correctly-valued
brake resistor being wired in. The brake resistor never got warm during
these events.

**Root cause:** odrv0.config.enable_dc_bus_overvoltage_ramp was False
(firmware default), even though dc_bus_overvoltage_ramp_start/_end had
values set from an earlier config pass. The DC bus overvoltage ramp
feature — which drives brake resistor duty cycle directly off measured
vbus voltage — is fully inactive unless this flag is explicitly True.
Without it, the brake resistor only ever responded to the primary
current-based regen logic (tied to max_regen_current), which reacts to
sustained regen current, not fast voltage transients — so a hard pull
outran it and drove vbus toward the trip before the resistor engaged.

**Fix:**
- enable_dc_bus_overvoltage_ramp = True
- dc_bus_overvoltage_ramp_start = 24.0 V
- dc_bus_overvoltage_ramp_end = 25.0 V
- brake_resistance updated to 2.35 Ω (two spare resistors wired in
  parallel, replacing the single 2Ω/50W unit; combined wattage rating
  identified as 100W — resolves the wattage-unknown half of open item #4)
- dc_bus_overvoltage_trip_level raised to 27V (deliberate decision,
  distinct from the ramp fix itself — supersedes the prior 25V
  bench-only value on record)

**Verified:**
- Hard pull in Train mode — vbus stays ~23.6V, no fault (previously
  spiked toward trip)
- Full DC bus power cycle confirms all values above persist correctly via
  Freddy's Apply & Save — save_configuration() is working as expected on
  this board for this path

**Open follow-up:** resistor ran uncomfortably hot within seconds on a
short manual test despite the now-known 100W rating. Do not run
extended/hard training sessions until thermal behavior under sustained
real load has been checked — see open item #4.

Wired into both `config/board_constants.py` (`BRAKE_RESISTANCE`,
`DC_BUS_OVERVOLTAGE_TRIP_LEVEL`, new `ENABLE_DC_BUS_OVERVOLTAGE_RAMP` /
`DC_BUS_OVERVOLTAGE_RAMP_START` / `DC_BUS_OVERVOLTAGE_RAMP_END`, all
exposed via `GET /api/board-constants`'s existing `"bus"` key) and
`config/odrive_config.py`'s static config section (matching literal
assignments in the same "Bus-level limits" block), so a fresh board
bring-up or a post-`erase_configuration()` re-run reproduces this fix
automatically rather than relying on the live board's current flash
state. `dc_max_negative_current`, `max_regen_current`, and the
motor/encoder/gain config were deliberately left untouched — out of
scope for this fix.

## 5 August 2026 — Testing tab redesign: reuse Control's Position mode instead of a dedicated experiment mode

The Testing tab's first design (a `core/experiments/` `ExperimentMode` with
a configure → confirm → energize → immutable-run lifecycle) matched its own
build spec, but real use showed the actual complaint was about workflow, not
features: the user wanted to nudge a parameter and see the effect
immediately, keep adjusting, no restart — exactly what Control tab's
`mode: "position"` already does for free. Rather than teaching
`ExperimentMode` a second, parallel live-retarget path, the Testing tab now
drives that same session directly. Net effect was code *deletion* (the
whole `core/experiments/` package, its routes, its frontend plumbing, and
its tests) in favor of reusing an existing, already-correct mechanism — a
stronger fit for "keep it simple" than extending the mode that was purpose-
built for the old flow. Accepted trade-off: Testing-tab moves and Control-
tab moves both log CSVs under the same `position` mode name, indistinguishable
by filename alone — not worth a new mode purely for log labeling.

## 5 August 2026 — ExerciseMode's position guard was never wired to the Train enforcement toggles

`train_home_guard_enforced`/`train_max_extension_enforced` were added (an
earlier session) specifically for `TrainMode.tick()`'s runtime guard, with
`ExerciseMode.tick()`'s own guard deliberately left unconditional — the
frontend's own settings text said as much: "has no effect on the setup
session above ... which always enforces its own always-on guard regardless
of this toggle." That was a real design decision at the time (a safety
floor for the setup session), but it surfaced as a bug report from actual
use: disabling the toggle in the Train tab, then hitting Go Home or making
a manual move, still hard-stopped with the *generic* ExerciseMode error
message (no "Train" in it — confirmed this was the code path being hit, not
TrainMode's). Decided the floor wasn't actually wanted — "if the user has
disabled the guard, this protection should also be disabled" — and gated
`ExerciseMode.tick()`'s guard on the same two toggles as `TrainMode`,
combined with OR rather than per-side. That's a narrower behavior than
`TrainMode`'s own split per-side gating (`check_runtime_guard_split`):
disabling either toggle turns ExerciseMode's guard off entirely, rather than
leaving the untouched side still enforced. Chose the simpler combined gate
over duplicating `TrainMode`'s split logic a second time; flagged in code as
revisitable if the finer per-side distinction turns out to matter for
Exercise-mode operations specifically.

## 5 August 2026 — Torque/force calibration: sign-preserving magnitude fit, not a signed linear fit

Building the torque calibration model (`core/cable/torque_calibration.py`)
initially fit a straight line directly between the recorded (signed)
`raw_torque_nm` and the (always positive) `expected_torque_nm =
known_weight_kg * g * r_eff_m`. This looked fine at first — the two
calibration points recorded on the actual bench both happened to have a
negative raw reading (holding a weight against gravity reads negative
current on this rig's wiring convention), and a line through exactly 2
points fits exactly regardless of sign, so the fitted `scale` came out
negative (~-0.512) and still reproduced both points precisely.

The bug: `scale` being negative isn't just an aesthetic oddity — it means
`corrected_torque_nm()` and its inverse `raw_torque_nm_for_corrected()`
silently flip the sign of anything with the *other* sign of raw reading.
This is exactly what produced a real, user-visible symptom: selecting a 5kg
equivalent for the Testing tab's Torque Limit field computed a NEGATIVE raw
Nm value (~-0.7 Nm) to send to the hardware as a torque limit — nonsensical,
since a torque *limit* is a magnitude, never negative. Traced this to the
fit itself, not a downstream conversion bug: the model was trained on a
mix of a signed quantity (raw current/torque, direction-dependent) and an
unsigned one (a known weight's expected torque, never negative), so the
"correction" it learned baked in whatever sign the calibration holds
happened to share — physically meaningless outside that one sign regime.

Fix: split sign from magnitude at the model boundary. `fit_linear` now fits
`|raw_torque_nm|` against `expected_torque_nm` (both always non-negative),
so `scale`/`offset` describe how big the torque really is — a property of
the motor and friction, not of which way the cable happened to be moving
during calibration. `corrected_torque_nm()`/`raw_torque_nm_for_corrected()`
strip the sign of their input, apply the (now always meaningful) magnitude
correction, and reapply the original sign unchanged afterward — direction
still passes through untouched for every caller that needs it for control
(the sign of `torque_est`/`commanded_torque_nm` encodes which way the motor
is turning/pushing, genuinely useful information, never something this
calibration should touch). `raw_torque_nm_for_corrected()` additionally
floors the corrected magnitude at 0 before dividing — a corrected value
smaller than the fitted `offset` has no valid non-negative raw magnitude
that produces it, so clamping to 0 avoids returning a nonsense negative raw
command. Mirrored exactly in `frontend/src/utils/cableGeometry.js`
(`correctedTorqueNm`/`rawTorqueNmForCorrected`), same "keep in lockstep,
don't reintroduce a second drifted formula" rule as every other JS mirror in
that file.

Separately, wherever torque/force is presented as *resistance* to a human
(the Testing tab's "Measured torque"/"Measured force" stats, the main
user-facing numbers, not the Developer diagnostics panel) now display
`Math.abs(...)` — resistance isn't negative, and showing e.g. "-3.79 Nm" for
a felt resistance reads as a fault rather than a magnitude. The raw signed
value is still shown, deliberately, in the Developer diagnostics panel and
the calibration points table — sign is meaningful there for verifying/
debugging the model itself.

## 5 August 2026 — Torque calibration wasn't reaching the Control tab

Auditing "is this calibration used everywhere" (explicitly requested)
surfaced a real gap: `core/control/modes.py`'s generic `PositionMode`/
`TorqueMode` — used directly by the Control tab, and (via the Testing-tab
redesign above) by the Testing tab too — have no `CableState` awareness at
all by design (they're meant to be simple, hardware-generic set-and-forget
modes; `ProfileMode` is the only one with an outer loop). The Testing tab
already converts client-side before ever calling these modes (documented in
its own code from the redesign above), but the Control tab's own Torque
(est.) display and its Torque-mode/Position-mode-Torque-Limit targets never
got the same treatment — they read/wrote raw motor-constant Nm directly.

Rather than teaching the generic modes about `CableState` (which would break
their "hardware-generic, no cable-specific knowledge" design), the fix
follows the same precedent the Testing tab already established: convert at
the client boundary. `useControlTelemetry.js` now also polls
`/api/exercise/status` for the calibration snapshot (mirroring
`useTestingTelemetry.js`'s existing second poll exactly), and `ControlTab.jsx`
converts every user-facing Nm value through the calibration before it's
sent, and every displayed torque reading through it before it's shown —
making the calibrated model the single source of truth for torque/force
everywhere in the app that reasons about it, without adding cable-specific
coupling to the generic control modes themselves.

## 5 August 2026 — Resistance display unit (N vs kg): a display-only preference, Newtons stay the wire format

Added `resistance_display_unit_kg` as a persisted `CableState` setting
(same `_PERSISTED_DEFAULTS` mechanism as the existing guard toggles),
settable from the new Setup tab. Deliberately scoped as display/entry-only:
`core/cable/train_profiles.py` and the wire format between frontend and
backend are unchanged, always Newtons — conversion happens only at
`TrainProfileEditor.jsx`'s own input/output boundary (building the payload
sent to the backend, and populating fields when a saved profile is loaded
back in). This means a profile saved while in kg mode and reloaded in N
mode (or vice versa) still represents the same physical resistance, just
displayed differently — the alternative (persisting profiles in whatever
unit was active when saved) would make saved profiles' meaning depend on a
setting that could change later, which is worse.

Deliberately NOT extended to `TrainPositionChart.jsx` (the Planned-vs-Actual
diagnostic overlay chart, which already has its own manual per-curve
scale-factor multiplier and axis-range controls — a developer-facing
diagnostic view, not the "building a profile" surface the request was
about) or to the Testing tab's existing independent Nm/N/kg Torque Limit
selector (a different, already-flexible per-field unit choice, not this
global preference) — kept the change scoped to the one place explicitly
asked for (the Train tab's resistance profile builder) rather than
threading a new global preference through every force-shaped field in the
app.

## 17 August 2026 — Repetitive testing sub-tab, adjustable settle tolerance, and a mock-fidelity gap found along the way

Added a **Repetitive testing** sub-tab alongside Configure move in the
Testing tab (`RepetitiveTesting.jsx`), for running a defined sequence of
position-mode moves (each with its own distance/unit, velocity, torque
limit) a chosen number of times in a row — built ahead of upcoming
endurance/thermal characterization work. Configure move itself is
untouched, just relocated one level deeper into its own `TabPanel` of a new
`Tabs` wrapper around the same card (`TestingTab.jsx`'s own header comment
and behavior — Known Weight, Move Distance, Move Velocity, single Torque
Limit, live Update — are unchanged).

There's no backend "move finished" signal to build a sequence off of —
`ControlSession.status()`/`PositionMode` never expose anything like
`trajectory_done` (confirmed: nothing in `core/control/modes.py`,
`core/hardware/odrive_hw.py`, or the ODrive attributes read anywhere in
this codebase reports trajectory completion). "Settled" is instead
inferred client-side: the live sample's position within a tolerance of the
commanded target AND velocity below a threshold, sustained for 3
consecutive polls (debounces normal trajectory-following noise before a
move has actually stopped), with a 20s per-move timeout as a safety net
against a move that never settles (e.g. torque-limited against real load).

That position tolerance is now a user-adjustable "Settle tolerance" field
(default 0.02 turns) rather than a fixed constant — a tight tolerance can
leave a real rig chasing the last fraction of a turn before a move is
allowed to advance, needlessly slowing a long repetition sequence down.
The velocity threshold isn't exposed as its own field; it scales with the
same input at the ratio the two were originally fixed at (1.5×), so the
one control loosens both halves of "settled" together rather than adding a
second field for a distinction most users won't care to tune separately.

**Bug found via an actual browser run, not by lint/build/the test suite**:
the first version of the "stopped externally" safety net (catches the
top-level STOP button, another tab, or a hardware auto-stop cancelling the
sequence out from under it) checked a `running` boolean prop in its own
`useEffect([running, busy])`. That prop only updates on the parent's own
~150ms telemetry poll cycle, which lags just behind this component's own
start/resume call finishing — so the effect fired inside that gap and
misread the sequence's own just-started session as an external stop,
halting every run immediately after Start. Fixed by folding the same check
into the effect that's already gated on a *new* telemetry sample arriving
(`status?.latest_sample?.t` changing) instead of its own independent
trigger — that guarantees `status` is at least as fresh as the render that
caused it, so the check can only ever evaluate once genuinely caught up.
Caught by starting a sequence against the mock backend in a headless
browser and watching it self-abort within the first render; none of
lint, the build, or the existing test suite exercise real telemetry
timing closely enough to have caught it.

**Separately found while trying to verify a full run completes naturally
against `ODRIVE_MOCK=1`**: it can't. `backend/app/mock_odrive.py`'s
`encoder.pos_estimate` is driven purely by wall-clock time (`2.0 *
sin(t * 0.5)`, `_animated_value()`) — it never reads back
`axis.controller.input_pos`, so it doesn't track a commanded position
target regardless of what's sent; current/torque telemetry animates the
same time-driven way, independent of the command. "Wait for live position
to approach the commanded target" — the whole basis of this feature's
settle detection — can therefore never reliably succeed against the mock.
This is a pre-existing mock-fidelity gap, not introduced here and not
specific to this feature (the same kind of check against Configure Move's
own moves would hit it too), not a bug in the new code. Verifying this
feature's settle/advance behavior end-to-end requires real hardware; no
workaround exists in the mock today.

Also worth recording here: while researching the brake-resistor question
for the accompanying real-hardware testing plan, confirmed this rig's
brake resistor is driven by two independent mechanisms (see 5 August
2026's DC-bus-overvoltage-ramp entry above) — a current-based path
(`max_regen_current`) reacting to *sustained* regenerative current, and a
voltage-ramp path added specifically because a fast/hard pull could
outrun the current-based path. Repeated automated lifting/lowering of a
hung weight (no human pulling involved) generates sustained regenerative
current during the lowering — and to a lesser extent, the deceleration —
phases, exactly like any other regenerative-braking event: it exercises
the *current-based* path the same way a real workout would, just without
the fast-transient case a hard yank specifically stresses. This directly
informs open item #2 (brake-resistor thermal verification, v1.9 §6) and is
written up for hands-on use in
`docs/testing_tab_experiment_guide.md`.

## UI redesign sub-phase 1 (Setup tab prototype) — styling mechanism (Step 0)

Per the handoff doc's Step 0, confirmed before making any visual change: the frontend
styles through **Chakra UI** (`@chakra-ui/react` + `@emotion/*`), not Tailwind, CSS
modules, or styled-components — there is no `tailwind.config.js` or any `.module.css`
anywhere in `frontend/`. There **is** a shared theme file: `main.jsx` calls
`extendTheme({...})` (fonts Inter/JetBrains Mono, a `gray` scale, a teal-ish `odrive`
color scheme used as the app-wide accent via `Button`'s `defaultProps.colorScheme`,
custom `radii.md`/`radii.lg`, and `config: { initialColorMode: 'dark', useSystemColorMode:
false }` with a dark global body background). Individual components then layer
per-instance Chakra style props on top (`bg="gray.800"`, `color="gray.400"`,
`colorScheme="odrive"`, `fontFamily="mono"` for numeric values, etc.) rather than
consuming named semantic tokens — so today's styling is theme-for-palette/fonts,
per-component-props for everything else.

This matters for scoping sub-phase 1 to the Setup tab only: the whole app is forced into
dark mode globally (`initialColorMode: 'dark'`), and Chakra's `colorScheme` props (Badge,
Alert, Switch, Button, Card `variant="elevated"`'s shadow) render differently depending on
the active color-mode context. Rather than hand-recoloring every dark-mode-specific prop
in the four Setup files, the Setup tab's root is wrapped in Chakra's `<LightMode>`
(exported by `@chakra-ui/react`, confirmed present in `node_modules`) — this locks the
color-mode context to light for that subtree only, so existing `colorScheme` usages
(green/red/orange/gray status badges and alerts) automatically render their light-mode
variants without any other tab's color mode changing. The four new flat-white tokens
(bg/text-primary/text-secondary/border) and the new `accent` (blue) / `tag` (amber) color
scales from §3 of the handoff doc are added as new top-level keys in `main.jsx`'s
`extendTheme` colors — additive only, no existing key (`gray`, `odrive`, `radii.md/lg`)
is modified, so no other tab's appearance changes. Card elevation switches from
`variant="elevated"` (box-shadow) to `variant="outline"` (1px border, no shadow) per the
"no drop shadows" rule in §3. Rounded-full is applied as an explicit `borderRadius="full"`
per Button/IconButton/Badge instance in the four Setup files rather than as a global
`Button` theme override, again to keep the change scoped to this one tab.

## UI redesign full roll-out — chart color palette and theme scoping

Once the Setup tab's look was approved and the same tokens were rolled out app-wide, two
choices from sub-phase 1 got revisited now that scope changed from "one tab" to "the whole
app":

**Theme scoping**: sub-phase 1 deliberately avoided touching `main.jsx`'s global theme
(`initialColorMode: 'dark'`) and instead wrapped just the Setup tab in Chakra's
`<LightMode>`, specifically so the rest of the still-dark app was unaffected. With the
roll-out now covering every tab, that per-tab scoping mechanism no longer serves a
purpose — flipping `initialColorMode` to `'light'` in the theme itself (plus the global
`body` styles and `Button`'s default `colorScheme`) is the correct fix at this scope, and
the `<LightMode>` wrapper was removed from `SetupTab.jsx` as redundant.

**Chart colors needed the `dataviz` skill, not a mechanical remap**: the existing dark-
theme telemetry charts (`TelemetryTimeSeriesChart.jsx`, shared by Control/Train/Testing/
Inspector) used pastel line colors (`#63B3ED` blue, `#68D391` green, `#F6E05E` yellow,
etc.) chosen for contrast against a dark background — several of these are close to
unreadable on white (e.g. the yellow is ~2:1 contrast). Rather than guessing replacement
hues, loaded the `dataviz` skill and used its validated reference categorical palette
(`references/palette.md`), substituting slot 1 with this app's own brand blue (`#2563eb`)
and validating the resulting 7-hue set with `scripts/validate_palette.js --mode light
--surface "#FFFFFF"` — all CVD/lightness/chroma gates passed; 3 of the 7 hues (aqua,
yellow, magenta) land below 3:1 contrast on white, which the skill calls out as requiring
"relief" (visible labels or a table view) rather than a hue swap — already satisfied here
since every chart always renders an on-screen `Legend`.

Per-chart color assignment is **not** a single fixed physical-quantity → color mapping
held across the whole app (e.g. "velocity is always hue X everywhere"). Several charts
render calibrated-vs-raw or measured-vs-setpoint pairs on **separate, non-shared Y axes**
(no `axisKey` linking them) rather than one axis with a dashed overlay — for those,
sharing one hue (the "target_position shares its axis-owner's hue, dashed" convention)
would have made two distinct axes look identical. Colors are instead assigned per chart,
in that chart's own fixed line order, so a chart's own N simultaneously-visible lines are
each guaranteed a distinct, validated hue — which is what the CVD-safety rule actually
requires (distinct color per entity *within a chart*, never reassigned by which lines are
toggled on/off), without chasing an unachievable global one-hue-per-signal mapping across
~9 distinct telemetry quantities spread across differently-shaped per-tab chart configs.

Separately: `AxisRangeControl.jsx` (the small "Auto | min–max" control next to each chart
line's checkbox) colored its own label *text* with the line's raw series color — directly
called out by the dataviz skill's own non-negotiables ("text wears text tokens, never the
series color"), and a real bug once several series' colors dropped below 3:1 on white.
Fixed by keeping the label in neutral ink and adding a small colored swatch dot next to it
instead, so color still carries the identity without the label itself losing legibility.

Also found **two stylesheets with real (not orphaned) dark backgrounds** that no amount of
Chakra prop remapping would have touched, since they're plain CSS painting behind Chakra's
own elements: `styles/DeviceList.css`'s `.device-list` (dark gradient sidebar background)
and `styles/InspectorTab.css`'s `.inspector-tab` (dark gradient). Both fixed. By contrast,
`App.css` and `styles/ConfigurationTab.css` turned out to be **entirely dead** — verified
by grepping actual `className` usage in the corresponding JSX before touching anything;
`ConfigurationTab.css` isn't even imported anywhere. Left both alone since editing unused
CSS has zero visual effect and isn't part of this pass.

## UI redesign full roll-out — low-contrast bug: stale `chakra-ui-color-mode` in localStorage

Flagged directly from a screenshot after the full roll-out: several **un-overridden**
Chakra defaults (an outline button's text, e.g. "Restart Freddy" / "Reset") were rendering
visibly pale/washed out — e.g. `orange.200` (`#FBD38D`, a pale peach) instead of the
expected `orange.600` (`#C05621`, a solid burnt orange) an outline button should use in
light mode. Everywhere a color was set via an explicit literal prop (e.g. this session's
own `color="accent.600"`/`color="paper.textPrimary"` additions) looked correct; only the
spots still relying on Chakra's own internal light/dark computation looked wrong — which
narrowed it down fast.

Root cause: `main.jsx`'s `config: { initialColorMode: 'light' }` only picks the color mode
Chakra starts with on a **fresh** browser profile. `ChakraProvider`'s `ColorModeProvider`
persists the resolved mode to `localStorage` (`chakra-ui-color-mode`) and prefers that
cached value over `initialColorMode` on every later load — and this exact browser profile
had already run the app under the old `initialColorMode: 'dark'` (both this session's own
`ODRIVE_MOCK=1` dev-server testing, and presumably real prior usage), so the cached value
was still `dark`. Every Chakra component whose variant styling calls `mode(lightValue,
darkValue)` internally (outline/ghost button text and borders, Badge's default `subtle`/
`outline` variants, Alert, etc.) was silently still resolving its **dark** branch, even
though the theme's own colors, fonts, and every explicitly-set prop were correctly light —
that split (some things right, some things wrong, no error, no obvious pattern from the
code alone) is what made this a real bug rather than an obviously-incomplete pass; it
would not have been caught by grepping for leftover `gray.*`/`odrive.*` tokens, since none
of the affected styles are literal props in this codebase — they come from Chakra's own
component theme internals.

Fixed by wrapping the whole app in Chakra's `<LightMode>` (`main.jsx`) — this app has
dropped dark mode entirely as part of the redesign, so forcing every `mode(light, dark)`
call to its light branch unconditionally, regardless of what's cached from before, is the
correct fix (not a workaround) — nobody needs to manually clear `localStorage` on their
own machine or browser profile for the app to render correctly. Separately, while looking
at this: bumped every Chakra component's default disabled-state `opacity: 0.4` (baked into
Button/Input/Select/Checkbox/Switch's own theme, `_disabled`) to `0.6` — a 0.4-opacity
control blends acceptably into a dark background but reads as nearly invisible on white —
and re-implemented the Button `outline` variant's `gray` colorScheme case, whose default
border (`gray.200`) was too close to the white background for this design's "structure
from the 1px border" principle to actually hold once genuinely in light mode.
