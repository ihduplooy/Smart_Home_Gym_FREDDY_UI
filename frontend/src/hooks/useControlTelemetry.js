import { useEffect, useRef, useState } from 'react'
import { getControlStatus, getControlTelemetry } from '../api/control'
import { getExerciseStatus } from '../api/exercise'
import { correctedTorqueNm } from '../utils/cableGeometry'
import { appendAndTrimByAge } from '../utils/telemetryBuffer'

// Rolling buffer duration (train_tab_build_spec.md "calibration overhaul"
// item 6a) -- evicted by sample AGE via utils/telemetryBuffer.js's
// appendAndTrimByAge(), the same age-based strategy useTrainTelemetry.js
// already used, replacing a fixed MAX_CHART_POINTS=300 point-count cap that
// silently held only ~6s of real history at the telemetry loop's 50Hz tick
// rate regardless of what MiniChart's own "60s"/"All" range buttons
// claimed to offer (see docs/decisions.md, "Train tab" entry, for the
// original bug report this same fix already addressed for Train). No
// per-tab-adjustable setting for Control the way Train's is (CableState-
// backed) -- a fixed constant matching Train's own default is enough for
// now; Control has no natural persisted-settings home to put one in.
// Exported so ControlTab.jsx can pass the exact same duration to
// TelemetryTimeSeriesChart's `bufferS` prop (its range buttons cap
// themselves at bufferS) rather than a second hardcoded copy that could
// drift out of sync with the buffer this hook actually keeps.
export const CONTROL_TELEMETRY_BUFFER_S = 90

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
// Calibration constants (torque_model scale/offset) change rarely -- no need
// for the 150ms telemetry cadence, same rationale useTestingTelemetry.js's
// own slower `cable` poll already follows.
const CABLE_POLL_INTERVAL_MS = 1000

/**
 * Polls control status + new ring-buffer samples. Local to the Control tab —
 * polls while `enabled` (i.e. the tab is active), stops and clears
 * otherwise. Also polls /api/exercise/status for the `cable` calibration
 * snapshot (item 1, "calibration becomes the single source of truth" --
 * Control tab's own Torque display/targets used to bypass the calibrated
 * model entirely, unlike Train/Testing) so torque_est can be corrected the
 * same way useTestingTelemetry.js already does.
 */
export function useControlTelemetry(enabled) {
  const [status, setStatus] = useState(null)
  const [series, setSeries] = useState([])
  const [connected, setConnected] = useState(false)
  const [cable, setCable] = useState(null)

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
        const [nextStatus, samples] = await Promise.all([
          getControlStatus(),
          getControlTelemetry(lastTRef.current ?? undefined),
        ])
        if (cancelled) return
        setStatus(nextStatus)
        setConnected(true)
        if (samples.length) {
          // Stamp each new sample with the target position active *at poll
          // time* -- position-mode targets only change on an explicit
          // retarget (rare relative to the ~150ms poll rate), so treating
          // every sample in this batch as sharing the latest target is an
          // accurate-enough history for the chart overlay without the
          // backend needing to record a target alongside every ring-buffer
          // sample itself.
          const targetPosition =
            nextStatus?.mode === 'position' && nextStatus?.target && typeof nextStatus.target === 'object'
              ? nextStatus.target.position
              : null
          const torqueScale = cableRef.current?.torque_model?.scale ?? 1.0
          const torqueOffset = cableRef.current?.torque_model?.offset ?? 0.0
          const stamped = samples.map((s) => ({
            ...s,
            target_position: targetPosition,
            torque_est_corrected: correctedTorqueNm(s.torque_est, torqueScale, torqueOffset),
          }))
          lastTRef.current = samples[samples.length - 1].t
          const next = appendAndTrimByAge(seriesRef.current, stamped, CONTROL_TELEMETRY_BUFFER_S)
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

  return { status, series, connected, cable }
}
