# core/ — hardware interface, control, telemetry, profiles

All cable-resistance control logic lives here — the GUI (`backend/`,
`frontend/`) is presentation only.

## The split rule

**GUI calls into `core/`, never the reverse.** `backend/` route handlers call
functions/classes exposed by `core/`; `core/` never imports from `backend/` or
knows anything about Flask, HTTP, or the frontend. This keeps the control
logic testable and swappable (real ODrive vs. mock) independent of the GUI.
`core/` may import `config.board_constants` (plain data) and the `odrive`
package (inside `hardware/odrive_hw.py` only, lazily) — nothing else
project-side.

## Layout (Session 2, built)

```
core/
  hardware/
    interface.py     # HardwareInterface ABC + TelemetrySample dataclass
    odrive_hw.py      # real implementation (wraps the odrive lib)
    sim_hw.py         # dynamic simulated implementation (motor model)
    _macos_usb.py      # shared Apple Silicon libusb path fix
  control/
    modes.py          # VelocityMode, TorqueMode
    session.py        # ControlSession: owns mode + telemetry loop + logger lifecycle
  telemetry/
    csv_logger.py
  tests/               # plain pytest, runnable with no hardware and no Flask
```

Units are ODrive 0.5.1 native throughout: turns, turns/s, Nm, A. No degrees,
no counts. Cable-linear conversions (spool radius) are Session 3's business.

Run the test suite (no hardware, no Flask required):

```
python -m pytest core/tests
```

## Programmatic torque mode (Session 3's entry point)

Torque mode is a programmatic API, not GUI-only — Session 3's profile loop
calls it directly, in a loop, without any Flask process running. Minimal
example, run against the sim:

```python
from core.control.session import ControlSession

session = ControlSession(hardware_source="sim")
session.start(mode="torque", target=0.3)  # Nm
print(session.status()["latest_sample"])
session.stop()
```

Swap `hardware_source="real"` to run the same code against actual hardware
(Phase 2A) — nothing else in the call changes.

## Resistance profiles (Session 3's entry point)

Profiles run as a third mode (`mode="profile"`) inside the same `ControlSession`
loop above — no separate thread, no separate API. The "target" is a
`ResistanceProfile` instance; live retargeting afterward takes a plain number
(the profile's primary parameter, e.g. base force in Newtons). Minimal example,
run against the sim, no Flask:

```python
import time
from core.control.session import ControlSession
from core.profiles import ConstantProfile

session = ControlSession(hardware_source="sim")
session.start(mode="profile", target=ConstantProfile(base_force_n=50.0))
time.sleep(0.1)  # give the 50 Hz telemetry thread a tick before reading status
print(session.status()["latest_sample"], session.status()["phase"], session.status()["rep_count"])
session.stop()
```

All four stubs (`ConstantProfile`, `BellCurveProfile`, `OverloadWrapper`,
`VBTProfile`) live in `core/profiles/` and share the `ResistanceProfile` ABC
(`base.py`) — see `core/profiles/__init__.py`'s `PROFILE_REGISTRY` for the
full set. Every stub's math is a placeholder (`# STUB(2A+)`); the interface
shape is this session's deliverable, not the numbers.

## Layout addition (Session 3)

```
core/
  ...
  profiles/
    units.py          # force_to_torque / torque_to_force (the ONLY spool-radius site)
    detectors.py       # Phase enum, PhaseDetector, RepCounter, ProfileState
    base.py            # ResistanceProfile ABC
    constant.py, bell_curve.py, overload.py, vbt.py   # the 4 stubs
```

## Known follow-ups (flagged in-code, not solved — see docs/decisions.md)

- Two-connection conflict: `core/hardware/odrive_hw.py` and
  `backend/app/device_manager.py` each open their own USB handle
  independently; both grabbing the same device at once is unreconciled,
  `# TODO(2A)`.
- `enable_torque_mode_vel_limit` vs. profile-layer velocity behaviour — open
  item #8, `# TODO(2A)` at `TorqueMode` and (now directly load-bearing)
  `ProfileMode` in `core/control/modes.py`.
- `MOTOR_TORQUE_CONSTANT` (`config/board_constants.py`) is a placeholder
  pending motor characterisation — open item #2.
- Sim `SIM_INERTIA_J` / `SIM_DAMPING_B` (`core/hardware/sim_hw.py`) are
  placeholders; real values also come from characterisation.
- `SPOOL_RADIUS_M`, `ECCENTRIC_OVERLOAD_RATIO_DEFAULT`, and every phase/rep
  detector tuning constant (`config/board_constants.py`) are placeholders —
  `# TODO(2A)`, tune against real cable motion.
- All four profile stubs' math (`core/profiles/`) — `# STUB(2A+)`, interface
  shape only.
