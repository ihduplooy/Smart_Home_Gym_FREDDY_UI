"""core/experiments/ tests -- pure Experiment/StaticWeightHoldExperiment state
machine, no HardwareInterface fake needed (see base.py's module docstring for
why step() is deliberately hardware-free). ExperimentMode's own hardware-write
wiring is covered separately in test_experiment_mode.py.
"""

import pytest

from core.cable.geometry import turns_delta_from_length
from core.cable.state import CableState
from core.experiments.base import ExperimentConfig, ExperimentState
from core.experiments.static_hold import StaticWeightHoldExperiment
from core.hardware.interface import TelemetrySample


def _cable_state(tmp_path, home=0.0, max_turns=None):
    cs = CableState(
        sidecar_path=tmp_path / "spool_calibration.json",
        growth_sidecar_path=tmp_path / "spool_growth_calibration.json",
    )
    cs.latch_home(home)
    if max_turns is not None:
        cs.set_max(marked_turns=max_turns, enforced_turns=max_turns)
    return cs


def _config(**overrides):
    base = dict(
        known_weight_kg=1.0,
        initial_position_m=0.0,
        target_position_m=1.0,
        initial_torque_nm=0.1,
        torque_ramp_rate_nm_per_s=0.05,
        movement_threshold_m_per_s=0.01,
        hold_deadband_m=0.005,
        hold_gain=5.0,
        max_torque_nm=2.0,
        max_duration_s=60.0,
    )
    base.update(overrides)
    return ExperimentConfig(**base)


def _sample(position=0.0, velocity=0.0, t=0.0):
    return TelemetrySample(t=t, position=position, velocity=velocity, current_iq=0.0, torque_est=0.0)


def _turns_for_length(cs, length_m):
    return cs.home_turns + turns_delta_from_length(length_m, cs.r0, cs.k)


class TestConfigure:
    def test_rejects_when_not_homed(self, tmp_path):
        cs = CableState(sidecar_path=tmp_path / "s.json", growth_sidecar_path=tmp_path / "g.json")
        exp = StaticWeightHoldExperiment(cs)
        with pytest.raises(RuntimeError):
            exp.configure(_config())

    def test_rejects_when_no_max_set(self, tmp_path):
        cs = _cable_state(tmp_path, home=0.0, max_turns=None)
        exp = StaticWeightHoldExperiment(cs)
        with pytest.raises(RuntimeError):
            exp.configure(_config())

    def test_rejects_target_out_of_range(self, tmp_path):
        cs = _cable_state(tmp_path, home=0.0, max_turns=10.0)
        exp = StaticWeightHoldExperiment(cs)
        with pytest.raises(ValueError):
            exp.configure(_config(target_position_m=1000.0))

    @pytest.mark.parametrize(
        "field,value",
        [
            ("torque_ramp_rate_nm_per_s", 0.0),
            ("movement_threshold_m_per_s", -0.1),
            ("hold_deadband_m", 0.0),
            ("hold_gain", -1.0),
            ("max_torque_nm", 0.0),
            ("max_duration_s", -1.0),
        ],
    )
    def test_rejects_invalid_thresholds(self, tmp_path, field, value):
        cs = _cable_state(tmp_path, home=0.0, max_turns=10.0)
        exp = StaticWeightHoldExperiment(cs)
        with pytest.raises(ValueError):
            exp.configure(_config(**{field: value}))

    def test_rejects_initial_torque_exceeding_max(self, tmp_path):
        cs = _cable_state(tmp_path, home=0.0, max_turns=10.0)
        exp = StaticWeightHoldExperiment(cs)
        with pytest.raises(ValueError):
            exp.configure(_config(initial_torque_nm=5.0, max_torque_nm=1.0))

    def test_configure_then_start_transitions_to_ramping(self, tmp_path):
        cs = _cable_state(tmp_path, home=0.0, max_turns=10.0)
        exp = StaticWeightHoldExperiment(cs)
        exp.configure(_config())
        assert exp.state == ExperimentState.CONFIGURED
        exp.start()
        assert exp.state == ExperimentState.RAMPING

    def test_start_before_configure_raises(self, tmp_path):
        cs = _cable_state(tmp_path, home=0.0, max_turns=10.0)
        exp = StaticWeightHoldExperiment(cs)
        with pytest.raises(RuntimeError):
            exp.start()


