import { describe, it, expect } from 'vitest'
import { appendAndTrimByAge } from '../telemetryBuffer'

describe('appendAndTrimByAge', () => {
  it('returns the existing series unchanged when there are no new samples', () => {
    const existing = [{ t: 1, v: 1 }]
    expect(appendAndTrimByAge(existing, [], 10)).toBe(existing)
  })

  it('appends without trimming when everything is within the buffer window', () => {
    const existing = [{ t: 0, v: 0 }, { t: 1, v: 1 }]
    const result = appendAndTrimByAge(existing, [{ t: 2, v: 2 }], 10)
    expect(result.map((p) => p.t)).toEqual([0, 1, 2])
  })

  it('evicts samples older than bufferS relative to the newest sample', () => {
    const existing = [{ t: 0, v: 0 }, { t: 5, v: 5 }, { t: 9, v: 9 }]
    const result = appendAndTrimByAge(existing, [{ t: 10, v: 10 }], 5)
    // cutoff = 10 - 5 = 5 -- t=0 falls out, t=5 sits exactly on the cutoff (kept)
    expect(result.map((p) => p.t)).toEqual([5, 9, 10])
  })

  it('never mutates the existing series array', () => {
    const existing = [{ t: 0, v: 0 }]
    const existingCopy = [...existing]
    appendAndTrimByAge(existing, [{ t: 1, v: 1 }], 10)
    expect(existing).toEqual(existingCopy)
  })

  it('handles a single incoming sample with an empty existing series', () => {
    const result = appendAndTrimByAge([], [{ t: 0, v: 42 }], 10)
    expect(result).toEqual([{ t: 0, v: 42 }])
  })

  it('keeps buffer duration independent of sample rate (many samples, same window)', () => {
    const dense = Array.from({ length: 1000 }, (_, i) => ({ t: i * 0.01, v: i })) // 10s @ 100Hz
    const result = appendAndTrimByAge([], dense, 5)
    const newestT = result[result.length - 1].t
    const oldestT = result[0].t
    expect(newestT - oldestT).toBeLessThanOrEqual(5)
    expect(result.length).toBeLessThan(dense.length) // actually trimmed, not just point-capped
  })
})
