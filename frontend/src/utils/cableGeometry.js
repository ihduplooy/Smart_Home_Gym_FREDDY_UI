// Pure JS mirrors of core/cable/geometry.py / core/profiles/units.py's
// conversions. Originally Train-tab-only; also used by the Control tab's
// Position mode (25 July 2026, cable-length unit option) since both need
// the same turns<->metres conversion and there's no other conversion site
// to reuse across a network boundary. Needed because the raw ring-buffer
// telemetry the backend streams (/api/control/telemetry) carries encoder
// turns/velocity/torque_est only -- it has no per-sample cable-length-in-
// metres field (that's computed fresh per *tick* server-side, in the
// active mode's `extra`, not historized per sample).
//
// Keep these in exact lockstep with their Python originals; do not
// reintroduce a second, drifted formula.

const TURNS_TO_RADIANS = 2 * Math.PI

/** Mirrors core/cable/geometry.py's length_from_turns_delta(). */
export function lengthFromTurnsDelta(turnsDelta, r0, k) {
  const theta = Math.abs(turnsDelta) * TURNS_TO_RADIANS
  return r0 * theta + (k / 2) * theta * theta
}

/** Mirrors core/cable/geometry.py's turns_delta_from_length() (inverse of
 * lengthFromTurnsDelta). Returns an unsigned turns magnitude -- callers
 * apply direction/sign themselves, same convention as the Python original. */
export function turnsDeltaFromLength(lengthM, r0, k) {
  if (lengthM < 0) throw new Error(`lengthM must be non-negative, got ${lengthM}`)
  let theta
  if (k === 0) {
    theta = lengthM / r0
  } else {
    const discriminant = r0 * r0 + 2 * k * lengthM
    if (discriminant < 0) throw new Error(`No real solution for length_m=${lengthM} under r0=${r0}, k=${k}`)
    theta = (-r0 + Math.sqrt(discriminant)) / k
  }
  return theta / TURNS_TO_RADIANS
}

/** Mirrors core/cable/geometry.py's speed_m_s_from_turns_s(). */
export function speedMsFromTurnsS(turnsPerS, r0) {
  return turnsPerS * TURNS_TO_RADIANS * r0
}

/** Mirrors core/profiles/units.py's torque_to_force(). */
export function forceFromTorque(torqueNm, r0) {
  return torqueNm / r0
}

// ---- Piecewise growth-calibration mirror (train_tab_build_spec.md
// "calibration overhaul" item 3b) -- mirrors core/cable/geometry.py's
// build_growth_segments()/length_from_angle_piecewise()/
// r_eff_at_turns_delta(), the experimental multi-point spool-growth model
// fit exactly through measured (turns, length) points. Needed because
// useTrainTelemetry.js was, until this fix, only ever using the flat
// r0/k mirror above to convert live-chart samples client-side -- so even
// after core/cable/train_mode.py's own torque fix (item 3a), the Train
// tab's own chart would have kept silently ignoring an active piecewise
// growth calibration for its displayed position/force lines. Keep in exact
// lockstep with geometry.py; do not reintroduce a second, drifted formula.

/** Mirrors core/cable/geometry.py's length_from_angle(). */
function lengthFromAngle(theta, r0, k) {
  const t = Math.abs(theta)
  return r0 * t + (k / 2) * t * t
}

/** Mirrors core/cable/geometry.py's build_growth_segments() (the
 * min_r_eff_m floor check is intentionally omitted here -- this mirror is
 * display-only, fed by already-saved/validated points from the backend, so
 * there's nothing to reject; the backend is the source of truth for
 * validation). `points` is [[turnsFromHome, lengthM], ...]. */
function buildGrowthSegments(r0, points) {
  const sorted = [...points].sort((a, b) => a[0] - b[0])
  const segments = []
  let rStart = r0
  let thetaStart = 0
  let lengthStart = 0
  for (const [turns, lengthM] of sorted) {
    const thetaEnd = turns * TURNS_TO_RADIANS
    const dTheta = thetaEnd - thetaStart
    const dLength = lengthM - lengthStart
    const slope = dTheta === 0 ? 0 : (2 * (dLength - rStart * dTheta)) / (dTheta * dTheta)
    const rEnd = rStart + slope * dTheta
    segments.push({ thetaStart, thetaEnd, rStart, slope, lengthStart, lengthEnd: lengthM })
    rStart = rEnd
    thetaStart = thetaEnd
    lengthStart = lengthM
  }
  const last = segments[segments.length - 1]
  segments.push({ thetaStart: last.thetaEnd, thetaEnd: null, rStart, slope: last.slope, lengthStart: last.lengthEnd, lengthEnd: null })
  return segments
}

function findSegmentForTheta(theta, segments) {
  for (const seg of segments) {
    if (seg.thetaEnd === null || theta <= seg.thetaEnd) return seg
  }
  return segments[segments.length - 1]
}

/** Mirrors core/cable/geometry.py's length_from_angle_piecewise(). */
function lengthFromAnglePiecewise(theta, segments) {
  const t = Math.abs(theta)
  const seg = findSegmentForTheta(t, segments)
  const dTheta = t - seg.thetaStart
  return seg.lengthStart + seg.rStart * dTheta + (seg.slope / 2) * dTheta * dTheta
}

/**
 * Bundles (r0, k, growthPoints) the same way core/cable/geometry.py's
 * SpoolGeometry class does, so callers (useTrainTelemetry.js) don't have to
 * re-derive which model is active on every sample. `growthPoints` is
 * `cable.spool_model.growth_points` from /api/train/status, mapped to
 * `[[turns_from_home, length_m], ...]` pairs -- when empty, every method
 * here reduces to exactly the flat r0/k functions above (same "empty ->
 * completely unchanged" guarantee the Python class documents).
 *
 * `minREffM` mirrors the floor core/cable/train_mode.py's tick() clamps
 * r_eff to (board_constants.SPOOL_MIN_EFFECTIVE_RADIUS_M, already exposed
 * to the frontend at `cable.spool_model.min_effective_radius_m`) -- the
 * piecewise model's open-ended final segment extrapolates unbounded past
 * the last calibration point, so this display-side mirror needs the same
 * floor the backend's actual torque conversion applies, or a chart sample
 * taken out there could divide by a near-zero/negative radius. Defaults to
 * 0 (no clamp) so existing callers that don't pass it are unaffected.
 */
export function createSpoolGeometry(r0, k, growthPoints, minREffM = 0) {
  const points = growthPoints && growthPoints.length ? growthPoints : null
  const segments = points ? buildGrowthSegments(r0, points) : null

  const rawREffAtTurnsDelta = (turnsDelta) => {
    const theta = Math.abs(turnsDelta * TURNS_TO_RADIANS)
    if (!segments) return r0 + k * theta
    const seg = findSegmentForTheta(theta, segments)
    return seg.rStart + seg.slope * (theta - seg.thetaStart)
  }

  return {
    lengthFromTurnsDelta(turnsDelta) {
      const theta = turnsDelta * TURNS_TO_RADIANS
      return segments ? lengthFromAnglePiecewise(theta, segments) : lengthFromAngle(theta, r0, k)
    },
    rEffAtTurnsDelta(turnsDelta) {
      return Math.max(rawREffAtTurnsDelta(turnsDelta), minREffM)
    },
  }
}
