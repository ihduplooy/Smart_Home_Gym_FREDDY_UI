import time

import pytest

from core.control.session import ControlSession
from core.profiles import ConstantProfile, OverloadWrapper, Phase, ProfileState, ResistanceProfile


def _sim_session(**kwargs) -> ControlSession:
    return ControlSession(hardware_source="sim", **kwargs)


class _RaisingProfile(ResistanceProfile):
    name = "raising"

    def compute_torque(self, state: ProfileState) -> float:
        raise RuntimeError("simulated profile math failure")

    def describe(self):
        return {"name": self.name, "is_wrapper": False, "primary_parameter": "x", "parameters": {}}

    @property
    def primary_parameter_label(self) -> str:
        return "x"

    def get_primary_parameter(self) -> float:
        return 0.0

    def set_primary_parameter(self, value: float) -> None:
        pass

    def reset(self) -> None:
        pass


def test_profile_mode_runs_end_to_end_against_sim():
    session = _sim_session()
    profile = ConstantProfile(base_force_n=50.0)
    session.start(mode="profile", target=profile)
    time.sleep(0.1)

    status = session.status()
    assert status["running"] is True
    assert status["mode"] == "profile"
    assert status["target"] == 50.0  # primary parameter, not the raw profile object
    assert status["phase"] is not None
    assert status["rep_count"] == 0
    assert status["latest_sample"] is not None

    session.stop()
    assert session.status()["running"] is False


def test_profile_mode_retarget_adjusts_primary_parameter_not_the_profile_object():
    session = _sim_session()
    profile = ConstantProfile(base_force_n=50.0)
    session.start(mode="profile", target=profile)

    session.set_target(75.0)
    assert session.status()["target"] == 75.0
    assert profile.get_primary_parameter() == 75.0  # same object, adjusted in place

    session.stop()


def test_profile_mode_csv_filename_includes_profile_name():
    session = _sim_session()
    profile = ConstantProfile(base_force_n=10.0)
    session.start(mode="profile", target=profile)
    time.sleep(0.05)
    log_path = session.status()["log_path"]
    session.stop()

    assert log_path is not None
    assert "_profile-constant_sim.csv" in log_path


def test_profile_mode_csv_gains_phase_and_rep_count_columns():
    import csv as csv_module

    session = _sim_session()
    profile = ConstantProfile(base_force_n=10.0)
    session.start(mode="profile", target=profile)
    time.sleep(0.1)
    log_path = session.status()["log_path"]
    session.stop()

    with open(log_path, newline="") as f:
        rows = list(csv_module.reader(f))
    header = rows[0]
    assert header[-2:] == ["phase", "rep_count"]
    data_row = rows[1]
    assert data_row[-2] in {p.value for p in Phase}
    assert data_row[-1].isdigit()


def test_velocity_mode_csv_leaves_phase_and_rep_count_columns_empty():
    import csv as csv_module

    session = _sim_session()
    session.start(mode="velocity", target=0.5)
    time.sleep(0.1)
    log_path = session.status()["log_path"]
    session.stop()

    with open(log_path, newline="") as f:
        rows = list(csv_module.reader(f))
    data_row = rows[1]
    assert data_row[-2] == ""
    assert data_row[-1] == ""


def test_profile_with_overload_wrapper_runs_end_to_end():
    session = _sim_session()
    base = ConstantProfile(base_force_n=30.0)
    wrapped = OverloadWrapper(wrapped=base, ratio=1.35, target_phase=Phase.ECCENTRIC)
    session.start(mode="profile", target=wrapped)
    time.sleep(0.1)
    status = session.status()
    assert status["running"] is True
    assert status["target"] == 30.0  # primary parameter passes through the wrapper
    session.stop()


def test_profile_compute_torque_raising_auto_stops_session():
    session = _sim_session()
    session.start(mode="profile", target=_RaisingProfile())

    deadline = time.monotonic() + 2.0
    status = session.status()
    while status["running"] and time.monotonic() < deadline:
        time.sleep(0.02)
        status = session.status()

    assert status["running"] is False
    assert status["errored"] is True
    assert "simulated profile math failure" in status["error_message"]


def test_profile_mode_rejects_starting_without_a_resistance_profile():
    session = _sim_session()
    with pytest.raises(TypeError):
        session.start(mode="profile", target="not-a-profile")
