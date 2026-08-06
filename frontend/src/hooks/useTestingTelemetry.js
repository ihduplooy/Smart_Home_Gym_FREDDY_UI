import { useEffect, useRef, useState } from 'react'
import { getControlStatus, getControlTelemetry } from '../api/control'
import { getExerciseStatus } from '../api/exercise'
import { createSpoolGeometry, speedMsFromTurnsS, forceFromTorque } from '../utils/cableGeometry'
import { appendAndTrimByAge } from '../utils/telemetryBuffer'

// Item 2: the Testing tab now drives Control's own `mode: "position"`
// session directly (frontend/src/api/control.js) instead of a dedicated
// "experiment" ControlSession mode -- so this hook is
// useControlTelemetry.js's own polling shape (mode-agnostic REST poll, no
// websocket -- same flask-sock rationale documented there) plus the
// cable-geometry position/velocity/force conversion useTrainTelemetry.js
// already does, PLUS the torque-calibration correction (items 6/7,
// core/cable/torque_calibration.py) on top of the raw torque_est reading.
const POLL_INTERVAL_MS = 150
// Calibration constants (r0/k/growth points/home_turns/torque_model) change
// rarely -- no need for the 150ms telemetry cadence, same rationale
// ControlTab.jsx's own `cableGeometry` state already follows.
const CABLE_POLL_INTERVAL_MS = 1000
const DEFAULT_BUFFER_S = 90

/**
 * Polls /api/control/status + new ring-buffer samples (mode-agnostic --
 * works whether this tab, Control, or nothing owns the session), plus a
 * slower poll of /api/exercise/status for the `cable` calibration snapshot.
 * Converts each sample to position_m/velocity_m_s/force_est_n the same way
 * useTrainTelemetry.js does, with the torque-calibration correction applied
 * before the force conversion.
 */
export function useTestingTelemetry(enabled) {
  const [status, setStatus] = useState(null)
  const [cable, setCable] = useState(null)
  const [series, setSeries] = useState([])
  const [connected, setConnected] = useState(false)

  const seriesRef = useRef([])
  const lastTRef = useRef(null)
  const cableRef = useRef(null)

  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    let timer = null

    async function poll() {
      if (cancelled) return
      try {
        const nextStatus = await getControlStatus()
        if (cancelled) return
        setStatus(nextStatus)
        setConnected(true)

        const samples = await getControlTelemetry(lastTRef.current ?? undefined)
        if (cancelled) return
        if (samples.length) {
          lastTRef.current = samples[samples.length - 1].t

          const c = cableRef.current
          const r0 = c?.r0
          const homeTurns = c?.home_turns
          const growthPoints = (c?.spool_model?.growth_points ?? []).map((p) => [p.turns_from_home, p.length_m])
          const minREffM = c?.spool_model?.min_effective_radius_m ?? 0
          const spoolGeometry = r0 != null ? createSpoolGeometry(r0, c.k ?? 0, growthPoints, minREffM) : null
          const torqueScale = c?.torque_model?.scale ?? 1.0
          const torqueOffset = c?.torque_model?.offset ?? 0.0
          // Same "stamp every sample in this batch with the target active at
          // poll time" convention useControlTelemetry.js already uses --
          // retargets are rare relative to the ~150ms poll rate.
          const targetPositionTurns =
            nextStatus?.mode === 'position' && nextStatus?.target && typeof nextStatus.target === 'object'
              ? nextStatus.target.position
              : null

          const converted = samples.map((s) => {
            const turnsDelta = homeTurns != null ? s.position - homeTurns : null
            const rEff = spoolGeometry && turnsDelta != null ? spoolGeometry.rEffAtTurnsDelta(turnsDelta) : null
            const correctedTorqueNm = torqueScale * s.torque_est + torqueOffset
            const targetTurnsDelta = homeTurns != null && targetPositionTurns != null ? targetPositionTurns - homeTurns : null
            return {
              t: s.t,
              position_m: spoolGeometry && turnsDelta != null ? spoolGeometry.lengthFromTurnsDelta(turnsDelta) : null,
              velocity_m_s: r0 ? speedMsFromTurnsS(s.velocity, r0) : null,
              torque_est_nm: s.torque_est,
              corrected_torque_nm: correctedTorqueNm,
              force_est_n: rEff ? forceFromTorque(correctedTorqueNm, rEff) : null,
              current_iq_a: s.current_iq,
              bus_voltage_v: s.bus_voltage_v,
              estimated_power_w: s.torque_est * s.velocity * 2 * Math.PI,
              target_position_m:
                spoolGeometry && targetTurnsDelta != null ? spoolGeometry.lengthFromTurnsDelta(targetTurnsDelta) : null,
            }
          })

          const trimmed = appendAndTrimByAge(seriesRef.current, converted, DEFAULT_BUFFER_S)
          seriesRef.current = trimmed
          setSeries(trimmed)
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

  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    let timer = null

    async function poll() {
      if (cancelled) return
      try {
        const s = await getExerciseStatus()
        if (!cancelled) {
          cableRef.current = s.cable
          setCable(s.cable)
        }
      } catch {
        // Transient poll failure -- keep the last known calibration snapshot.
      } finally {
        if (!cancelled) timer = setTimeout(poll, CABLE_POLL_INTERVAL_MS)
      }
    }
    poll()

    return () => {
      cancelled = true
      clearTimeout(timer)
      cableRef.current = null
      setCable(null)
    }
  }, [enabled])

  return { status, cable, series, connected }
}
