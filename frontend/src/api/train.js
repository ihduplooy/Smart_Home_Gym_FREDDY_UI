// Typed client for the Train tab's backend routes (backend/app/train_routes.py).
// REST polling only, matching every other tab's precedent -- no websocket.
//
//   GET  /api/train/status
//   POST /api/train/start            { profile? }
//   POST /api/train/stop
//   POST /api/train/set_profile      { profile }
//   POST /api/train/update_settings  { max_extension_enforced?, home_guard_enforced?, telemetry_buffer_s? }
//   POST /api/train/preview_profile  { profile, position_range_m: [lo, hi], n_points? } -> { points: [{position_m, force_n}] }
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

export function startTrainSession(profile) {
  return postJson('/api/train/start', profile ? { profile } : {})
}

export function stopTrainSession() {
  return postJson('/api/train/stop')
}

export function setTrainProfile(profile) {
  return postJson('/api/train/set_profile', { profile })
}

export function updateTrainSettings({ maxExtensionEnforced, homeGuardEnforced, telemetryBufferS } = {}) {
  const body = {}
  if (maxExtensionEnforced != null) body.max_extension_enforced = maxExtensionEnforced
  if (homeGuardEnforced != null) body.home_guard_enforced = homeGuardEnforced
  if (telemetryBufferS != null) body.telemetry_buffer_s = telemetryBufferS
  return postJson('/api/train/update_settings', body)
}

export function previewTrainProfile(profile, positionRangeM, nPoints) {
  const body = { profile, position_range_m: positionRangeM }
  if (nPoints != null) body.n_points = nPoints
  return postJson('/api/train/preview_profile', body)
}
