// Typed client for anti-cogging calibration (backend/app/anticogging_routes.py).
// REST polling only, matching every other tab's precedent -- no websocket.
//
//   GET  /api/anticogging/status
//   POST /api/anticogging/start        { pos_gain_multiplier?, vel_integrator_gain_multiplier?, calib_pos_threshold?, calib_vel_threshold? }
//   POST /api/anticogging/abort
//   POST /api/anticogging/set_enabled  { enabled }

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

export function getAnticoggingStatus() {
  return getJson('/api/anticogging/status')
}

export function startAnticoggingCalibration(params = {}) {
  return postJson('/api/anticogging/start', params)
}

export function abortAnticoggingCalibration() {
  return postJson('/api/anticogging/abort')
}

export function setAnticoggingEnabled(enabled) {
  return postJson('/api/anticogging/set_enabled', { enabled })
}
