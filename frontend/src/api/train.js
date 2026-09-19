// Typed client for the Train tab's backend routes (backend/app/train_routes.py).
// REST polling only, matching every other tab's precedent -- no websocket.
//
//   GET  /api/train/status
//   POST /api/train/start            { profile?, phase_forces? }
//   POST /api/train/stop
//   POST /api/train/set_profile      { profile?, phase_forces? }
//   POST /api/train/update_settings  { max_extension_enforced?, home_guard_enforced?, telemetry_buffer_s?, resistance_display_unit_kg? }
//   POST /api/train/update_inertia_settings  { inertia_kg_max?, inertia_velocity_filter_alpha? }
//   POST /api/train/update_phase_settings    { phase_force_delta_max_n?, velocity_deadband_m_s?, min_sustained_velocity_m_s?, sustain_window_s?, reversal_distance_m?, ramp_duration_s? }
//   POST /api/train/update_gym_dashboard_settings  { constant_force_tolerance_fraction?, band_stretch_tolerance_pct?, rep_speed_low_m_s?, rep_speed_high_m_s?, rep_speed_max_m_s? }
//   POST /api/train/preview_profile  { profile, position_range_m: [lo, hi], n_points? } -> { points: [{position_m, force_n}] }
//
// update_inertia_settings/update_phase_settings (resistance-modes sub-phases
// 3/4's "configure in a GYM Settings sub-tab" follow-up): current values are
// read back off GET /api/train/status's own `cable` object (inertia_kg_max,
// phase_velocity_deadband_m_s, etc. -- see exercise_routes.py's
// _cable_status_dict()), same as every other live-adjustable setting already
// surfaced there.
//
// phase_forces (resistance-modes sub-phase 4, GYM's Concentric/Eccentric
// mode): { concentric_force_n, eccentric_force_n } | null -- mutually
// exclusive with `profile`-driven position-based playback (TrainMode bypasses
// the profile entirely once phase_forces is set); startTrainSession/
// setTrainProfile below take `{ profile, phaseForces }` (either or both, most
// callers only ever send one) rather than a bare profile, matching the two
// alternative shapes TrainMode.validate_target() itself accepts.
//
// Homing / max-extension calibration / spool calibration (k, r0) are NOT
// duplicated here -- the Train tab's Settings section calls the existing
// /api/exercise/* routes directly (frontend/src/api/exercise.js), same
// shared cable_state regardless of which mode is running.

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

export function getTrainStatus() {
  return getJson('/api/train/status')
}

export function startTrainSession({ profile, phaseForces } = {}) {
  const body = {}
  if (profile) body.profile = profile
  if (phaseForces) body.phase_forces = phaseForces
  return postJson('/api/train/start', body)
}

export function stopTrainSession() {
  return postJson('/api/train/stop')
}

export function setTrainProfile({ profile, phaseForces } = {}) {
  const body = {}
  if (profile) body.profile = profile
  if (phaseForces) body.phase_forces = phaseForces
  return postJson('/api/train/set_profile', body)
}

export function updateTrainSettings({ maxExtensionEnforced, homeGuardEnforced, telemetryBufferS, resistanceDisplayUnitKg } = {}) {
  const body = {}
  if (maxExtensionEnforced != null) body.max_extension_enforced = maxExtensionEnforced
  if (homeGuardEnforced != null) body.home_guard_enforced = homeGuardEnforced
  if (telemetryBufferS != null) body.telemetry_buffer_s = telemetryBufferS
  if (resistanceDisplayUnitKg != null) body.resistance_display_unit_kg = resistanceDisplayUnitKg
  return postJson('/api/train/update_settings', body)
}

export function updateInertiaSettings({ inertiaKgMax, inertiaVelocityFilterAlpha } = {}) {
  const body = {}
  if (inertiaKgMax != null) body.inertia_kg_max = inertiaKgMax
  if (inertiaVelocityFilterAlpha != null) body.inertia_velocity_filter_alpha = inertiaVelocityFilterAlpha
  return postJson('/api/train/update_inertia_settings', body)
}

export function updatePhaseSettings({
  phaseForceDeltaMaxN,
  velocityDeadbandMS,
  minSustainedVelocityMS,
  sustainWindowS,
  reversalDistanceM,
  rampDurationS,
} = {}) {
  const body = {}
  if (phaseForceDeltaMaxN != null) body.phase_force_delta_max_n = phaseForceDeltaMaxN
  if (velocityDeadbandMS != null) body.velocity_deadband_m_s = velocityDeadbandMS
  if (minSustainedVelocityMS != null) body.min_sustained_velocity_m_s = minSustainedVelocityMS
  if (sustainWindowS != null) body.sustain_window_s = sustainWindowS
  if (reversalDistanceM != null) body.reversal_distance_m = reversalDistanceM
  if (rampDurationS != null) body.ramp_duration_s = rampDurationS
  return postJson('/api/train/update_phase_settings', body)
}

export function updateGymDashboardSettings({
  constantForceToleranceFraction,
  bandStretchTolerancePct,
  repSpeedLowMS,
  repSpeedHighMS,
  repSpeedMaxMS,
} = {}) {
  const body = {}
  if (constantForceToleranceFraction != null) body.constant_force_tolerance_fraction = constantForceToleranceFraction
  if (bandStretchTolerancePct != null) body.band_stretch_tolerance_pct = bandStretchTolerancePct
  if (repSpeedLowMS != null) body.rep_speed_low_m_s = repSpeedLowMS
  if (repSpeedHighMS != null) body.rep_speed_high_m_s = repSpeedHighMS
  if (repSpeedMaxMS != null) body.rep_speed_max_m_s = repSpeedMaxMS
  return postJson('/api/train/update_gym_dashboard_settings', body)
}

export function previewTrainProfile(profile, positionRangeM, nPoints) {
  const body = { profile, position_range_m: positionRangeM }
  if (nPoints != null) body.n_points = nPoints
  return postJson('/api/train/preview_profile', body)
}
