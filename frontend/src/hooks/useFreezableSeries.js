import { useRef, useState } from 'react'

/**
 * Pause/freeze for a live telemetry series (train_tab_build_spec.md
 * "calibration overhaul" item 5) -- pins a chart to a snapshot so it can be
 * inspected without the underlying poll being disturbed. Deliberately a
 * thin wrapper around whatever `liveSeries` array a telemetry hook (e.g.
 * useTrainTelemetry) already produces, not baked into that hook or its
 * chart component, so the same freeze behavior is trivial to reuse for the
 * Control tab / Inspector's own telemetry views later (item 6) without
 * duplicating this logic three times.
 *
 * Semantics: pausing snapshots the series at that instant and pins the
 * chart to it; the underlying poll keeps running unaffected (nothing is
 * lost -- Stop/Reset and any other control still see live data). Resuming
 * drops the snapshot and jumps straight back to whatever `liveSeries`
 * currently is -- a jump forward, not a gap-filling replay.
 */
export function useFreezableSeries(liveSeries) {
  const [paused, setPaused] = useState(false)
  const frozenRef = useRef(null)

  const togglePause = () => {
    setPaused((wasPaused) => {
      frozenRef.current = wasPaused ? null : liveSeries
      return !wasPaused
    })
  }

  const reset = () => {
    frozenRef.current = null
    setPaused(false)
  }

  return { displaySeries: paused ? frozenRef.current : liveSeries, paused, togglePause, reset }
}
