// Typed client for the GYM tab's rotary encoder -> Weight field link
// (backend/app/gym_routes.py).
//
//   GET  /api/gym/weight              -> { weight_kg }
//   POST /api/gym/weight  { weight_kg } -> { weight_kg }

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

export function getGymWeight() {
  return getJson('/api/gym/weight')
}

export function setGymWeight(weightKg) {
  return postJson('/api/gym/weight', { weight_kg: weightKg })
}
