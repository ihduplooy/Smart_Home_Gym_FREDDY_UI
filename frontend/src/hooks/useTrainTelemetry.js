import { useEffect, useRef, useState } from 'react'
import { getTrainStatus } from '../api/train'
import { getControlTelemetry } from '../api/control'
import { createSpoolGeometry, speedMsFromTurnsS, forceFromTorque } from '../utils/cableGeometry'
import { appendAndTrimByAge } from '../utils/telemetryBuffer'

// REST polling, same rationale as useControlTelemetry.js/useExerciseStatus.js
// (flask-sock's close-path race under Werkzeug's dev server) -- no websocket.
const POLL_INTERVAL_MS = 150

// Fallback only, before the first /api/train/status response tells us the
// real persisted value (cable.train_telemetry_buffer_s).
const DEFAULT_BUFFER_S = 90

/**
 * Polls Train status (control + cable) plus new ring-buffer samples,
 * converted to cable position (m) / velocity (m/s) / force (N) client-side
 * (frontend/src/utils/cableGeometry.js) since the raw telemetry stream only
 * carries turns/torque.
 *
 * The rolling buffer evicts by sample AGE (against cable.train_telemetry_
 * buffer_s), not by a fixed point count -- via utils/telemetryBuffer.js's
 * shared appendAndTrimByAge(), item 6's consolidation point. This is the
 * fix for the graph time-window bug documented in docs/decisions.md ("Train
 * tab" entry): a fixed-count buffer's real duration silently depends on the
 * poll/tick rate (MiniChart's old cap held only ~6s of real history at the
 * telemetry loop's 50 Hz tick rate, no matter what its "60s"/"All" range
 * buttons claimed to offer). Evicting by age keeps this buffer's real
 * duration independent of tick/poll rate and always matching what the range
 * selector actually offers.
 */
export function useTrainTelemetry(enabled) {
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
        const next = await getTrainStatus()
        if (cancelled) return
        setStatus(next)
        setConnected(true)

        const { control, cable } = next

        if (control?.running && control?.mode === 'train') {
          const samples = await getControlTelemetry(lastTRef.current ?? undefined)
          if (cancelled) return
          if (samples.length) {
            lastTRef.current = samples[samples.length - 1].t

            const r0 = cable?.r0
            const k = cable?.k ?? 0
            const homeTurns = cable?.home_turns
            // Piecewise growth-calibration mirror (item 3b): built once per
            // poll from whatever's currently saved server-side
            // (cable.spool_model.growth_points), same model TrainMode's own
            // torque conversion uses (item 3a) -- reduces to the flat r0/k
            // model below when no growth calibration is saved, so an
            // uncalibrated rig's chart is unaffected.
            const growthPoints = (cable?.spool_model?.growth_points ?? []).map((p) => [p.turns_from_home, p.length_m])
            const minREffM = cable?.spool_model?.min_effective_radius_m ?? 0
            const spoolGeometry = r0 != null ? createSpoolGeometry(r0, k, growthPoints, minREffM) : null

            const converted = samples.map((s) => {
              const turnsDelta = homeTurns != null ? s.position - homeTurns : null
              const rEff = spoolGeometry && turnsDelta != null ? spoolGeometry.rEffAtTurnsDelta(turnsDelta) : null
              return {
                t: s.t,
                position_m: spoolGeometry && turnsDelta != null ? spoolGeometry.lengthFromTurnsDelta(turnsDelta) : null,
                velocity_m_s: r0 ? speedMsFromTurnsS(s.velocity, r0) : null,
                torque_est_nm: s.torque_est,
                force_est_n: rEff ? forceFromTorque(s.torque_est, rEff) : null,
              }
            })

            const bufferS = cable?.train_telemetry_buffer_s ?? DEFAULT_BUFFER_S
            const trimmed = appendAndTrimByAge(seriesRef.current, converted, bufferS)

            seriesRef.current = trimmed
            setSeries(trimmed)
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
