// Friendly display names for ODrive enum members.
//
// The data-driven registry already knows each enum's members and integer values
// (from the API reference). This module only adds human-friendly labels on top;
// anything without an explicit label falls back to title-casing the raw name.

import { getRegistry, enumTypeOf } from './odriveRegistry'

const FRIENDLY = {
  'ODrive.Motor.MotorType': {
    HIGH_CURRENT: 'High Current',
    GIMBAL: 'Gimbal',
    ACIM: 'ACIM (Induction)',
  },
  'ODrive.Encoder.Mode': {
    INCREMENTAL: 'Incremental (ABZ)',
    HALL: 'Hall Effect',
    SINCOS: 'SinCos',
    SPI_ABS_CUI: 'SPI Absolute (CUI)',
    SPI_ABS_AMS: 'SPI Absolute (AMS)',
    SPI_ABS_AEAT: 'SPI Absolute (AEAT)',
    SPI_ABS_RLS: 'SPI Absolute (RLS)',
    SPI_ABS_MA732: 'SPI Absolute (MA732)',
  },
  'ODrive.Controller.ControlMode': {
    VOLTAGE_CONTROL: 'Voltage Control',
    TORQUE_CONTROL: 'Torque Control',
    VELOCITY_CONTROL: 'Velocity Control',
    POSITION_CONTROL: 'Position Control',
  },
  'ODrive.Controller.InputMode': {
    INACTIVE: 'Inactive',
    PASSTHROUGH: 'Passthrough',
    VEL_RAMP: 'Velocity Ramp',
    POS_FILTER: 'Position Filter',
    MIX_CHANNELS: 'Mix Channels',
    TRAP_TRAJ: 'Trapezoidal Trajectory',
    TORQUE_RAMP: 'Torque Ramp',
    MIRROR: 'Mirror',
    TUNING: 'Tuning',
  },
  'ODrive.Axis.AxisState': {
    UNDEFINED: 'Undefined',
    IDLE: 'Idle',
    STARTUP_SEQUENCE: 'Startup Sequence',
    FULL_CALIBRATION_SEQUENCE: 'Full Calibration',
    MOTOR_CALIBRATION: 'Motor Calibration',
    ENCODER_INDEX_SEARCH: 'Encoder Index Search',
    ENCODER_OFFSET_CALIBRATION: 'Encoder Offset Calibration',
    CLOSED_LOOP_CONTROL: 'Closed Loop Control',
    LOCKIN_SPIN: 'Lock-in Spin',
    ENCODER_DIR_FIND: 'Encoder Direction Find',
    HOMING: 'Homing',
    ENCODER_HALL_POLARITY_CALIBRATION: 'Hall Polarity Calibration',
    ENCODER_HALL_PHASE_CALIBRATION: 'Hall Phase Calibration',
  },
}

// One-line explanation of what each enum member actually does, so a field's
// tooltip can tell you not just "what is this setting" but "which option do
// I want" — surfaced next to each choice in ParameterField's tooltip.
const OPTION_DESCRIPTIONS = {
  'ODrive.Motor.MotorType': {
    HIGH_CURRENT: 'Standard closed-loop current control. Use for almost all BLDC/PMSM motors, including this project’s hub motor.',
    GIMBAL: 'Simplified voltage-only control for low-current gimbal motors. Not suitable for a high-current motor like this one.',
    ACIM: 'For AC induction motors (no permanent magnets). Not applicable here.',
  },
  'ODrive.Encoder.Mode': {
    INCREMENTAL: 'Quadrature ABZ encoder — relative position only, needs an index/offset calibration.',
    HALL: '3 Hall-effect sensors built into the motor — coarse resolution, no separate encoder needed.',
    SINCOS: 'Analog sine/cosine encoder output.',
    SPI_ABS_CUI: 'Absolute encoder over SPI, CUI AMT23-series protocol.',
    SPI_ABS_AMS: 'Absolute encoder over SPI, AMS AS5047/AS5048-series protocol — this board’s onboard encoder.',
    SPI_ABS_AEAT: 'Absolute encoder over SPI, Broadcom/Avago AEAT protocol.',
    SPI_ABS_RLS: 'Absolute encoder over SPI, RLS AksIM protocol.',
    SPI_ABS_MA732: 'Absolute encoder over SPI, MPS MA732 protocol.',
  },
  'ODrive.Controller.ControlMode': {
    VOLTAGE_CONTROL: 'Directly commands motor voltage, open loop. Rarely used.',
    TORQUE_CONTROL: 'Regulates motor torque (via current). Use for force/resistance-style control.',
    VELOCITY_CONTROL: 'Regulates shaft speed. Use for constant-speed testing/operation.',
    POSITION_CONTROL: 'Regulates shaft position/angle. Use for point-to-point or trajectory moves.',
  },
  'ODrive.Controller.InputMode': {
    INACTIVE: 'Ignores input entirely — controller output stays at zero.',
    PASSTHROUGH: 'Uses the input value immediately, with no shaping. Pairs with Velocity or Torque control for direct, instant commands.',
    VEL_RAMP: 'Smoothly ramps the velocity target at a fixed acceleration. Pairs with Velocity control.',
    POS_FILTER: 'Low-pass filters the position target for smooth position moves. Pairs with Position control.',
    MIX_CHANNELS: 'Blends multiple analog/PWM input channels. Rarely used.',
    TRAP_TRAJ: 'Plans a trapezoidal (accel/cruise/decel) position move. Pairs with Position control only — do not use with Velocity or Torque control.',
    TORQUE_RAMP: 'Smoothly ramps the torque target at a fixed rate. Pairs with Torque control.',
    MIRROR: 'Mirrors another axis’s position — for synchronized dual-axis setups.',
    TUNING: 'Special mode used only during ODrive’s live tuning/step-response testing.',
  },
}

