// Typed client for the Exercise tab's Force Feedback section
// (backend/app/force_routes.py). REST polling only, no websocket -- same
// precedent as Control/Profiles/Exercise. Status is shared with the
// Exercise tab's own hook (GET /api/exercise/status) since it's generic
// regardless of what's active.
//
// Force feedback used to be a separate ControlSession session ("force"),
// mutually exclusive with Exercise -- merged 24 July 2026 (see
// backend/app/force_routes.py's module docstring): there's no more
// start/stop here, engage/disengage/update_params/resume are just actions
// on the one running Exercise session (started via exercise.js's
// startExerciseSession()).
//
//   POST /api/force/engage          { mode: "constant"|"isokinetic", concentric_force_n, eccentric_force_n,
//                                      velocity_target_turns_s?, start_length_m?, end_length_m? }
//   POST /api/force/update_params   same shape as engage -- live retarget while ENGAGED/HOLDING
//   POST /api/force/disengage
//   POST /api/force/resume          -- manual fault recovery, confirm in the UI first; moves to a
//                                      SETTLING state, Engage stays refused until velocity settles
//
// concentric_force_n/eccentric_force_n (split 24 July 2026 -- "separate
// configurable force for eccentric"): the resistance applied while pulling
// out vs. while controlling the return, independently.
// start_length_m/end_length_m (requested 23 July 2026): the sub-range of
// home->max travel where resistance is active. Either, both, or neither may
// be given; omitted defaults to the full range server-side.

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

function _forceParamsBody({ mode, concentricForceN, eccentricForceN, velocityTargetTurnsS, startLengthM, endLengthM }) {
  const body = { mode, concentric_force_n: concentricForceN, eccentric_force_n: eccentricForceN }
  if (velocityTargetTurnsS != null) body.velocity_target_turns_s = velocityTargetTurnsS
  if (startLengthM != null) body.start_length_m = startLengthM
  if (endLengthM != null) body.end_length_m = endLengthM
  return body
}

export function engageForce(params) {
  return postJson('/api/force/engage', _forceParamsBody(params))
}

export function updateForceParams(params) {
  return postJson('/api/force/update_params', _forceParamsBody(params))
}

export function disengageForce() {
  return postJson('/api/force/disengage')
}

export function resumeForce() {
  return postJson('/api/force/resume')
}
