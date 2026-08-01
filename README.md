# Smart Gym Control

GUI + control software for a motor-driven cable resistance training system
(Stellenbosch Mechatronic Engineering skripsie — Ivan du Plooy, 27668266).
Nicknamed **Freddy**.

The motor controller is an **MKS ODrive Mini V1.0** (an ODrive v3.6 clone) on
**firmware v0.5.1 — never upgrade; v0.5.6 breaks motor activation on this clone.**
Feedback is the onboard **AS5047P** encoder (SPI, CS pin 7 on this board). The motor
is a **hoverboard BLDC hub motor, 15 pole pairs**, driving a cable/spool. Phase 2A
(live hardware bring-up) is underway — real hardware is wired up and this GUI is
the primary day-to-day tool now, not just a bench-testing scaffold. Everything
also still runs with no ODrive attached via a built-in mock device
(`ODRIVE_MOCK=1` / `npm run mock_dev`).

Originally a trimmed, rebranded fork of
[MoonLighTingPY/odrive3.6_web_gui](https://github.com/MoonLighTingPY/odrive3.6_web_gui)
(React + Vite frontend, Flask backend) — the raw property-tree/config-wizard
layer is still that fork's lineage, but almost everything cable/training-related
(`core/`, the Train tab, Configuration wizard defaults) is project-specific code
built on top of it since.

## Repo layout

See `INDEX.md` for the full, regenerated directory tree. Summary:

```
smart-gym-control/
├── backend/           # Flask backend: generic ODrive property read/write/command
│                       # over REST + a telemetry WebSocket, plus control/exercise/
│                       # force/train routes. All ODrive access goes through one
│                       # module (backend/app/device_manager.py).
├── frontend/           # React + Vite GUI: Configuration, Control, Train, Inspector
│                       # tabs (see "Tabs" below).
├── core/               # Hardware-agnostic control logic: modes (velocity/torque/
│                       # position/profile), ControlSession orchestrator, the
│                       # cable/ package (ExerciseMode, TrainMode, CableState,
│                       # homing/limits/letgo/governor), resistance profiles,
│                       # CSV telemetry. See core/README.md for the GUI/core split.
├── config/
│   ├── board_constants.py     # single source of truth: firmware, motor, encoder,
│   │                          # axis, and every live-tunable setting's fallback default
│   ├── odrive_config.py       # the Phase 1B ODrive bring-up script (terminal-run
│   │                          # on real hardware; not run by the GUI)
│   └── diagnose_encoder_spi.py / odrive_diag_common.py  # read-only bench
│                          # diagnostics for encoder/SPI issues
└── docs/
    ├── decisions.md      # what was stripped/changed from upstream (and later,
    │                      # project-specific design decisions), and why — append-only
    ├── progress.md        # build-session checklist — append-only
    └── user_manual.md / manual.html   # end-user "how do I use it" guide
```

## Prerequisites (macOS, Apple Silicon)

- pyenv with Python **3.9.18** (`pyenv install 3.9.18`) — must match `odrive==0.5.1.post0`
- `brew install libusb`
- Node.js 18+ with npm

## Setup

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Frontend
cd frontend
npm install
```

## Run in development

**Easiest**: double-click `Start Freddy.command` from Finder — kills any stale
backend/frontend on ports 5050/3000, starts both fresh against **real hardware**
(no `ODRIVE_MOCK`), waits for both to come up, then opens Safari. Use
`Stop Freddy.command` to shut both down (they're detached/`nohup`'d, so closing
the Terminal window alone won't stop them).

Manually, with the backend venv active, from the project root:

```bash
source .venv/bin/activate
python backend/start_backend.py     # real hardware — NOT the same as the frontend's
                                     # own concurrently-launched backend, see below
```

```bash
cd frontend
npm run dev:frontend   # real hardware — talks to the backend started above
npm run mock_dev        # no hardware needed — spins up its own mock backend + frontend together
```

**Important**: `npm run dev:frontend` (frontend only) is the correct real-hardware
command once a backend is already running via `start_backend.py` or
`Start Freddy.command`. Plain `npm run dev` spins up a *second* backend via
`concurrently`, using its own (non-activated) Python env — this can miss Flask
entirely and risks a second process contending for the same USB device. Use
`mock_dev` for hardware-free work instead.

The UI is served at `http://localhost:3000` and proxies the API and telemetry
WebSocket to the Flask backend on `http://127.0.0.1:5050` (not 5000 — that
port collides with macOS's own AirPlay Receiver).

## Tests

```bash
cd frontend && npm test       # vitest unit tests
cd frontend && npm run lint   # eslint
cd .. && pytest core/tests    # core/ control logic unit tests (with venv active)
```

## Tabs (frontend)

Four tabs as of 28 July 2026 (`frontend/src/components/MainTabs.jsx`):

1. **Configuration** — guided config wizard, writes this board's known-good
   settings to a connected device.
2. **Control** — raw velocity/torque/position control, no cable required.
   Position mode's Move Distance field has a turns/metres toggle.
3. **Train** — the primary day-to-day tab once a cable is attached: homing,
   max-extension calibration, spool calibration (its collapsible
   "Settings / Startup" section), position-based resistance profiles
   (segments — constant/linear/bell — with save/load), and two live graphs
   (time-series + force-vs-position).
4. **Inspector** — full raw ODrive property tree.

A persistent sidebar (`DeviceList.jsx`) is available regardless of tab:
connect/scan/reset the device, **EMERGENCY STOP**, and **Go Home** (jogs the
cable back to its homed position from anywhere in the app). `App.jsx`'s top
bar also has a **Restart Freddy** button (full backend process restart).

Earlier standalone Exercise, Dashboard, Presets, and Profiles tabs have been
removed — homing/calibration moved into Train's Settings section (same
backend routes, same `CableState`). **Note**: `ExerciseMode`'s force-feedback
(Engage/Disengage constant/isokinetic resistance) and `core/profiles/`'s
phase/rep-aware resistance profiles (bell-curve, VBT, eccentric overload) are
still fully implemented and tested but currently have **no frontend tab** —
see `docs/decisions.md` ("Frontend consolidation to four tabs") for why this
is flagged as an open question rather than settled.

## Architecture

- **Thin backend** (Flask): generic, firmware-line-aware endpoints that read/write/
  invoke ODrive properties by dotted path, plus a telemetry WebSocket, plus
  higher-level control/exercise/force/train routes. All ODrive device access —
  real or mock (`ODRIVE_MOCK=1`) — goes through the single choke point in
  `backend/app/device_manager.py`.
- **`core/` is hardware-agnostic** and holds the real control logic: a hardware
  interface ABC (real ODrive wrapper + sim), `MODES_BY_NAME` (velocity/torque/
  position/profile) plus `"exercise"`/`"train"` injected via a `mode_factories`
  override on `ControlSession`, the `cable/` package (`ExerciseMode`,
  `TrainMode`, `CableState` — the single persisted-settings singleton),
  `core/profiles/`'s resistance-profile system, and CSV telemetry.
- **Data-driven frontend** (React + Vite + Chakra UI): a registry built from
  `frontend/src/utils/odriveApiReference05x.json` (this board's firmware line) drives
  the property tree, config wizard, validation, and command generation.
- **Single axis, single device**: this board only ever drives axis0 (axis1 is a
  ghost node, silenced via CAN node ID 63). Multi-axis and multi-device UI from
  upstream have been removed; see `docs/decisions.md`.

## Fork notes

Cloned from upstream (kept as a git remote, `upstream`) rather than GitHub-forked —
this is a one-way, personal fork with no upstream PR flow. See `docs/decisions.md`
for a full log of what was stripped from upstream and why (plus later,
project-specific design decisions), and `docs/progress.md` for the build-session
checklist.
