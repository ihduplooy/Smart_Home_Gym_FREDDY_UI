"""core/hardware/anticogging.py tests -- fake odrv/axis object tree, same
"fake the hardware surface directly" style as RecordingHardware elsewhere,
since this module deliberately isn't a HardwareInterface implementation.
"""

import fibre.protocol
import pytest

from core.hardware.anticogging import AnticoggingCalibration, AnticoggingState


class FakeAnticoggingConfig:
    def __init__(self):
        self.calib_pos_threshold = 0.0
        self.calib_vel_threshold = 0.0
        self.calib_anticogging = False
        self.pre_calibrated = False
        self.anticogging_enabled = False


class FakeControllerConfig:
    def __init__(self):
        self.pos_gain = 6.0
        self.vel_integrator_gain = 0.1
        self.control_mode = 0
        self.input_mode = 0
        self.anticogging = FakeAnticoggingConfig()


class FakeController:
    def __init__(self):
        self.config = FakeControllerConfig()
        self.start_anticogging_calls = 0

    def start_anticogging_calibration(self):
        self.start_anticogging_calls += 1
        self.config.anticogging.calib_anticogging = True


class FakeMotor:
    def __init__(self, is_calibrated=True):
        self.is_calibrated = is_calibrated


class FakeEncoder:
    def __init__(self, is_ready=True):
        self.is_ready = is_ready


class FakeAxis:
    def __init__(self, is_calibrated=True, is_ready=True):
        self.motor = FakeMotor(is_calibrated)
        self.encoder = FakeEncoder(is_ready)
        self.controller = FakeController()
        self.requested_state = None


class FakeOdrv:
    def __init__(self, is_calibrated=True, is_ready=True):
        self.axis0 = FakeAxis(is_calibrated, is_ready)
        self.save_configuration_calls = 0
        self.save_configuration_raises = None  # exception instance, or None

    def save_configuration(self):
        self.save_configuration_calls += 1
        if self.save_configuration_raises is not None:
            raise self.save_configuration_raises


class TestStart:
    def test_rejects_when_motor_not_calibrated(self):
        odrv = FakeOdrv(is_calibrated=False)
        calib = AnticoggingCalibration()
        with pytest.raises(RuntimeError):
            calib.start(odrv)

    def test_rejects_when_encoder_not_ready(self):
        odrv = FakeOdrv(is_ready=False)
        calib = AnticoggingCalibration()
        with pytest.raises(RuntimeError):
            calib.start(odrv)

    def test_rejects_when_already_running(self):
        odrv = FakeOdrv()
        calib = AnticoggingCalibration()
        calib.start(odrv)
        with pytest.raises(RuntimeError):
            calib.start(odrv)

    @pytest.mark.parametrize(
        "field,value",
        [
            ("pos_gain_multiplier", 0.0),
            ("vel_integrator_gain_multiplier", -1.0),
            ("calib_pos_threshold", 0.0),
            ("calib_vel_threshold", -0.5),
        ],
    )
    def test_rejects_invalid_numeric_args(self, field, value):
        odrv = FakeOdrv()
        calib = AnticoggingCalibration()
        with pytest.raises(ValueError):
            calib.start(odrv, **{field: value})

    def test_start_raises_gains_by_multiplier_and_triggers_rpc(self):
        odrv = FakeOdrv()
        odrv.axis0.controller.config.pos_gain = 6.0
        odrv.axis0.controller.config.vel_integrator_gain = 0.1
        calib = AnticoggingCalibration()

        result = calib.start(odrv, pos_gain_multiplier=6.0, vel_integrator_gain_multiplier=8.0)

        assert result["state"] == "running"
        assert odrv.axis0.controller.config.pos_gain == pytest.approx(36.0)
        assert odrv.axis0.controller.config.vel_integrator_gain == pytest.approx(0.8)
        assert odrv.axis0.controller.start_anticogging_calls == 1
        assert odrv.axis0.requested_state is not None  # AXIS_STATE_CLOSED_LOOP_CONTROL requested

    def test_start_uses_board_constants_defaults_when_omitted(self):
        odrv = FakeOdrv()
        odrv.axis0.controller.config.pos_gain = 6.0
        odrv.axis0.controller.config.vel_integrator_gain = 0.1
        calib = AnticoggingCalibration()

        calib.start(odrv)

        assert odrv.axis0.controller.config.pos_gain == pytest.approx(6.0 * 6.0)
        assert odrv.axis0.controller.config.anticogging.calib_pos_threshold == pytest.approx(1.0)


