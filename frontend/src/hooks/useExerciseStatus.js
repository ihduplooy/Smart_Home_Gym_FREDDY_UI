import { useEffect, useRef, useState } from 'react'
import { getExerciseStatus } from '../api/exercise'
import { getControlTelemetry } from '../api/control'

// Bounded so recharts stays smooth; matches useControlTelemetry's window.
const MAX_CHART_POINTS = 300

// Polls REST, same rationale as useControlTelemetry.js (flask-sock's
// close-path race under Werkzeug). Unlike Control/Profiles, this keeps
// polling /api/exercise/status even while nothing is running: cable.is_homed
// must stay visible after a Stop (spec §3.5 -- Reset Position needs a
// still-valid home to be visible while idle), so this can't gate on
// status.control.running the way useControlTelemetry gates on `enabled`.
const POLL_INTERVAL_MS = 150

/**
 * Polls Exercise status (control + cable) plus new ring-buffer samples for
 * the live charts. Local to the Exercise tab -- polls while `enabled` (tab
 * active), stops and clears otherwise.
 */
export function useExerciseStatus(enabled) {
  const [status, setStatus] = useState(null) // { control, cable }
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
        const next = await getExerciseStatus()
        if (cancelled) return
        setStatus(next)
        setConnected(true)

        if (next.control?.running) {
          const samples = await getControlTelemetry(lastTRef.current ?? undefined)
          if (cancelled) return
          if (samples.length) {
            lastTRef.current = samples[samples.length - 1].t
            const merged = seriesRef.current.concat(samples)
            if (merged.length > MAX_CHART_POINTS) merged.splice(0, merged.length - MAX_CHART_POINTS)
            seriesRef.current = merged
            setSeries(merged)
          }
        } else if (seriesRef.current.length) {
          seriesRef.current = []
          lastTRef.current = null
          setSeries([])
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
