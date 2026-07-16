"""
Single source of truth for this project's board/motor/encoder constants.

Every value here is taken verbatim from config/odrive_config.py (the Phase 1B
ODrive setup script). This module is plain data with no dependency on the
`odrive` package or any hardware — it's imported by the backend (to pre-load the
config wizard and serve the /api/board-constants route) and, from Session 2
onward, by core/. Never duplicate these values into frontend code; the frontend
fetches them via that one backend route.

Board: MKS ODrive Mini V1.0 (ODrive v3.6 clone, also sold as "MKS XDrive Mini")
"""

# --------------------------------------------------------------------------
# Firmware
# --------------------------------------------------------------------------
# v0.5.1 ONLY — do not upgrade. v0.5.6 breaks motor activation on this board.
EXPECTED_FW_VERSION_MAJOR = 0
EXPECTED_FW_VERSION_MINOR = 5
EXPECTED_FW_VERSION_REVISION = 1
EXPECTED_FW_VERSION_STRING = "0.5.1"

# Must match firmware; see backend/requirements.txt.
ODRIVE_PYTHON_PACKAGE_VERSION = "0.5.1.post0"

# --------------------------------------------------------------------------
# Motor — hoverboard BLDC hub motor
# --------------------------------------------------------------------------
MOTOR_POLE_PAIRS = 15
MOTOR_TYPE_HIGH_CURRENT = 0  # odrive.enums.MOTOR_TYPE_HIGH_CURRENT

# Hoverboard hub motors have notably higher phase resistance/inductance than
# typical hobby aircraft/actuator motors. These values are conservative starting
# points confirmed against a reference config written specifically for hoverboard
# motors on ODrive v3.6 (see config/odrive_config.py for full annotations).
MOTOR_CURRENT_LIM = 10.0  # A, conservative first pass
MOTOR_REQUESTED_CURRENT_RANGE = 25.0
MOTOR_CALIBRATION_CURRENT = 5.0
MOTOR_RESISTANCE_CALIB_MAX_VOLTAGE = 4.0
MOTOR_CURRENT_CONTROL_BANDWIDTH = 100  # reduced from ODrive's default for stability
                                       # given this motor's higher inductance

# --------------------------------------------------------------------------
# Encoder — onboard AS5047P magnetic encoder (SPI, absolute)
# --------------------------------------------------------------------------
ENCODER_MODE_SPI_ABS_AMS = 257  # odrive.enums.ENCODER_MODE_SPI_ABS_AMS
# Specific to this MKS clone board (confirmed via community reports) — differs
# from genuine ODrive Pro/S1 pin numbers.
ENCODER_ABS_SPI_CS_GPIO_PIN = 7
ENCODER_CPR = 16384  # AS5047P is 14-bit -> 2^14
ENCODER_BANDWIDTH = 3000
ENCODER_CALIB_RANGE = 10

# --------------------------------------------------------------------------
# Controller — conservative starting points, not tuned values
# --------------------------------------------------------------------------
CONTROL_MODE_POSITION_CONTROL = 3  # odrive.enums.CONTROL_MODE_POSITION_CONTROL
INPUT_MODE_TRAP_TRAJ = 5  # odrive.enums.INPUT_MODE_TRAP_TRAJ
CONTROLLER_VEL_LIMIT = 2.0  # turns/s
CONTROLLER_POS_GAIN = 1.0
CONTROLLER_VEL_GAIN = 0.02
CONTROLLER_VEL_INTEGRATOR_GAIN = 0.0

TRAP_TRAJ_VEL_LIMIT = 1.0  # turns/s
TRAP_TRAJ_ACCEL_LIMIT = 1.0  # turns/s^2
TRAP_TRAJ_DECEL_LIMIT = 1.0  # turns/s^2

# TODO(2A): enable_torque_mode_vel_limit — ODrive's torque mode velocity limiter
# may fight a profile layer (Session 3's core/profiles/) doing its own
# velocity-dependent control. Decision waits for real hardware in Phase 2A.

# --------------------------------------------------------------------------
# Axis — axis0 only; axis1 is a ghost node
# --------------------------------------------------------------------------
# This board only ever drives axis0. Axis1's CAN node ID must be set to 63 to
# silence it (a Phase 2B concern — CAN HAT wiring — recorded here per plan).
ACTIVE_AXIS = 0
AXIS0_CAN_NODE_ID = 0
AXIS1_CAN_NODE_ID = 63
CAN_BAUD_RATE = 500000