class TestPollAndFinish:
    def test_poll_while_still_calibrating_is_a_no_op(self):
        odrv = FakeOdrv()
        calib = AnticoggingCalibration()
        calib.start(odrv)
        odrv.axis0.controller.config.anticogging.calib_anticogging = True

        result = calib.poll(odrv)
        assert result["state"] == "running"
        assert odrv.save_configuration_calls == 0

    def test_poll_on_completion_restores_gains_and_saves(self):
        odrv = FakeOdrv()
        odrv.axis0.controller.config.pos_gain = 6.0
        odrv.axis0.controller.config.vel_integrator_gain = 0.1
        calib = AnticoggingCalibration()
        calib.start(odrv, pos_gain_multiplier=6.0, vel_integrator_gain_multiplier=6.0)

        # Firmware reports calibration finished.
        odrv.axis0.controller.config.anticogging.calib_anticogging = False
        result = calib.poll(odrv)

        assert result["state"] == "done"
        assert odrv.axis0.controller.config.pos_gain == pytest.approx(6.0)
        assert odrv.axis0.controller.config.vel_integrator_gain == pytest.approx(0.1)
        assert odrv.axis0.controller.config.anticogging.pre_calibrated is True
        assert odrv.save_configuration_calls == 1

    def test_channel_broken_exception_on_save_is_treated_as_success(self):
        odrv = FakeOdrv()
        odrv.save_configuration_raises = fibre.protocol.ChannelBrokenException()
        calib = AnticoggingCalibration()
        calib.start(odrv)
        odrv.axis0.controller.config.anticogging.calib_anticogging = False

        result = calib.poll(odrv)
        assert result["state"] == "done"

    def test_other_exception_on_save_marks_failed(self):
        odrv = FakeOdrv()
        odrv.save_configuration_raises = RuntimeError("usb went sideways")
        calib = AnticoggingCalibration()
        calib.start(odrv)
        odrv.axis0.controller.config.anticogging.calib_anticogging = False

        result = calib.poll(odrv)
        assert result["state"] == "failed"
        assert "usb went sideways" in result["error_message"]

    def test_poll_when_idle_is_a_no_op(self):
        odrv = FakeOdrv()
        calib = AnticoggingCalibration()
        result = calib.poll(odrv)
        assert result["state"] == "idle"


class TestAbort:
    def test_abort_restores_gains_and_does_not_save(self):
        odrv = FakeOdrv()
        odrv.axis0.controller.config.pos_gain = 6.0
        odrv.axis0.controller.config.vel_integrator_gain = 0.1
        calib = AnticoggingCalibration()
        calib.start(odrv, pos_gain_multiplier=6.0, vel_integrator_gain_multiplier=6.0)

        result = calib.abort(odrv)

        assert result["state"] == "aborted"
        assert odrv.axis0.controller.config.pos_gain == pytest.approx(6.0)
        assert odrv.axis0.controller.config.vel_integrator_gain == pytest.approx(0.1)
        assert odrv.save_configuration_calls == 0
        assert odrv.axis0.controller.config.anticogging.pre_calibrated is False

    def test_abort_when_not_running_is_a_no_op(self):
        odrv = FakeOdrv()
        calib = AnticoggingCalibration()
        result = calib.abort(odrv)
        assert result["state"] == "idle"

    def test_can_restart_after_abort(self):
        odrv = FakeOdrv()
        calib = AnticoggingCalibration()
        calib.start(odrv)
        calib.abort(odrv)
        result = calib.start(odrv)
        assert result["state"] == "running"
