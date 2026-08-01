import { useEffect, useRef, useState } from 'react'
import { getExperimentStatus } from '../api/experiments'
import { getControlTelemetry } from '../api/control'
import { createSpoolGeometry, speedMsFromTurnsS } from '../utils/cableGeometry'
import { appendAndTrimByAge } from '../utils/telemetryBuffer'

// REST polling, same rationale as useControlTelemetry.js/useTrainTelemetry.js
// (flask-sock's close-path race under Werkzeug's dev server) -- no websocket.
const POLL_INTERVAL_MS = 150
const DEFAULT_BUFFER_S = 90

/**
 * Polls Testing-tab status (control + cable + current_position_m) plus new
 * ring-buffer samples, converted to cable position (m) / velocity (m/s) /
 * estimated power (W) client-side (position/velocity via
 * utils/cableGeometry.js, same conversion Train already uses).
 *
 * The ring buffer (core/control/session.py) only ever historizes raw
 * TelemetrySample fields (position/velocity/current_iq/torque_est/
 * bus_voltage_v) -- it does NOT historize per-sample experiment_state/
 * commanded_torque_nm/target_position_m (those are point-in-time-only,
 * exposed via status().extra, same convention Session 3 already established
 * for phase/rep_count -- see docs/decisions.md). So the charted "torque"
 * series here is torque_est (measured/estimated), not the literal commanded
 * value -- same substitution Train's own chart already makes
 * (TRAIN_CHART_LINES labels it "Torque (actual)"). The current commanded
 * torque is still shown as a live numeric readout in TestingTab, sourced
 * from status.control.extra.commanded_torque_nm. target_position_m is
 * injected into every buffered row as a constant (it doesn't change mid-run
 * in v1) so it can be drawn as a flat reference line on the position chart.
 */
export function useExperimentTelemetry(enabled) {
  const [status, setStatus] = useState(null) // { control, cable, current_position_m }
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
        const next = await getExperimentStatus()
        if (cancelled) return
        setStatus(next)
        setConnected(true)

        const { control, cable } = next

        if (control?.running && control?.mode === 'experiment') {
          const samples = await getControlTelemetry(lastTRef.current ?? undefined)
          if (cancelled) return
          if (samples.length) {
            lastTRef.current = samples[samples.length - 1].t

            const r0 = cable?.r0
            const k = cable?.k ?? 0
            const homeTurns = cable?.home_turns
            const growthPoints = (cable?.spool_model?.growth_points ?? []).map((p) => [p.turns_from_home, p.length_m])
            const minREffM = cable?.spool_model?.min_effective_radius_m ?? 0
            const spoolGeometry = r0 != null ? createSpoolGeometry(r0, k, growthPoints, minREffM) : null
            const targetPositionM = control?.extra?.target_position_m ?? null

            const converted = samples.map((s) => {
              const turnsDelta = homeTurns != null ? s.position - homeTurns : null
              const angularVelocityRadS = s.velocity * 2 * Math.PI
              return {
                t: s.t,
                position_m: spoolGeometry && turnsDelta != null ? spoolGeometry.lengthFromTurnsDelta(turnsDelta) : null,
                velocity_m_s: r0 ? speedMsFromTurnsS(s.velocity, r0) : null,
                torque_est_nm: s.torque_est,
                current_iq_a: s.current_iq,
                bus_voltage_v: s.bus_voltage_v,
                estimated_power_w: s.torque_est * angularVelocityRadS,
                target_position_m: targetPositionM,
              }
            })

            const bufferS = DEFAULT_BUFFER_S
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
