// Typed client for the Exercise tab's backend routes
// (backend/app/exercise_routes.py). Layer A: cable-attached positioning &
// safety (exercise_tab_build_spec_layerA.md). REST polling only, matching
// the Control/Profiles precedent — no websocket.
//
//   GET  /api/exercise/status
//   POST /api/exercise/start                  {} -- arms, zero motion
//   POST /api/exercise/home
//   POST /api/exercise/go_home                -- same reel-in-to-current-threshold as Home, but never re-latches home
//   POST /api/exercise/abort_homing
//   POST /api/exercise/start_max_calibration
//   POST /api/exercise/confirm_max
//   POST /api/exercise/cancel_max_calibration
//   POST /api/exercise/move                   { target_length_m, move_velocity_turns_s?, accel_decel_turns_s2? }
//   POST /api/exercise/stop
//   POST /api/exercise/reset_position          -- idle-gated, confirm in the UI first
//   POST /api/exercise/calibrate_k             { measured_length_m }
//   POST /api/exercise/update_homing_settings  { current_threshold_a?, velocity_turns_s?, current_limit_a? }
//   POST /api/exercise/update_spool_radius     { r0 }
//   POST /api/exercise/update_spool_k          { k } -- direct entry, still bounds-checked
//   POST /api/exercise/update_calib_hold_force { force_n }
//   POST /api/exercise/update_force_settings   { letgo_velocity_turns_s?, letgo_debounce_samples?,
//                                                 hold_duration_s?, force_ramp_in_s?, force_ramp_out_s?,
//                                                 isokinetic_governor_gain?, isokinetic_velocity_filter_alpha?,
//                                                 max_extension_force_taper_m?, position_guard_warning_turns?,
//                                                 position_guard_hard_turns? }
//
// Train tab calibration overhaul -- manual max-extension entry and the
// experimental multi-point spool-growth calibration (see status.cable
// .spool_model for the currently-active model/equations/segments):
//   POST /api/exercise/set_max_extension_manual        { length_m }
//   POST /api/exercise/start_spool_growth_calibration
//   POST /api/exercise/record_growth_point             { length_m }
//   POST /api/exercise/remove_growth_point              { index }
//   POST /api/exercise/clear_growth_points
//   POST /api/exercise/cancel_spool_growth_calibration
//   POST /api/exercise/save_growth_calibration
//   POST /api/exercise/clear_growth_calibration
//
// Torque/force calibration (items 6/7 -- see status.cable.torque_model for
// the currently-fitted scale/offset/equation/points):
//   POST /api/exercise/record_torque_calibration_point { known_weight_kg }
//   POST /api/exercise/clear_torque_calibration
//
// Force Feedback (formerly a separate "force" session, merged 24 July 2026
// into this same Exercise session -- see backend/app/force_routes.py):
//   POST /api/force/engage          { mode, concentric_force_n, eccentric_force_n, velocity_target_turns_s?,
//                                      start_length_m?, end_length_m? }
//   POST /api/force/update_params   same shape as engage
//   POST /api/force/disengage
//   POST /api/force/resume

