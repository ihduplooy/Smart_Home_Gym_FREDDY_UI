import { describe, it, expect, beforeEach, vi } from 'vitest'
import { listTrainProfiles, saveTrainProfile, deleteTrainProfile } from '../trainProfilesManager'

// Minimal localStorage shim for the Node test environment (same shape as
// presetsManager.test.js's).
beforeEach(() => {
  const store = new Map()
  vi.stubGlobal('localStorage', {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
  })
})

const profile = (name) => ({ name, segments: [{ start_pos_m: 0, end_pos_m: 1, shape: 'constant', params: { force_n: 50 } }] })

describe('trainProfilesManager', () => {
  it('starts empty', () => {
    expect(listTrainProfiles()).toEqual([])
  })

  it('saves and lists profiles', () => {
    saveTrainProfile(profile('a'))
    saveTrainProfile(profile('b'))
    expect(listTrainProfiles().map((p) => p.name)).toEqual(['a', 'b'])
  })

  it('overwrites by name', () => {
    saveTrainProfile(profile('a'))
    const changed = { name: 'a', segments: [] }
    saveTrainProfile(changed)
    const all = listTrainProfiles()
    expect(all).toHaveLength(1)
    expect(all[0].segments).toEqual([])
  })

  it('deletes by name', () => {
    saveTrainProfile(profile('a'))
    saveTrainProfile(profile('b'))
    deleteTrainProfile('a')
    expect(listTrainProfiles().map((p) => p.name)).toEqual(['b'])
  })
})
