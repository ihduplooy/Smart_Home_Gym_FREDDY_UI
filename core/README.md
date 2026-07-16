# core/ — hardware interface, control, telemetry, profiles

Empty placeholder for Session 2 and 3. This package is where all cable-resistance
control logic lives — the GUI (`backend/`, `frontend/`) is presentation only.

## The split rule

**GUI calls into `core/`, never the reverse.** `backend/` route handlers call
functions/classes exposed by `core/`; `core/` never imports from `backend/` or knows
anything about Flask, HTTP, or the frontend. This keeps the control logic testable and
swappable (real ODrive vs. mock) independent of the GUI.

Planned contents (from the Session 1 build spec, §9–§10 — subject to revision during
their own HOW passes):

- `core/hardware/` — `odrive_interface.py` (real hardware, wraps the single connection
  choke point in `backend/app/device_manager.py`) and `mock_odrive.py` (simulated
  position/velocity/current). Selection via a config flag surfaced in the GUI.
- `core/control/` — velocity mode, torque mode: thin wrappers setting ODrive control
  mode + target, plus start/stop state handling.
- `core/telemetry/` — CSV logger: timestamp, position, velocity, torque/current-derived
  force.
- `core/profiles/` — resistance profiles (`base.py`'s `ResistanceProfile` and its
  subclasses: constant, bell-curve, eccentric-overload, VBT).

Nothing under `core/` is implemented yet — it exists now so the architecture boundary
is visible in the tree before there's any temptation to put control logic in backend
route handlers.
