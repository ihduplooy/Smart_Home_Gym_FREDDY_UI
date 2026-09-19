// Named, color-coded presets for the Train tab's linear ("band") profile
// shape (resistance-modes sub-phase 3, Part B). Frontend-only convenience --
// selecting one just pre-fills a segment's existing start_force_n/
// end_force_n fields (core/cable/train_profiles.py's actual linear-shape
// field names, confirmed in Step 0) exactly as if the user had typed them
// in by hand. No backend route, no new persistence, no new profile/segment
// shape.
//
// There's no real cross-brand industry-standard color-to-tension code for
// resistance bands (it varies by manufacturer), so this picks its own
// light -> heavy scale (green -> blue -> purple -> black) and documents it
// here rather than trying to match any particular brand's convention.
//
// Force values (Newtons, matching train_profiles.py's own unit) are
// placeholders picked to be a plausible light-to-heavy spread within
// FORCE_MAX_N -- NOT bench-validated. Per the sub-phase 3 doc: test each
// preset's steepness live on the bench and adjust these numbers before
// treating them as final defaults.

export const BAND_PRESETS = [
  { name: 'Green', color: '#48BB78', start_force_n: 10, end_force_n: 40 },
  { name: 'Blue', color: '#4299E1', start_force_n: 20, end_force_n: 70 },
  { name: 'Purple', color: '#805AD5', start_force_n: 35, end_force_n: 110 },
  { name: 'Black', color: '#1A202C', start_force_n: 55, end_force_n: 160 },
]
