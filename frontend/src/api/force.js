// Typed client for the Exercise tab's Force Feedback section
// (backend/app/force_routes.py). Layer B Session B1: concentric-only force
// feedback (exercise_tab_build_spec_layerB.md). REST polling only, no
// websocket -- same precedent as Control/Profiles/Exercise. Status is
// shared with the Exercise tab's own hook (GET /api/exercise/status) since
// it's generic regardless of which mode is active.
//
//   POST /api/force/start           {} -- arms, zero torque
//   POST /api/force/engage          { mode: "constant"|"isokinetic", force_n, velocity_target_turns_s? }
//   POST /api/force/update_params   same shape as engage -- live retarget while ENGAGED/HOLDING
//   POST /api/force/disengage
//   POST /api/force/resume          -- manual fault recovery, confirm in the UI first
//   POST /api/force/stop

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

export function startForceSession() {
  return postJson('/api/force/start')
}

export function engageForce(mode, forceN, velocityTargetTurnsS) {
  const body = { mode, force_n: forceN }
  if (velocityTargetTurnsS != null) body.velocity_target_turns_s = velocityTargetTurnsS
  return postJson('/api/force/engage', body)
}

export function updateForceParams(mode, forceN, velocityTargetTurnsS) {
  const body = { mode, force_n: forceN }
  if (velocityTargetTurnsS != null) body.velocity_target_turns_s = velocityTargetTurnsS
  return postJson('/api/force/update_params', body)
}

export function disengageForce() {
  return postJson('/api/force/disengage')
}

export function resumeForce() {
  return postJson('/api/force/resume')
}

export function stopForce() {
  return postJson('/api/force/stop')
}
