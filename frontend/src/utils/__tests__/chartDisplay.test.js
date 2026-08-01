import { describe, it, expect } from 'vitest'
import { movingAverage, filterByRange, filterByAgeMs, domainFromRange } from '../chartDisplay'

describe('movingAverage', () => {
  it('is a no-op for window <= 1', () => {
    const data = [{ v: 1 }, { v: 2 }, { v: 3 }]
    expect(movingAverage(data, 'v', 1)).toBe(data)
  })

  it('smooths a trailing window', () => {
    const data = [{ v: 0 }, { v: 10 }, { v: 20 }]
    const result = movingAverage(data, 'v', 2)
    expect(result.map((p) => p.v)).toEqual([0, 5, 15])
  })

  it('leaves non-numeric values untouched', () => {
    const data = [{ v: 1 }, { v: null }, { v: 3 }]
    const result = movingAverage(data, 'v', 2)
    expect(result[1].v).toBeNull()
  })
})

describe('filterByRange', () => {
  it('returns everything when seconds is null', () => {
    const data = [{ t: 0 }, { t: 5 }]
    expect(filterByRange(data, null)).toBe(data)
  })

  it('keeps only the trailing window relative to the last point', () => {
    const data = [{ t: 0 }, { t: 5 }, { t: 9 }, { t: 10 }]
    expect(filterByRange(data, 5).map((p) => p.t)).toEqual([5, 9, 10])
  })
})

describe('filterByAgeMs', () => {
  it('returns an empty array unchanged', () => {
    expect(filterByAgeMs([], 1000)).toEqual([])
  })

  it('returns everything when ms is null', () => {
    const data = [{ t: 0 }, { t: 5000 }]
    expect(filterByAgeMs(data, null)).toBe(data)
  })

  it('keeps only samples within ms of the newest sample', () => {
    const data = [{ t: 1000 }, { t: 8500 }, { t: 9000 }, { t: 10000 }]
    expect(filterByAgeMs(data, 2000).map((p) => p.t)).toEqual([8500, 9000, 10000])
  })

  it('duration stays constant regardless of sample density (the bug this replaces a fixed-point window for)', () => {
    const sparse = [{ t: 0 }, { t: 1000 }, { t: 2000 }] // 3 points over 2s
    const dense = Array.from({ length: 2000 }, (_, i) => ({ t: i })) // 2000 points over ~2s
    const sparseResult = filterByAgeMs(sparse, 1000)
    const denseResult = filterByAgeMs(dense, 1000)
    expect(sparseResult[sparseResult.length - 1].t - sparseResult[0].t).toBeLessThanOrEqual(1000)
    expect(denseResult[denseResult.length - 1].t - denseResult[0].t).toBeLessThanOrEqual(1000)
  })
})

describe('domainFromRange', () => {
  it('defaults to auto/auto when auto is set', () => {
    expect(domainFromRange({ auto: true, min: '1', max: '2' })).toEqual(['auto', 'auto'])
  })

  it('uses explicit min/max when valid and auto is off', () => {
    expect(domainFromRange({ auto: false, min: '1', max: '5' })).toEqual([1, 5])
  })

  it('falls back to auto/auto when min >= max', () => {
    expect(domainFromRange({ auto: false, min: '5', max: '1' })).toEqual(['auto', 'auto'])
  })
})