# --------------------------------------------------------------------------
# Bus-level limits
# --------------------------------------------------------------------------
BRAKE_RESISTANCE = 2.0  # ohm
DC_BUS_UNDERVOLTAGE_TRIP_LEVEL = 8.0
DC_BUS_OVERVOLTAGE_TRIP_LEVEL = 25.0  # capped for bench PSU testing; raise before
                                      # battery phase (~42V)
DC_MAX_POSITIVE_CURRENT = 15.0
DC_MAX_NEGATIVE_CURRENT = -3.0  # conservative: brake resistor wattage tbc
MAX_REGEN_CURRENT = 0  # conservative: brake resistor wattage tbc


def check_firmware(fw_major, fw_minor, fw_revision):
    """Return a human-readable warning if a connected board's firmware doesn't
    match what this project targets, else None. Callers should warn, never
    raise — per spec, a firmware mismatch is not a reason to refuse a
    connection, only to flag it."""
    if (fw_major, fw_minor, fw_revision) == (
        EXPECTED_FW_VERSION_MAJOR,
        EXPECTED_FW_VERSION_MINOR,
        EXPECTED_FW_VERSION_REVISION,
    ):
        return None
    return (
        f"Connected board reports firmware {fw_major}.{fw_minor}.{fw_revision}, "
        f"but this project targets v{EXPECTED_FW_VERSION_STRING} only "
        f"(v0.5.6 breaks motor activation on this board's clone — do not upgrade)."
    )


def as_dict():
    """JSON-serializable view of these constants, for the /api/board-constants route."""
    return {
        "firmware": {
            "expected_version": EXPECTED_FW_VERSION_STRING,
            "expected_major": EXPECTED_FW_VERSION_MAJOR,
            "expected_minor": EXPECTED_FW_VERSION_MINOR,
            "expected_revision": EXPECTED_FW_VERSION_REVISION,
            "odrive_python_package_version": ODRIVE_PYTHON_PACKAGE_VERSION,
        },
        "motor": {
            "pole_pairs": MOTOR_POLE_PAIRS,
            "motor_type": MOTOR_TYPE_HIGH_CURRENT,
            "current_lim": MOTOR_CURRENT_LIM,
            "requested_current_range": MOTOR_REQUESTED_CURRENT_RANGE,
            "calibration_current": MOTOR_CALIBRATION_CURRENT,
            "resistance_calib_max_voltage": MOTOR_RESISTANCE_CALIB_MAX_VOLTAGE,
            "current_control_bandwidth": MOTOR_CURRENT_CONTROL_BANDWIDTH,
        },
        "encoder": {
            "mode": ENCODER_MODE_SPI_ABS_AMS,
            "abs_spi_cs_gpio_pin": ENCODER_ABS_SPI_CS_GPIO_PIN,
            "cpr": ENCODER_CPR,
            "bandwidth": ENCODER_BANDWIDTH,
            "calib_range": ENCODER_CALIB_RANGE,
        },
        "controller": {
            "control_mode": CONTROL_MODE_POSITION_CONTROL,
            "input_mode": INPUT_MODE_TRAP_TRAJ,
            "vel_limit": CONTROLLER_VEL_LIMIT,
            "pos_gain": CONTROLLER_POS_GAIN,
            "vel_gain": CONTROLLER_VEL_GAIN,
            "vel_integrator_gain": CONTROLLER_VEL_INTEGRATOR_GAIN,
            "trap_traj_vel_limit": TRAP_TRAJ_VEL_LIMIT,
            "trap_traj_accel_limit": TRAP_TRAJ_ACCEL_LIMIT,
            "trap_traj_decel_limit": TRAP_TRAJ_DECEL_LIMIT,
        },
        "axis": {
            "active_axis": ACTIVE_AXIS,
            "axis0_can_node_id": AXIS0_CAN_NODE_ID,
            "axis1_can_node_id": AXIS1_CAN_NODE_ID,
            "can_baud_rate": CAN_BAUD_RATE,
        },
        "bus": {
            "brake_resistance": BRAKE_RESISTANCE,
            "dc_bus_undervoltage_trip_level": DC_BUS_UNDERVOLTAGE_TRIP_LEVEL,
            "dc_bus_overvoltage_trip_level": DC_BUS_OVERVOLTAGE_TRIP_LEVEL,
            "dc_max_positive_current": DC_MAX_POSITIVE_CURRENT,
            "dc_max_negative_current": DC_MAX_NEGATIVE_CURRENT,
            "max_regen_current": MAX_REGEN_CURRENT,
        },
    }
