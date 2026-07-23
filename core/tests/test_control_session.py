import threading
import time
from typing import List

import pytest

from core.control.session import ControlSession
from core.hardware.interface import ControlMode, HardwareInterface, TelemetrySample
from core.hardware.sim_hw import SimHardware


class _FakeHardwareBase(HardwareInterface):
    """Minimal fake implementing the full contract; subclasses override the
    specific method under test."""

    def __init__(self):
        self.connected = False
        self.stop_calls = 0
        self.disconnect_calls = 0
        self._t = 0.0

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False
        self.disconnect_calls += 1

    @property
    def is_connected(self):
        return self.connected

    def get_state(self):
        self._t += 1.0
        return TelemetrySample(t=self._t, position=0.0, velocity=0.0, current_iq=0.0, torque_est=0.0)

    def set_mode(self, mode):
        pass

    def set_velocity_target(self, turns_per_s):
        pass

    def set_torque_target(self, nm):
        pass

    def set_position_target(self, turns, move_velocity, accel_decel, torque_limit=None):
        pass

    def set_current_limit(self, amps):
        pass

    def stop(self):
        self.stop_calls += 1

    def get_errors(self) -> List[str]:
        return []


class WedgedHardware(_FakeHardwareBase):
    """get_state() blocks forever, simulating a hung telemetry thread."""

    def __init__(self):
        super().__init__()
        self._never = threading.Event()

    def get_state(self):
        self._never.wait()  # blocks until the test process exits
        raise AssertionError("unreachable")


class CrashingHardware(_FakeHardwareBase):
    """get_state() raises on the second call (first call seeds a sample)."""

    def __init__(self):
        super().__init__()
        self._calls = 0

    def get_state(self):
        self._calls += 1
        if self._calls >= 2:
            raise RuntimeError("simulated telemetry read failure")
        return super().get_state()


class ErroringHardware(_FakeHardwareBase):
    """get_errors() reports a fault starting on the second call."""

    def __init__(self):
        super().__init__()
        self._calls = 0

    def get_errors(self):
        self._calls += 1
        if self._calls >= 2:
            return ["motor: SIMULATED_FAULT"]
        return []


class ConnectFailsHardware(_FakeHardwareBase):
    def connect(self):
        raise RuntimeError("No ODrive device found")


def _sim_session(**kwargs) -> ControlSession:
    return ControlSession(hardware_source="sim", **kwargs)


def _fake_session(fake_cls) -> ControlSession:
    return ControlSession(hardware_source="sim", hardware_factories={"sim": fake_cls, "real": fake_cls})


# ---- lifecycle ----

def test_start_retarget_stop():
    session = _sim_session()
    session.start("velocity", 0.5)
    status = session.status()
    assert status["running"] is True
    assert status["mode"] == "velocity"
    assert status["target"] == 0.5

    session.set_target(1.0)
    assert session.status()["target"] == 1.0

    session.stop()
    status = session.status()
    assert status["running"] is False


def test_torque_mode_lifecycle():
    session = _sim_session()
    session.start("torque", 0.2)
    time.sleep(0.1)
    status = session.status()
    assert status["running"] is True
    assert status["latest_sample"] is not None
    session.stop()
    assert session.status()["running"] is False


def test_double_start_refused():
    session = _sim_session()
    session.start("velocity", 0.5)
    with pytest.raises(RuntimeError):
        session.start("velocity", 0.5)
    session.stop()


def test_set_target_without_running_raises():
    session = _sim_session()
    with pytest.raises(RuntimeError):
        session.set_target(1.0)


def test_hardware_source_refused_while_running():
    session = _sim_session()
    session.start("velocity", 0.5)
    with pytest.raises(RuntimeError):
        session.set_hardware_source("real")
    session.stop()


def test_hardware_source_switchable_when_idle():
    session = _sim_session()
    session.set_hardware_source("real")
    assert session.get_hardware_source() == "real"
    session.set_hardware_source("sim")
    assert session.get_hardware_source() == "sim"


def test_unknown_mode_rejected():
    session = _sim_session()
    with pytest.raises(ValueError):
        session.start("bogus-mode", 1.0)
    assert session.status()["running"] is False


def test_unknown_hardware_source_rejected():
    with pytest.raises(ValueError):
        ControlSession(hardware_source="bogus")


# ---- safety behaviours ----

def test_stop_reaches_hardware_even_if_telemetry_thread_wedged():
    session = _fake_session(WedgedHardware)
    session.start("velocity", 1.0)
    hardware = session._hardware
    assert isinstance(hardware, WedgedHardware)

    start = time.monotonic()
    session.stop()
    elapsed = time.monotonic() - start

    assert hardware.stop_calls == 1
    assert elapsed < 3.0  # bounded by the join timeout, never blocks forever
    assert session.status()["running"] is False


def test_telemetry_loop_exception_auto_stops_and_marks_errored():
    session = _fake_session(CrashingHardware)
    session.start("velocity", 1.0)

    deadline = time.monotonic() + 2.0
    status = session.status()
    while status["running"] and time.monotonic() < deadline:
        time.sleep(0.02)
        status = session.status()

    assert status["running"] is False
    assert status["errored"] is True
    assert "Telemetry loop error" in status["error_message"]


def test_hardware_errors_trigger_auto_stop():
    session = _fake_session(ErroringHardware)
    session.start("velocity", 1.0)

    deadline = time.monotonic() + 2.0
    status = session.status()
    while status["running"] and time.monotonic() < deadline:
        time.sleep(0.02)
        status = session.status()

    assert status["running"] is False
    assert status["errored"] is True
    assert status["errors"] == ["motor: SIMULATED_FAULT"]


def test_start_failure_leaves_session_idle_and_clean():
    session = _fake_session(ConnectFailsHardware)
    with pytest.raises(RuntimeError, match="No ODrive device found"):
        session.start("velocity", 1.0)
    status = session.status()
    assert status["running"] is False
    assert status["latest_sample"] is None


def test_stop_idempotent_and_callable_without_a_session():
    session = _sim_session()
    session.stop()  # never started — must not raise
    session.stop()  # repeated call — must not raise


def test_samples_since_filters_ring_buffer():
    session = _sim_session()
    session.start("velocity", 0.5)
    time.sleep(0.15)
    all_samples = session.samples_since()
    assert len(all_samples) > 0
    cutoff = all_samples[len(all_samples) // 2].t
    filtered = session.samples_since(cutoff)
    assert all(s.t > cutoff for s in filtered)
    session.stop()
