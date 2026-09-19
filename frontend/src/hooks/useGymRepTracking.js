import { useEffect, useMemo, useRef, useState } from 'react'

// GYM dashboard (resistance-modes sub-phase 5) rep/tempo/work tracking.
// Deliberately NOT its own telemetry poll -- TrainSessionShell already runs
// the one useTrainTelemetry(isActive) subscription GYM needs and passes its
// latest tick() `extra` dict down as `liveExtra`/its running flag as
// `sessionRunning` (see TrainSessionShell.jsx's own doc comment on that
// prop). This hook only takes those two as input and derives rep/tempo/work
// state from them client-side -- a second poll loop here would just be
// wasted duplicate REST traffic hitting the same status endpoint.
//
// Every force value passed in (extra.commanded_force_n, ...) already went
// through CableState's calibration model server-side (core/cable/
// train_mode.py's tick()) -- this hook never recomputes force from raw
// torque, only reads what the backend already calibrated.
//
// Velocity is a derivative of position samples and genuinely noisy --
// EMA-smoothed here once (VELOCITY_SMOOTHING_ALPHA), shared by every panel
// that needs a speed reading (Constant's rep-speed gauge, Concentric/
// Eccentric's rep-speed readout) rather than each one smoothing its own
// copy.
//
// Rep boundaries come from extra.rep_count (core/profiles/detectors.py's
// PhaseDetector+RepCounter, now running inside TrainMode purely as
// telemetry). Per-rep peak force/stretch, phase-tagged (concentric/
// eccentric) peaks+averages, and a force-vs-position point trail (for the
// Ghost Trace overlay) are all accumulated tick-by-tick here, generically --
// which fields a given panel actually displays is that panel's own concern.

const VELOCITY_SMOOTHING_ALPHA = 0.3
const MAX_REP_HISTORY = 50

function freshRepAccumulator(startedAtS) {
  return {
    startedAtS,
    peakForceN: 0,
    peakCableLengthM: 0,
    peakConcentricForceN: 0,
    peakEccentricForceN: 0,
    points: [],
    inRangeTicks: 0,
    totalTicks: 0,
    _concentricSum: 0,
    _concentricTicks: 0,
    _eccentricSum: 0,
    _eccentricTicks: 0,
  }
}

function finalizeRep(rep, repNumber, endedAtS) {
  return {
    rep: repNumber,
    durationS: Math.max(0, endedAtS - rep.startedAtS),
    peakForceN: rep.peakForceN,
    peakCableLengthM: rep.peakCableLengthM,
    peakConcentricForceN: rep.peakConcentricForceN,
    peakEccentricForceN: rep.peakEccentricForceN,
    avgConcentricForceN: rep._concentricTicks ? rep._concentricSum / rep._concentricTicks : 0,
    avgEccentricForceN: rep._eccentricTicks ? rep._eccentricSum / rep._eccentricTicks : 0,
    timeInRangeFraction: rep.totalTicks ? rep.inRangeTicks / rep.totalTicks : 0,
    points: rep.points,
  }
}

/**
 * classifyInRange(forceN, extra) -> boolean | null, optional. Only the
 * Constant panel supplies this (a fraction of the current rep's duration
 * spent within tolerance of its target force) -- Band's "reached target
 * stretch" is a simple peak-vs-threshold comparison the panel does directly
 * against peakCableLengthM, no per-tick classification needed.
 */
export function useGymRepTracking(extra, running, classifyInRange) {
  const [repHistory, setRepHistory] = useState([])
  const [speedMS, setSpeedMS] = useState(0)
  const [currentRepPeaks, setCurrentRepPeaks] = useState(() => freshRepAccumulator(0))

  const lastRepCountRef = useRef(0)
  const currentRepRef = useRef(freshRepAccumulator(performance.now() / 1000))
  const speedRef = useRef(0)
  const wasRunningRef = useRef(false)

  useEffect(() => {
    if (!running) {
      if (wasRunningRef.current) {
        // A set just ended (or was stopped) -- clear so the next Start
        // begins from zero, not carrying the previous set's reps/peaks.
        lastRepCountRef.current = 0
        currentRepRef.current = freshRepAccumulator(performance.now() / 1000)
        speedRef.current = 0
        setRepHistory([])
        setSpeedMS(0)
        setCurrentRepPeaks(currentRepRef.current)
      }
      wasRunningRef.current = false
      return
    }
    wasRunningRef.current = true
    if (!extra) return

    const nowS = performance.now() / 1000
    const speedNow = Math.abs(extra.cable_velocity_m_s ?? 0)
    speedRef.current = VELOCITY_SMOOTHING_ALPHA * speedNow + (1 - VELOCITY_SMOOTHING_ALPHA) * speedRef.current
    setSpeedMS(speedRef.current)

    const forceN = extra.commanded_force_n ?? 0
    const cableLengthM = extra.cable_length_m ?? 0
    const phase = extra.phase

    const acc = currentRepRef.current
    acc.peakForceN = Math.max(acc.peakForceN, forceN)
    acc.peakCableLengthM = Math.max(acc.peakCableLengthM, cableLengthM)
    acc.points = [...acc.points, { position_m: cableLengthM, force_n: forceN }]
    if (classifyInRange) {
      const inRange = classifyInRange(forceN, extra)
      if (inRange != null) {
        acc.totalTicks += 1
        if (inRange) acc.inRangeTicks += 1
      }
    }
    if (phase === 'concentric') {
      acc.peakConcentricForceN = Math.max(acc.peakConcentricForceN, forceN)
      acc._concentricSum += forceN
      acc._concentricTicks += 1
    } else if (phase === 'eccentric') {
      acc.peakEccentricForceN = Math.max(acc.peakEccentricForceN, forceN)
      acc._eccentricSum += forceN
      acc._eccentricTicks += 1
    }
    setCurrentRepPeaks({ ...acc })

    const repCount = extra.rep_count ?? 0
    if (repCount > lastRepCountRef.current) {
      const completed = finalizeRep(acc, repCount, nowS)
      setRepHistory((prev) => [...prev, completed].slice(-MAX_REP_HISTORY))
      lastRepCountRef.current = repCount
      currentRepRef.current = freshRepAccumulator(nowS)
    }
    // extra is a fresh object every poll tick (TrainSessionShell re-renders
    // with a new status each ~150ms), so this effect re-firing every change
    // is the point, not an oversight.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extra, running])

  const sessionSummary = useMemo(() => {
    const totalReps = repHistory.length
    const totalWorkJ = extra?.total_work_j ?? 0
    const avgTempoS = totalReps ? repHistory.reduce((sum, r) => sum + r.durationS, 0) / totalReps : 0
    const peakForceN = repHistory.reduce((max, r) => Math.max(max, r.peakForceN), 0)
    return { totalReps, totalWorkJ, avgTempoS, peakForceN }
  }, [repHistory, extra])

  return { repHistory, currentRepPeaks, speedMS, sessionSummary }
}