class TestStateMachine:
    def _started(self, tmp_path, **config_overrides):
        cs = _cable_state(tmp_path, home=0.0, max_turns=10.0)
        exp = StaticWeightHoldExperiment(cs)
        exp.configure(_config(**config_overrides))
        exp.start()
        return cs, exp

    def test_ramping_holds_until_movement_threshold(self, tmp_path):
        cs, exp = self._started(tmp_path)
        result = exp.step(_sample(position=0.0, velocity=0.0, t=0.0), elapsed_s=0.0)
        assert result.state == ExperimentState.RAMPING
        assert result.torque_command_nm == pytest.approx(0.1)

        result = exp.step(_sample(position=0.0, velocity=0.0, t=1.0), elapsed_s=1.0)
        assert result.state == ExperimentState.RAMPING
        assert result.torque_command_nm == pytest.approx(0.1 + 0.05 * 1.0)

    def test_ramping_to_lifting_freezes_torque_at_movement_onset(self, tmp_path):
        cs, exp = self._started(tmp_path)
        # velocity=0.06 turns/s at r0=0.035m -> ~0.0132 m/s, above the 0.01 m/s
        # threshold -- should trigger the RAMPING -> LIFTING transition.
        result = exp.step(_sample(position=0.0, velocity=0.06, t=2.0), elapsed_s=2.0)
        assert result.state == ExperimentState.LIFTING
        expected_torque = 0.1 + 0.05 * 2.0
        assert result.torque_command_nm == pytest.approx(expected_torque)

        # Subsequent LIFTING ticks command the SAME frozen torque, regardless
        # of elapsed time (spec §2.3: "flat, no further ramp").
        result = exp.step(_sample(position=0.0, velocity=0.02, t=5.0), elapsed_s=5.0)
        assert result.state == ExperimentState.LIFTING
        assert result.torque_command_nm == pytest.approx(expected_torque)

    def test_lifting_to_holding_at_deadband(self, tmp_path):
        cs, exp = self._started(tmp_path)
        exp.step(_sample(position=0.0, velocity=0.06, t=1.0), elapsed_s=1.0)
        assert exp.state == ExperimentState.LIFTING

        target_turns = _turns_for_length(cs, 1.0)  # target_position_m default
        result = exp.step(_sample(position=target_turns, velocity=0.0, t=2.0), elapsed_s=2.0)
        assert result.state == ExperimentState.HOLDING

    def test_holding_proportional_law_and_zero_floor_clamp(self, tmp_path):
        cs, exp = self._started(tmp_path, hold_gain=5.0, max_torque_nm=2.0)
        exp.step(_sample(position=0.0, velocity=0.06, t=1.0), elapsed_s=1.0)
        base_holding_torque = 0.1 + 0.05 * 1.0
        target_turns = _turns_for_length(cs, 1.0)
        exp.step(_sample(position=target_turns, velocity=0.0, t=2.0), elapsed_s=2.0)
        assert exp.state == ExperimentState.HOLDING

        # Sagged 0.1m below target -> positive error -> torque increases.
        below_turns = _turns_for_length(cs, 1.0 - 0.1)
        result = exp.step(_sample(position=below_turns, velocity=0.0, t=3.0), elapsed_s=3.0)
        assert result.state == ExperimentState.HOLDING
        expected = base_holding_torque + 5.0 * 0.1
        assert result.torque_command_nm == pytest.approx(expected, abs=1e-3)

        # Far above target -> large negative error -> clamped to the 0 floor,
        # never negative (spec §2.4's literal v1 clamp).
        above_turns = _turns_for_length(cs, 1.0 + 10.0)
        result = exp.step(_sample(position=above_turns, velocity=0.0, t=4.0), elapsed_s=4.0)
        assert result.torque_command_nm == 0.0

    def test_max_torque_breach_aborts(self, tmp_path):
        cs, exp = self._started(
            tmp_path,
            initial_torque_nm=0.1,
            torque_ramp_rate_nm_per_s=0.5,
            movement_threshold_m_per_s=100.0,  # never trip movement -- stay RAMPING
            max_torque_nm=0.2,
        )
        result = exp.step(_sample(position=0.0, velocity=0.0, t=0.3), elapsed_s=0.3)
        assert result.state == ExperimentState.ABORTED
        assert result.torque_command_nm == 0.0
        summary = exp.summary()
        assert summary["abort_reason"] is not None

    def test_max_duration_elapses_to_complete(self, tmp_path):
        cs, exp = self._started(tmp_path, max_duration_s=1.0)
        result = exp.step(_sample(position=0.0, velocity=0.0, t=1.0), elapsed_s=1.0)
        assert result.state == ExperimentState.COMPLETE
        assert result.torque_command_nm == 0.0
        summary = exp.summary()
        assert summary["complete_reason"] is not None

    def test_terminal_states_stay_terminal_and_return_zero_torque(self, tmp_path):
        cs, exp = self._started(tmp_path, max_duration_s=1.0)
        exp.step(_sample(position=0.0, velocity=0.0, t=1.0), elapsed_s=1.0)
        assert exp.state == ExperimentState.COMPLETE
        result = exp.step(_sample(position=0.0, velocity=0.5, t=2.0), elapsed_s=2.0)
        assert result.state == ExperimentState.COMPLETE
        assert result.torque_command_nm == 0.0

    def test_summary_tracks_peak_torque_and_timings(self, tmp_path):
        cs, exp = self._started(tmp_path)
        exp.step(_sample(position=0.0, velocity=0.0, t=0.0), elapsed_s=0.0)
        exp.step(_sample(position=0.0, velocity=0.06, t=1.0), elapsed_s=1.0)
        target_turns = _turns_for_length(cs, 1.0)
        exp.step(_sample(position=target_turns, velocity=0.0, t=2.0), elapsed_s=2.0)

        summary = exp.summary()
        assert summary["time_to_first_movement_s"] == pytest.approx(1.0)
        assert summary["time_to_target_s"] == pytest.approx(2.0)
        assert summary["peak_torque_nm"] == pytest.approx(0.1 + 0.05 * 1.0)
