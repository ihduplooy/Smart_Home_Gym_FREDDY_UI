// Shared rolling-buffer eviction for polled telemetry hooks (train_tab_
// build_spec.md "calibration overhaul" item 6) -- extracted verbatim out of
// useTrainTelemetry.js, which was the one hook that already got this right:
// it evicts by sample AGE against a target buffer duration (seconds), not
// by a fixed point count. A fixed-count buffer's real duration silently
// depends on the poll/tick rate -- useControlTelemetry.js's old
// MAX_CHART_POINTS=300 cap held only ~6s of real history at the telemetry
// loop's 50Hz tick rate, no matter what its "60s"/"All" range buttons
// claimed to offer (see docs/decisions.md, "Train tab" entry, for the bug
// this originally fixed for Train; useControlTelemetry.js had the same bug
// and gets the same fix here).
//
// `existingSeries`/`newSamples` are plain {t, ...} arrays (t in seconds,
// already comparable across both); returns a new merged-and-trimmed array,
// never mutates its inputs.
export function appendAndTrimByAge(existingSeries, newSamples, bufferS) {
  if (!newSamples.length) return existingSeries
  const merged = existingSeries.concat(newSamples)
  const cutoff = merged[merged.length - 1].t - bufferS
  let start = 0
  while (start < merged.length && merged[start].t < cutoff) start++
  return start > 0 ? merged.slice(start) : merged
}
