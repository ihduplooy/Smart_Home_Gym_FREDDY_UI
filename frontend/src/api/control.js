// Typed client for the Control tab's backend routes (backend/app/control_routes.py).
//
//   GET  /api/control/status
//   POST /api/control/start           { mode, target }
//   POST /api/control/target          { value }
//   POST /api/control/stop
//   GET  /api/control/hardware-source
//   POST /api/control/hardware-source { hardware_source }
//   GET  /api/control/telemetry[?since=]   (REST fallback for the WS stream)
//   WS   /ws/control-telemetry

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
    body: JSON.stringify(body),
  })
}

export function getControlStatus() {
  return getJson('/api/control/status')
}

export function startControlSession(mode, target) {
  return postJson('/api/control/start', { mode, target })
}

export function setControlTarget(value) {
  return postJson('/api/control/target', { value })
}

export function stopControlSession() {
  return postJson('/api/control/stop', {})
}

export function getHardwareSource() {
  return getJson('/api/control/hardware-source')
}

export function setHardwareSource(source) {
  return postJson('/api/control/hardware-source', { hardware_source: source })
}

export function getControlTelemetry(since) {
  const q = since != null ? `?since=${encodeURIComponent(since)}` : ''
  return getJson(`/api/control/telemetry${q}`)
}

// Not currently used by the UI — useControlTelemetry.js polls
// getControlTelemetry() instead. See its header comment / docs/decisions.md
// for why: Werkzeug's dev server doesn't close flask-sock connections
// cleanly when opened/closed as often as tab switches do here. Kept because
// the backend route is correct and may be worth revisiting under a
// production WSGI server in Phase 2A.
export function controlTelemetryUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/ws/control-telemetry`
}
