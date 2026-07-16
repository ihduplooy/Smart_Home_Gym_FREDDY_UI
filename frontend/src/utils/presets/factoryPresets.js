// Built-in factory presets. Values use template axis paths (`axis{n}...`) so they
// apply to whichever axis is selected. Mirrors common motor profiles.

export const FACTORY_PRESETS = [
  {
    format: 'odrive-gui-preset',
    version: 1,
    name: 'Smart Gym Cable — Hoverboard + AS5047P',
    factory: true,
    description:
      'This project\'s board: hoverboard hub motor (15 pole pairs) with an AS5047P ' +
      'SPI-absolute encoder (CS pin 7). Generated from config/odrive_config.py (Phase 1B).',
    values: {
      // Motor
      'axis{n}.motor.config.motor_type': 0, // MOTOR_TYPE_HIGH_CURRENT
      'axis{n}.motor.config.pole_pairs': 15,
      'axis{n}.motor.config.current_lim': 10.0,
      'axis{n}.motor.config.calibration_current': 5.0,
      'axis{n}.motor.config.current_control_bandwidth': 100,
      'axis{n}.motor.config.requested_current_range': 25.0,
      'axis{n}.motor.config.resistance_calib_max_voltage': 4.0,
      // Encoder — AS5047P, SPI absolute, CS pin 7
      'axis{n}.encoder.config.mode': 257, // ENCODER_MODE_SPI_ABS_AMS
      'axis{n}.encoder.config.abs_spi_cs_gpio_pin': 7,
      'axis{n}.encoder.config.cpr': 16384, // AS5047P is 14-bit -> 2^14
      'axis{n}.encoder.config.bandwidth': 3000,
      'axis{n}.encoder.config.calib_range': 10,
      // Controller
      'axis{n}.controller.config.control_mode': 3, // CONTROL_MODE_POSITION_CONTROL
      'axis{n}.controller.config.input_mode': 5, // INPUT_MODE_TRAP_TRAJ
      'axis{n}.controller.config.vel_limit': 2.0,
      'axis{n}.controller.config.pos_gain': 1.0,
      'axis{n}.controller.config.vel_gain': 0.02,
      'axis{n}.controller.config.vel_integrator_gain': 0.0,
      // CAN (this axis only — see docs/decisions.md for axis1's ghost-silencing ID)
      'axis{n}.config.can_node_id': 0,
      // Bus-level limits
      'config.brake_resistance': 2.0,
      'config.dc_bus_undervoltage_trip_level': 8.0,
      'config.dc_bus_overvoltage_trip_level': 25.0,
      'config.dc_max_positive_current': 15.0,
      'config.dc_max_negative_current': -3.0,
      'config.max_regen_current': 0,
    },
  },
  {
    format: 'odrive-gui-preset',
    version: 1,
    name: 'High Current — D6374 150KV',
    factory: true,
    description: 'ODrive D6374 150KV high-current motor with a 4000 CPR encoder.',
    values: {
      'axis{n}.motor.config.motor_type': 0,
      'axis{n}.motor.config.pole_pairs': 7,
      'axis{n}.motor.config.torque_constant': 0.0551, // 8.27 / 150
      'axis{n}.motor.config.current_lim': 40,
      'axis{n}.motor.config.calibration_current': 10,
      'axis{n}.encoder.config.mode': 0,
      'axis{n}.encoder.config.cpr': 4000,
      'axis{n}.controller.config.control_mode': 2,
      'axis{n}.controller.config.vel_limit': 10,
    },
  },
  {
    format: 'odrive-gui-preset',
    version: 1,
    name: 'Gimbal — GBM2804 100KV',
    factory: true,
    description: 'Low-current gimbal motor. Use gimbal motor mode and a low current limit.',
    values: {
      'axis{n}.motor.config.motor_type': 2,
      'axis{n}.motor.config.pole_pairs': 7,
      'axis{n}.motor.config.torque_constant': 0.0827, // 8.27 / 100
      'axis{n}.motor.config.current_lim': 5,
      'axis{n}.motor.config.calibration_current': 2,
      'axis{n}.encoder.config.mode': 0,
      'axis{n}.encoder.config.cpr': 4000,
      'axis{n}.controller.config.control_mode': 2,
      'axis{n}.controller.config.vel_limit': 20,
    },
  },
  {
    format: 'odrive-gui-preset',
    version: 1,
    name: 'Hoverboard — 6.5" Wheel',
    factory: true,
    description: 'Hoverboard hub motor with Hall sensors (15 pole pairs, CPR = pole_pairs × 6).',
    values: {
      'axis{n}.motor.config.motor_type': 0,
      'axis{n}.motor.config.pole_pairs': 15,
      'axis{n}.motor.config.torque_constant': 0.517, // 8.27 / 16
      'axis{n}.motor.config.current_lim': 30,
      'axis{n}.motor.config.calibration_current': 10,
      'axis{n}.encoder.config.mode': 1, // Hall
      'axis{n}.encoder.config.cpr': 90, // 15 * 6
      'axis{n}.controller.config.control_mode': 2,
      'axis{n}.controller.config.vel_limit': 2,
    },
  },
]
