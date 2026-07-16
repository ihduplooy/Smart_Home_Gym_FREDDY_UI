# Smart Gym Control

Raw-testing GUI for a motor-driven cable resistance training system (Stellenbosch
Mechatronic Engineering skripsie — Ivan du Plooy, 27668266).

The motor controller is an **MKS ODrive Mini V1.0** (an ODrive v3.6 clone) on
**firmware v0.5.1 — never upgrade; v0.5.6 breaks motor activation on this clone.**
Feedback is the onboard **AS5047P** encoder (SPI, CS pin 7 on this board). The motor
is a **hoverboard BLDC hub motor, 15 pole pairs**. No hardware is wired up yet — that's
Phase 2A of this project; everything here runs and is testable with no ODrive
attached.

This is a trimmed, rebranded fork of
[MoonLighTingPY/odrive3.6_web_gui](https://github.com/MoonLighTingPY/odrive3.6_web_gui)
(React + Vite frontend, Flask backend). It's the tool Phase 2A uses to poke the bare
motor once it's wired — encoder sanity, live telemetry, direct commands, calibration —
before any control-mode software exists. `core/` (Session 2+) is where the actual
control logic goes; this GUI is presentation only.

## Repo layout

```
smart-gym-control/
├── backend/          # Flask backend: generic ODrive property read/write/command
│                      # over REST + a telemetry WebSocket. All ODrive access goes
│                      # through one module (backend/app/device_manager.py).
├── frontend/          # React + Vite GUI: config wizard, Inspector, live charts,
│                      # dashboard, command console, calibration flows.
├── core/              # Empty placeholder — Session 2+ builds the real control
│                      # logic here. See core/README.md for the GUI/core split rule.
├── config/
│   ├── board_constants.py  # single source of truth: firmware, motor, encoder, axis
│   └── odrive_config.py    # the Phase 1B ODrive setup script (run on real hardware
│                            # in Phase 2A; not run by the GUI)
└── docs/
    ├── decisions.md   # what was stripped/changed from upstream, and why
    └── progress.md    # build-session checklist
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

From `frontend/`, with the backend venv active:

```bash
npm run dev        # backend + frontend, real hardware
npm run mock_dev    # backend + frontend, simulated device (no hardware needed)
```

The UI is served at `http://localhost:3000` and proxies the API and telemetry
WebSocket to the Flask backend on `http://127.0.0.1:5000`.

## Tests

```bash
cd frontend && npm test       # vitest unit tests
cd frontend && npm run lint   # eslint
```

## Architecture

- **Thin backend** (Flask): generic, firmware-line-aware endpoints that read/write/
  invoke ODrive properties by dotted path, plus a telemetry WebSocket. All ODrive
  device access — real or mock (`ODRIVE_MOCK=1`) — goes through the single choke
  point in `backend/app/device_manager.py`, so Session 2 can swap in `core/`'s
  hardware-interface layer without a backend refactor.
- **Data-driven frontend** (React + Vite + Chakra UI): a registry built from
  `frontend/src/utils/odriveApiReference05x.json` (this board's firmware line) drives
  the property tree, config wizard, validation, and command generation.
- **Single axis, single device**: this board only ever drives axis0 (axis1 is a
  ghost node, silenced via CAN node ID 63 — a Phase 2B concern, recorded in
  `config/board_constants.py`). Multi-axis and multi-device UI from upstream have
  been removed; see `docs/decisions.md`.

## Fork notes

Cloned from upstream (kept as a git remote, `upstream`) rather than GitHub-forked —
this is a one-way, personal fork with no upstream PR flow. See `docs/decisions.md`
for a full log of what was stripped from upstream and why, and `docs/progress.md`
for this build session's checklist.
