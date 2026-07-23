// Typed client for the Exercise tab's backend routes
// (backend/app/exercise_routes.py). Layer A: cable-attached positioning &
// safety (exercise_tab_build_spec_layerA.md). REST polling only, matching
// the Control/Profiles precedent — no websocket.
//
//   GET  /api/exercise/status
//   POST /api/exercise/start                  {} -- arms, zero motion
//   POST /api/exercise/home
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
//   POST /api/exercise/update_calib_hold_force { force_n }

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

export function updateCalibHoldForce(forceN) {
  return postJson('/api/exercise/update_calib_hold_force', { force_n: forceN })
}
