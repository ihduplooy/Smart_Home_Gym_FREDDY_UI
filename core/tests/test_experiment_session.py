"""ExperimentMode wired through the real ControlSession against SimHardware --
the end-to-end path (configure -> confirm_start -> RAMPING -> LIFTING ->
HOLDING), CSV correctness, and Stop from each of the three running states
(Testing tab Build Spec §7 Definition of Done's explicit ask). Unlike
test_experiment_mode.py's RecordingHardware fake, this drives the real 50 Hz
telemetry thread and SimHardware's own dynamics, so timings are tuned to be
fast and reliable rather than physically realistic.
"""

import csv as csv_module
import time

import pytest

from core.cable.state import CableState
from core.control.modes import MODES_BY_NAME
from core.control.session import ControlSession
from core.experiments.mode import ExperimentMode


def _homed_cable_state(tmp_path, max_turns=100000.0):
    cs = CableState(sidecar_path=tmp_path / "s.json", growth_sidecar_path=tmp_path / "g.json")
    cs.latch_home(0.0)
    cs.set_max(marked_turns=max_turns, enforced_turns=max_turns)
    return cs


def _session(cable_state) -> ControlSession:
    return ControlSession(
        hardware_source="sim",
        mode_factories={**MODES_BY_NAME, "experiment": lambda: ExperimentMode(cable_state)},
    )


def _config_dict(**overrides):
    base = dict(
        known_weight_kg=1.0,
        initial_position_m=0.0,
        target_position_m=0.05,
        initial_torque_nm=1.0,
        torque_ramp_rate_nm_per_s=2.0,
        movement_threshold_m_per_s=0.02,
        hold_deadband_m=0.01,
        hold_gain=5.0,
        max_torque_nm=5.0,
        max_duration_s=5.0,
    )
    base.update(overrides)
    return base


def _wait_for_experiment_state(session, expected, timeout=3.0):
    deadline = time.monotonic() + timeout
    status = session.status()
    while status.get("extra", {}).get("experiment_state") != expected and time.monotonic() < deadline:
        time.sleep(0.02)
        status = session.status()
    return status


def test_experiment_runs_end_to_end_and_csv_has_correct_columns(tmp_path):
    cable_state = _homed_cable_state(tmp_path)
    session = _session(cable_state)

    session.start(mode="experiment", target={"action": "configure", "experiment": "static_hold", "config": _config_dict()})
    status = _wait_for_experiment_state(session, "configured", timeout=1.0)
    assert status["extra"]["experiment_state"] == "configured"

    session.set_target({"action": "confirm_start"})

    status = _wait_for_experiment_state(session, "holding", timeout=3.0)
    assert status["extra"]["experiment_state"] == "holding"
    assert status["running"] is True

    log_path = status["log_path"]
    session.stop()
    assert session.status()["running"] is False

    with open(log_path, newline="") as f:
        rows = list(csv_module.reader(f))
    header = rows[0]
    for col in ("experiment_state", "position_m", "velocity_m_s", "commanded_torque_nm", "bus_voltage_v", "estimated_power_w", "target_position_m"):
        assert col in header

    states_seen = {row[header.index("experiment_state")] for row in rows[1:]}
    assert states_seen  # at least one populated row
    assert "" not in states_seen  # every row while this experiment ran had a label


def test_stop_from_ramping(tmp_path):
    cable_state = _homed_cable_state(tmp_path)
    session = _session(cable_state)
    # Absurdly high movement threshold -- never trips, guaranteed RAMPING.
    config = _config_dict(movement_threshold_m_per_s=1000.0, max_duration_s=30.0)
    session.start(mode="experiment", target={"action": "configure", "experiment": "static_hold", "config": config})
    session.set_target({"action": "confirm_start"})
    time.sleep(0.1)

    assert session.status()["extra"]["experiment_state"] == "ramping"
    session.stop()
    assert session.status()["running"] is False


def test_stop_from_lifting(tmp_path):
    cable_state = _homed_cable_state(tmp_path)
    session = _session(cable_state)
    # Target far away -- reaches LIFTING quickly but takes a long time to
    # arrive, so a brief sleep reliably lands inside LIFTING.
    config = _config_dict(target_position_m=500.0, max_duration_s=30.0)
    session.start(mode="experiment", target={"action": "configure", "experiment": "static_hold", "config": config})
    session.set_target({"action": "confirm_start"})

    status = _wait_for_experiment_state(session, "lifting", timeout=2.0)
    assert status["extra"]["experiment_state"] == "lifting"
    session.stop()
    assert session.status()["running"] is False


def test_stop_from_holding(tmp_path):
    cable_state = _homed_cable_state(tmp_path)
    session = _session(cable_state)
    config = _config_dict()
    session.start(mode="experiment", target={"action": "configure", "experiment": "static_hold", "config": config})
    session.set_target({"action": "confirm_start"})

    status = _wait_for_experiment_state(session, "holding", timeout=3.0)
    assert status["extra"]["experiment_state"] == "holding"
    session.stop()
    assert session.status()["running"] is False


def test_max_torque_breach_aborts_and_stops_hardware(tmp_path):
    cable_state = _homed_cable_state(tmp_path)
    session = _session(cable_state)
    config = _config_dict(
        initial_torque_nm=0.1,
        torque_ramp_rate_nm_per_s=5.0,
        movement_threshold_m_per_s=1000.0,  # stay RAMPING so the ramp keeps climbing
        max_torque_nm=0.5,
        max_duration_s=30.0,
    )
    session.start(mode="experiment", target={"action": "configure", "experiment": "static_hold", "config": config})
    session.set_target({"action": "confirm_start"})

    status = _wait_for_experiment_state(session, "aborted", timeout=2.0)
    assert status["extra"]["experiment_state"] == "aborted"
    session.stop()


def test_max_duration_elapses_to_complete(tmp_path):
    cable_state = _homed_cable_state(tmp_path)
    session = _session(cable_state)
    config = _config_dict(max_duration_s=0.2, target_position_m=500.0)  # never reaches target in time
    session.start(mode="experiment", target={"action": "configure", "experiment": "static_hold", "config": config})
    session.set_target({"action": "confirm_start"})

    status = _wait_for_experiment_state(session, "complete", timeout=2.0)
    assert status["extra"]["experiment_state"] == "complete"
    session.stop()


def test_start_rejects_when_not_homed(tmp_path):
    cable_state = CableState(sidecar_path=tmp_path / "s.json", growth_sidecar_path=tmp_path / "g.json")
    session = _session(cable_state)
    with pytest.raises(RuntimeError):
        session.start(
            mode="experiment",
            target={"action": "configure", "experiment": "static_hold", "config": _config_dict()},
        )
