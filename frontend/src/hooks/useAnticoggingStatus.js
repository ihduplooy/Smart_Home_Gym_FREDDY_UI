import { useEffect, useState } from 'react'
import { getAnticoggingStatus } from '../api/anticogging'

// Coarse state-machine polling (idle/running/done/aborted/failed), not a live
// telemetry stream -- much lighter than the 150ms Control/Testing poll rate,
// same REST-polling convention as every other tab (no websocket).
const POLL_INTERVAL_MS = 1000

export function useAnticoggingStatus(enabled) {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    let timer = null
    const poll = async () => {
      try {
        const s = await getAnticoggingStatus()
        if (!cancelled) setStatus(s)
      } catch {
        // Transient poll failure -- keep the last known status rather than
        // flickering the UI.
      }
      if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS)
    }
    poll()
    return () => {
      cancelled = true
      clearTimeout(timer)
      setStatus(null)
    }
  }, [enabled])

  return status
}