async function getJson(url, options) {
  const res = await fetch(url, options)
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      detail = body?.error || JSON.stringify(body)
    } catch {
      detail = await res.text().catch(() => '')
    }
    throw new Error(`${options?.method || 'GET'} ${url} failed (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return res.json()
}

function postJson(url, body) {
  return getJson(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
}

export function getExerciseStatus() {
  return getJson('/api/exercise/status')
}

export function startExerciseSession() {
  return postJson('/api/exercise/start')
}

export function homeExercise() {
  return postJson('/api/exercise/home')
}

export function goHomeExercise() {
  return postJson('/api/exercise/go_home')
}

export function abortHoming() {
  return postJson('/api/exercise/abort_homing')
}

export function startMaxCalibration() {
  return postJson('/api/exercise/start_max_calibration')
}

export function confirmMax() {
  return postJson('/api/exercise/confirm_max')
}

export function cancelMaxCalibration() {
  return postJson('/api/exercise/cancel_max_calibration')
}

export function moveCable(targetLengthM, moveVelocityTurnsS, accelDecelTurnsS2) {
  const body = { target_length_m: targetLengthM }
  if (moveVelocityTurnsS != null) body.move_velocity_turns_s = moveVelocityTurnsS
  if (accelDecelTurnsS2 != null) body.accel_decel_turns_s2 = accelDecelTurnsS2
  return postJson('/api/exercise/move', body)
}

export function stopExercise() {
  return postJson('/api/exercise/stop')
}

export function resetExercisePosition() {
  return postJson('/api/exercise/reset_position')
}

export function calibrateSpoolK(measuredLengthM) {
  return postJson('/api/exercise/calibrate_k', { measured_length_m: measuredLengthM })
}

export function updateHomingSettings({ currentThresholdA, velocityTurnsS, currentLimitA } = {}) {
  const body = {}
  if (currentThresholdA != null) body.current_threshold_a = currentThresholdA
  if (velocityTurnsS != null) body.velocity_turns_s = velocityTurnsS
  if (currentLimitA != null) body.current_limit_a = currentLimitA
  return postJson('/api/exercise/update_homing_settings', body)
}

export function updateSpoolRadius(r0) {
  return postJson('/api/exercise/update_spool_radius', { r0 })
}

export function updateSpoolK(k) {
  return postJson('/api/exercise/update_spool_k', { k })
}

export function updateCalibHoldForce(forceN) {
  return postJson('/api/exercise/update_calib_hold_force', { force_n: forceN })
}

export function setMaxExtensionManual(lengthM) {
  return postJson('/api/exercise/set_max_extension_manual', { length_m: lengthM })
}

export function startSpoolGrowthCalibration() {
  return postJson('/api/exercise/start_spool_growth_calibration')
}

export function recordGrowthPoint(lengthM) {
  return postJson('/api/exercise/record_growth_point', { length_m: lengthM })
}

export function removeGrowthPoint(index) {
  return postJson('/api/exercise/remove_growth_point', { index })
}

export function clearGrowthPoints() {
  return postJson('/api/exercise/clear_growth_points')
}

export function cancelSpoolGrowthCalibration() {
  return postJson('/api/exercise/cancel_spool_growth_calibration')
}

export function saveGrowthCalibration() {
  return postJson('/api/exercise/save_growth_calibration')
}

export function clearGrowthCalibration() {
  return postJson('/api/exercise/clear_growth_calibration')
}

export function recordTorqueCalibrationPoint(knownWeightKg) {
  return postJson('/api/exercise/record_torque_calibration_point', { known_weight_kg: knownWeightKg })
}

export function clearTorqueCalibration() {
  return postJson('/api/exercise/clear_torque_calibration')
}

export function updateForceSettings({
  letgoVelocityTurnsS,
  letgoDebounceSamples,
  holdDurationS,
  forceRampInS,
  forceRampOutS,
  isokineticGovernorGain,
  isokineticVelocityFilterAlpha,
  maxExtensionForceTaperM,
  positionGuardWarningTurns,
  positionGuardHardTurns,
} = {}) {
  const body = {}
  if (letgoVelocityTurnsS != null) body.letgo_velocity_turns_s = letgoVelocityTurnsS
  if (letgoDebounceSamples != null) body.letgo_debounce_samples = letgoDebounceSamples
  if (holdDurationS != null) body.hold_duration_s = holdDurationS
  if (forceRampInS != null) body.force_ramp_in_s = forceRampInS
  if (forceRampOutS != null) body.force_ramp_out_s = forceRampOutS
  if (isokineticGovernorGain != null) body.isokinetic_governor_gain = isokineticGovernorGain
  if (isokineticVelocityFilterAlpha != null) body.isokinetic_velocity_filter_alpha = isokineticVelocityFilterAlpha
  if (maxExtensionForceTaperM != null) body.max_extension_force_taper_m = maxExtensionForceTaperM
  if (positionGuardWarningTurns != null) body.position_guard_warning_turns = positionGuardWarningTurns
  if (positionGuardHardTurns != null) body.position_guard_hard_turns = positionGuardHardTurns
  return postJson('/api/exercise/update_force_settings', body)
}
