// Typed client for the Profiles tab's registry route (backend/app/control_routes.py).
//
//   GET /api/profiles

async function getJson(url) {
  const res = await fetch(url)
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      detail = body?.error || JSON.stringify(body)
    } catch {
      detail = await res.text().catch(() => '')
    }
    throw new Error(`GET ${url} failed (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return res.json()
}

// Returns the registry-driven profile list: [{ name, is_wrapper, primary_parameter,
// parameters: { <key>: { label, value, default, min, max } }, ... }]. Never
// hardcode profile names in components — always read this list.
export function getProfiles() {
  return getJson('/api/profiles')
}
