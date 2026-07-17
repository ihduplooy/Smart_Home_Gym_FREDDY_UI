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

## Planned contents (Session 3, not yet built)

- `core/profiles/` — resistance profiles (`base.py`'s `ResistanceProfile` and
  its subclasses: constant, bell-curve, eccentric-overload, VBT). Out of
  scope for Session 2 — do not create this package yet.

## Known follow-ups (flagged in-code, not solved — see docs/decisions.md)

- Two-connection conflict: `core/hardware/odrive_hw.py` and
  `backend/app/device_manager.py` each open their own USB handle
  independently; both grabbing the same device at once is unreconciled,
  `# TODO(2A)`.
- `enable_torque_mode_vel_limit` vs. profile-layer velocity behaviour — open
  item #8, `# TODO(2A)` at `TorqueMode`.
- `MOTOR_TORQUE_CONSTANT` (`config/board_constants.py`) is a placeholder
  pending motor characterisation — open item #2.
- Sim `SIM_INERTIA_J` / `SIM_DAMPING_B` (`core/hardware/sim_hw.py`) are
  placeholders; real values also come from characterisation.
