// Train resistance profiles: save/load named profiles so a segment layout
// built in the profile editor can be reused across sessions, instead of
// re-typing it every time. Same localStorage + save-by-name-overwrite
// pattern as frontend/src/utils/presets/presetsManager.js, but for the
// {name, segments} TrainProfile shape (core/cable/train_profiles.py) rather
// than a flat config-value map -- kept as its own module since the two
// aren't otherwise related.

const STORAGE_KEY = 'freddy.trainProfiles.v1'

function readStore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeStore(profiles) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(profiles))
}

/** Saved profiles, most-recently-saved last (same order presets use). */
export function listTrainProfiles() {
  return readStore()
}

/** Save (or overwrite by name) a profile payload ({name, segments}). */
export function saveTrainProfile(profile) {
  const profiles = readStore().filter((p) => p.name !== profile.name)
  profiles.push(profile)
  writeStore(profiles)
  return profiles
}

export function deleteTrainProfile(name) {
  const profiles = readStore().filter((p) => p.name !== name)
  writeStore(profiles)
  return profiles
}