/** One-line explanation of a specific enum member, or '' if none is written yet. */
export function enumOptionDescription(enumTypeName, memberName) {
  return OPTION_DESCRIPTIONS[enumTypeName]?.[memberName] || ''
}

const titleCase = (name) =>
  name
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')

// Axis-state value -> friendly name, usable without the registry/firmware line.
const AXIS_STATE_NAMES = {
  0: 'Undefined',
  1: 'Idle',
  2: 'Startup Sequence',
  3: 'Full Calibration',
  4: 'Motor Calibration',
  5: 'Sensorless Control',
  6: 'Encoder Index Search',
  7: 'Encoder Offset Calibration',
  8: 'Closed Loop Control',
  9: 'Lock-in Spin',
  10: 'Encoder Direction Find',
  11: 'Homing',
  12: 'Hall Polarity Calibration',
  13: 'Hall Phase Calibration',
}

/** Friendly name for an axis-state integer. */
export function getAxisStateName(state) {
  return AXIS_STATE_NAMES[Number(state)] || `State ${state}`
}

// One-line explanation of what the axis is actually doing in each state, for
// the sidebar's axis-state readout (a name like "Homing" alone doesn't say
// what that means in practice).
const AXIS_STATE_DESCRIPTIONS = {
  0: 'State not yet reported by the device.',
  1: 'Motor unpowered — safe to handle, no control loop running.',
  2: 'Running the configured startup actions on power-up.',
  3: 'Running the combined motor + encoder calibration sequence.',
  4: 'Measuring motor phase resistance and inductance.',
  5: 'Closed-loop control without an encoder, using a sensorless position estimate.',
  6: "Rotating to find the encoder's index pulse.",
  7: "Measuring the encoder's offset relative to the motor's electrical angle.",
  8: 'Motor is actively powered and following commands.',
  9: 'Forcing the motor to spin open-loop at a fixed rate (used during calibration).',
  10: 'Determining which way the encoder counts relative to motor rotation.',
  11: 'Driving to an endstop to establish a reference position.',
  12: 'Determining Hall sensor polarity.',
  13: 'Measuring Hall sensor electrical phase offset.',
}

/** One-line explanation of what an axis-state integer means in practice. */
export function getAxisStateDescription(state) {
  return AXIS_STATE_DESCRIPTIONS[Number(state)] || 'Unrecognized state.'
}

/** Friendly label for a raw enum member name within an enum type. */
export function friendlyEnumLabel(enumTypeName, memberName) {
  return FRIENDLY[enumTypeName]?.[memberName] || titleCase(memberName)
}

/**
 * Build select options for an enum property: [{ value:number, label:string }].
 * `enumTypeName` may be given explicitly or derived from the property meta.
 * Returns [] when the enum is unknown.
 */
export function enumSelectOptions(fwLine, enumTypeName, meta) {
  const typeName = enumTypeName || (meta && enumTypeOf(meta))
  if (!typeName) return []
  const reg = getRegistry(fwLine)
  const en = reg.enums[typeName]
  if (!en?.values) return []
  return Object.entries(en.values).map(([name, info]) => ({
    value: typeof info?.value === 'number' ? info.value : Number(info?.value ?? 0),
    label: friendlyEnumLabel(typeName, name),
    description: enumOptionDescription(typeName, name),
  }))
}
