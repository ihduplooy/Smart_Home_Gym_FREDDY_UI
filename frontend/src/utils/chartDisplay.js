// Display-only helpers for live telemetry charts. Both operate on whatever
// array a chart is about to render and return a new array -- they never
// mutate or feed back into the caller's data, so the underlying telemetry
// buffer/log a chart's `data` prop was built from stays untouched.

// Trailing simple moving average, smoothing visual jitter without losing any
// logged/telemetry precision (the raw values still live in `data`/the
// buffers it came from -- only this rendered copy is averaged).
export function movingAverage(data, key, window) {
  if (window <= 1) return data
  const buf = []
  let sum = 0
  return data.map((point) => {
    const value = point[key]
    if (typeof value !== 'number') return point
    buf.push(value)
    sum += value
    if (buf.length > window) sum -= buf.shift()
    return { ...point, [key]: sum / buf.length }
  })
}

// Keeps only the trailing `seconds` of a {t, ...} series (t already relative,
// in seconds). `seconds == null` means "no filtering, show everything".
export function filterByRange(data, seconds) {
  if (seconds == null || data.length === 0) return data
  const maxT = data[data.length - 1].t
  const minT = maxT - seconds
  return data.filter((p) => p.t >= minT)
}

// Age-based counterpart to filterByRange() above, for callers whose `t` is
// still an absolute epoch-ms timestamp rather than an already-relative
// seconds value (train_tab_build_spec.md "calibration overhaul" item 6b --
// Inspector's LiveCharts.jsx, whose raw WebSocket samples carry epoch-ms).
// Keeps only the trailing `ms` milliseconds ending at the newest sample.
// `ms == null` means "no filtering, show everything" -- same convention as
// filterByRange()'s `seconds == null`.
export function filterByAgeMs(data, ms) {
  if (ms == null || data.length === 0) return data
  const newestT = data[data.length - 1].t
  const cutoff = newestT - ms
  return data.filter((p) => p.t >= cutoff)
}

// Resolves a Train tab AxisRangeControl `{auto, min, max}` selection
// (frontend/src/components/tabs/train/AxisRangeControl.jsx) to a recharts
// `domain` -- ['auto','auto'] whenever auto is on or min/max aren't both
// valid numbers with min < max, else the explicit [min, max] pair.
export function domainFromRange(range) {
  if (!range || range.auto) return ['auto', 'auto']
  const min = Number(range.min)
  const max = Number(range.max)
  if (range.min === '' || range.max === '' || !Number.isFinite(min) || !Number.isFinite(max) || min >= max) {
    return ['auto', 'auto']
  }
  return [min, max]
}
