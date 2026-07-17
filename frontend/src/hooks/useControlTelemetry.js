import { useEffect, useRef, useState } from 'react'
import { getControlStatus, getControlTelemetry } from '../api/control'

// Bounded so recharts stays smooth; ~30s of history at the ~150ms poll rate
// below.
const MAX_CHART_POINTS = 300

// REST fallback for /ws/control-telemetry (see backend/app/control_routes.py
// and docs/decisions.md, Session 2): Werkzeug's dev server hands each
// flask-sock connection its own background thread that processes the
// client's close handshake independently of the app's send loop, and the
// Control tab opens/closes this socket on every tab switch — far more often
// than the always-on per-device telemetry socket. That triggered an
// unsynchronized write to the same raw socket from both threads, which
// surfaced client-side as a stray "Invalid frame header" console error on
// close. Polling avoids the open/close churn entirely. The websocket route
// itself is left in place — it works fine once connected and may be worth
// revisiting under a production WSGI server in Phase 2A.
const POLL_INTERVAL_MS = 150

/**
 * Polls control status + new ring-buffer samples. Local to the Control tab —
 * polls while `enabled` (i.e. the tab is active), stops and clears
 * otherwise.
 */
export function useControlTelemetry(enabled) {
  const [status, setStatus] = useState(null)
  const [series, setSeries] = useState([])
  const [connected, setConnected] = useState(false)

  const seriesRef = useRef([])
  const lastTRef = useRef(null)

  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    let timer = null

    async function poll() {
      if (cancelled) return
      try {
        const [nextStatus, samples] = await Promise.all([
          getControlStatus(),
          getControlTelemetry(lastTRef.current ?? undefined),
        ])
        if (cancelled) return
        setStatus(nextStatus)
        setConnected(true)
        if (samples.length) {
          lastTRef.current = samples[samples.length - 1].t
          const next = seriesRef.current.concat(samples)
          if (next.length > MAX_CHART_POINTS) next.splice(0, next.length - MAX_CHART_POINTS)
          seriesRef.current = next
          setSeries(next)
        }
      } catch {
        if (!cancelled) setConnected(false)
      } finally {
        if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }
    poll()

    return () => {
      cancelled = true
      clearTimeout(timer)
      seriesRef.current = []
      lastTRef.current = null
      setSeries([])
      setStatus(null)
      setConnected(false)
    }
  }, [enabled])

  return { status, series, connected }
}
