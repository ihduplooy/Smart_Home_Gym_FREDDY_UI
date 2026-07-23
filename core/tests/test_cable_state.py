"""core/cable/state.py tests -- persistence split (spec §6): home/max are
in-memory only, k persists across a fresh CableState() (simulating a backend
restart)."""

from config import board_constants
from core.cable.state import CableState


def _tmp_sidecar(tmp_path):
    return tmp_path / "spool_calibration.json"


def test_fresh_state_is_unhomed_and_has_default_k(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path))
    assert state.is_homed is False
    assert state.has_max is False
    assert state.k == board_constants.SPOOL_CORRECTION_K_DEFAULT


def test_latch_home_sets_is_homed(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path))
    state.latch_home(12.5)
    assert state.is_homed is True
    assert state.home_turns == 12.5


def test_latching_a_new_home_invalidates_previous_max(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path))
    state.latch_home(0.0)
    state.set_max(marked_turns=10.0, enforced_turns=9.0)
    assert state.has_max is True

    state.latch_home(1.0)  # re-homed -- old max no longer trustworthy
    assert state.has_max is False
    assert state.max_turns is None
    assert state.marked_max_turns is None


def test_reset_clears_home_and_max_but_not_k(tmp_path):
    state = CableState(sidecar_path=_tmp_sidecar(tmp_path))
    state.set_k(0.0003)
    state.latch_home(0.0)
    state.set_max(marked_turns=10.0, enforced_turns=9.0)

    state.reset()

    assert state.is_homed is False
    assert state.has_max is False
    assert state.k == 0.0003  # untouched -- physical spool property


# ---- persistence split: k survives a fresh instance, home/max never do ----

def test_k_persists_across_a_fresh_instance_simulating_backend_restart(tmp_path):
    sidecar = _tmp_sidecar(tmp_path)

    state1 = CableState(sidecar_path=sidecar)
    state1.set_k(0.00042)
    state1.latch_home(5.0)
    state1.set_max(marked_turns=15.0, enforced_turns=14.0)

    # A fresh instance against the same sidecar path simulates a backend
    # restart: k must survive, home/max must NOT (spec §6 hard requirement).
    state2 = CableState(sidecar_path=sidecar)
    assert state2.k == 0.00042
    assert state2.is_homed is False
    assert state2.has_max is False


def test_missing_sidecar_file_falls_back_to_default_k(tmp_path):
    sidecar = tmp_path / "does_not_exist.json"
    state = CableState(sidecar_path=sidecar)
    assert state.k == board_constants.SPOOL_CORRECTION_K_DEFAULT


def test_corrupt_sidecar_file_falls_back_to_default_k(tmp_path):
    sidecar = _tmp_sidecar(tmp_path)
    sidecar.write_text("not valid json{{{")
    state = CableState(sidecar_path=sidecar)
    assert state.k == board_constants.SPOOL_CORRECTION_K_DEFAULT
