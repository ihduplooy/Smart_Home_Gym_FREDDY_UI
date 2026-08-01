// Path constants for the Inspector tab's fixed axis0 telemetry graphs
// (AxisTelemetryCharts.jsx). This board only ever drives axis0 (ACTIVE_AXIS
// in config/board_constants.py) -- axis1 is a ghost node -- so these are
// hardcoded rather than keyed off the selected-axis UI state the way
// useDeviceTelemetry.js's statusPaths() is.
//
// Paths corroborated against frontend/src/utils/odriveApiReference05x.json
// (this project's firmware v0.5.1 reference, see config/board_constants.py's
// own firmware-pin comment) as of the graphs being added -- NOT live-verified
// against this board's actual dir(odrv0) output. controller.pos_setpoint /
// vel_setpoint in particular (the live trajectory-tracking setpoint, distinct
// from controller.input_pos/input_vel which is the raw commanded target) has
// no live dir() cross-check anywhere in this codebase yet, same unconfirmed
// status as ENABLE_TORQUE_MODE_VEL_LIMIT in board_constants.py -- confirm
// against a live board before trusting the setpoint overlay lines.
export const AXIS = 0

export const FIXED_AXIS_TELEMETRY_PATHS = Object.freeze({
  posEstimate: `axis${AXIS}.encoder.pos_estimate`,
  posSetpoint: `axis${AXIS}.controller.pos_setpoint`,
  velEstimate: `axis${AXIS}.encoder.vel_estimate`,
  velSetpoint: `axis${AXIS}.controller.vel_setpoint`,
  iqMeasured: `axis${AXIS}.motor.current_control.Iq_measured`,
  idMeasured: `axis${AXIS}.motor.current_control.Id_measured`,
  ibus: 'ibus',
  vbusVoltage: 'vbus_voltage',
})

// Flat list, for subscribing (telemetrySlice.addProperty) and for filtering
// these out of the free-form, user-picked property list in LiveCharts.jsx so
// each one doesn't also render a second, redundant generic card there.
export const FIXED_AXIS_TELEMETRY_PATH_LIST = Object.freeze(Object.values(FIXED_AXIS_TELEMETRY_PATHS))
