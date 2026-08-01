// Typed client for the Testing tab's backend routes (backend/app/experiment_routes.py).
// REST polling only, matching every other tab's precedent -- no websocket.
//
//   GET  /api/experiments                 -> [{ name, label, parameters }]
//   GET  /api/experiments/status          -> { control, cable, current_position_m }
//   POST /api/experiments/configure       { experiment, config }
//   POST /api/experiments/confirm_start   -- the motor-energization gate (spec §5)
//   POST /api/experiments/stop
//
// Homing / max-extension / spool calibration are NOT duplicated here -- the
// Testing tab's prerequisite banner reads the same `cable` status every other
// tab reads, and calibration itself happens via the Train tab's existing
// /api/exercise/* routes (frontend/src/api/exercise.js).

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

export function listExperiments() {
  return getJson('/api/experiments')
}

export function getExperimentStatus() {
  return getJson('/api/experiments/status')
}

export function configureExperiment(experiment, config) {
  return postJson('/api/experiments/configure', { experiment, config })
}

export function confirmStartExperiment() {
  return postJson('/api/experiments/confirm_start')
}

export function stopExperiment() {
  return postJson('/api/experiments/stop')
}
