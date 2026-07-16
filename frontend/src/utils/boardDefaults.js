// Maps config/board_constants.py's shape (fetched via GET /api/board-constants)
// to template-path config-wizard values.
//
// This module only knows the *structural* mapping — which board-constants key
// belongs at which property path. The actual numeric values always come from
// the backend fetch; they are never duplicated here, per the project's
// single-source-of-truth rule (config/board_constants.py).

/** Convert a fetched board-constants object into a template-path value map,
 * suitable for `presetsManager.expandValues(values, axis)`. */
export function boardConstantsToTemplateValues(bc) {
  if (!bc) return {}
  const raw = {
    'config.brake_resistance': bc.bus?.brake_resistance,
    'config.dc_bus_undervoltage_trip_level': bc.bus?.dc_bus_undervoltage_trip_level,
    'config.dc_bus_overvoltage_trip_level': bc.bus?.dc_bus_overvoltage_trip_level,
    'config.dc_max_positive_current': bc.bus?.dc_max_positive_current,
    'config.dc_max_negative_current': bc.bus?.dc_max_negative_current,
    'config.max_regen_current': bc.bus?.max_regen_current,

    'axis{n}.motor.config.motor_type': bc.motor?.motor_type,
    'axis{n}.motor.config.pole_pairs': bc.motor?.pole_pairs,
    'axis{n}.motor.config.current_lim': bc.motor?.current_lim,
    'axis{n}.motor.config.calibration_current': bc.motor?.calibration_current,
    'axis{n}.motor.config.current_control_bandwidth': bc.motor?.current_control_bandwidth,
    'axis{n}.motor.config.requested_current_range': bc.motor?.requested_current_range,
    'axis{n}.motor.config.resistance_calib_max_voltage': bc.motor?.resistance_calib_max_voltage,

    'axis{n}.encoder.config.mode': bc.encoder?.mode,
    'axis{n}.encoder.config.abs_spi_cs_gpio_pin': bc.encoder?.abs_spi_cs_gpio_pin,
    'axis{n}.encoder.config.cpr': bc.encoder?.cpr,
    'axis{n}.encoder.config.bandwidth': bc.encoder?.bandwidth,
    'axis{n}.encoder.config.calib_range': bc.encoder?.calib_range,

    'axis{n}.controller.config.control_mode': bc.controller?.control_mode,
    'axis{n}.controller.config.input_mode': bc.controller?.input_mode,
    'axis{n}.controller.config.vel_limit': bc.controller?.vel_limit,
    'axis{n}.controller.config.pos_gain': bc.controller?.pos_gain,
    'axis{n}.controller.config.vel_gain': bc.controller?.vel_gain,
    'axis{n}.controller.config.vel_integrator_gain': bc.controller?.vel_integrator_gain,

    // Only axis0's node ID — this wizard only ever operates on axis0. Axis1's
    // ghost-silencing node ID (63) is recorded in board_constants.py for
    // Phase 2B but isn't reachable through this single-axis wizard.
    'axis{n}.config.can_node_id': bc.axis?.axis0_can_node_id,
  }
  const out = {}
  for (const [path, value] of Object.entries(raw)) {
    if (value !== undefined && value !== null) out[path] = value
  }
  return out
}
