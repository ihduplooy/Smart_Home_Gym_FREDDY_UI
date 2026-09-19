import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Box, VStack, HStack, Text, Heading, Button, ButtonGroup, IconButton, Card, CardHeader, CardBody,
  Input, InputGroup, InputRightAddon, Slider, SliderTrack, SliderFilledTrack, SliderThumb,
  Alert, AlertIcon, AlertDescription,
} from '@chakra-ui/react'
import { previewTrainProfile } from '../../../api/train'
import { forceNFromMassKg, massKgFromForceN } from '../../../utils/cableGeometry'
import { BAND_PRESETS } from '../../../utils/bandPresets'
import { useGymRepTracking } from '../../../hooks/useGymRepTracking'
import ConstantPanel from './panels/ConstantPanel'
import BandPanel from './panels/BandPanel'
import ConcentricEccentricPanel from './panels/ConcentricEccentricPanel'
import GymFooter from './GymFooter'

// GYM's own bespoke, single-resistance-type builder -- deliberately NOT the
// general multi-segment/multi-shape TrainProfileEditor with a narrower
// dropdown. One mode active at a time (Constant+Inertia, Band, or
// Concentric/Eccentric -- sub-phase 4), each with only the handful of fields
// that mode actually needs, always in kg (GYM ignores the device-wide N/kg
// `resistanceUnitKg` toggle on purpose -- simplicity was the explicit ask)
// -- but every field stays directly editable (typed, not just dragged), so
// "minimalistic" only means fewer things on screen, never less control.
// Renders under TrainSessionShell, same prop contract as TrainProfileEditor
// (see that shell's own doc comment) PLUS `liveExtra` (the running session's
// latest tick() extra dict, for Concentric/Eccentric's live phase/force
// readout), talking to the exact same "train" backend session/routes.
//
// onStart/onApply receive { profile } (Constant/Band -- an ordinary
// TrainProfile, same shape TrainProfileEditor sends) or { phaseForces }
// (Concentric/Eccentric -- bypasses position-based profile evaluation
// entirely, see core/cable/train_mode.py) -- never both; TrainSessionShell
// forwards whichever it gets straight to the API client unchanged. `cable`
// (also from TrainSessionShell) carries the live-adjustable settings this
// editor's sliders size themselves against (inertia_kg_max) -- configurable
// from GYM's own Settings sub-tab (GymSettingsPanel.jsx), not a hardcoded
// frontend constant, so the slider's range always matches what the backend
// will actually accept/clamp to.

// Fallback only, for the brief window before the first /api/train/status
// response lands (`cable` is undefined) -- mirrors board_constants.py's
// INERTIA_KG_MAX_DEFAULT, the same value a fresh CableState seeds itself
// with, so this is never visibly wrong, just briefly stale by a network
// round-trip.
const INERTIA_KG_MAX_FALLBACK = 10

// Floor for the Length slider -- a band ramping over less than a few cm isn't
// meaningfully adjustable by drag, and TrainSegment rejects a zero-width
// segment outright. The numeric Length field above it has no such floor (it
// still accepts anything > 0), this only bounds the slider's own drag range.
const LENGTH_SLIDER_MIN_M = 0.05

// Returns { profile } (Constant/Band) or { phaseForces } (Concentric/
// Eccentric) -- the two alternative shapes onStart/onApply forward straight
// to the backend (see this file's own top doc comment).
function buildGymPayload(mode, fields, positionRangeM) {
  const maxTravelM = positionRangeM[1]
  if (mode === 'constant') {
    const weightKg = Number(fields.weightKg)
    const inertiaKg = Number(fields.inertiaKg)
    if (!Number.isFinite(weightKg) || weightKg < 0) throw new Error('Weight must be a non-negative number')
    return {
      profile: {
        name: 'GYM constant',
        segments: [
          {
            start_pos_m: 0,
            end_pos_m: maxTravelM,
            shape: 'constant',
            params: { force_n: forceNFromMassKg(weightKg), inertia_kg: inertiaKg },
          },
        ],
      },
    }
  }

  if (mode === 'band') {
    // Ramps linearly from minKg to maxKg over [0, lengthM], then holds
    // steady at maxKg for the rest of the travel range -- "the band
    // increases linearly till a certain value, then it doesn't increase
    // linearly anymore" -- a real elastic band reaching full stretch, not
    // dropping back to zero resistance past that point. Modeled as a linear
    // segment (the ramp) plus, when the ramp doesn't already cover the whole
    // travel range, a trailing constant segment holding maxKg -- the same
    // two shapes TrainProfile already supports, just built automatically
    // rather than hand-assembled the way the Train tab's general editor
    // requires.
    const minKg = Number(fields.minKg)
    const maxKg = Number(fields.maxKg)
    const lengthM = Number(fields.lengthM)
    if (!Number.isFinite(minKg) || !Number.isFinite(maxKg) || !Number.isFinite(lengthM)) {
      throw new Error('Min, Max, and Length must all be numbers')
    }
    if (lengthM <= 0) throw new Error('Length must be greater than 0')

    const rampEndM = Math.min(lengthM, maxTravelM)
    const segments = [
      {
        start_pos_m: 0,
        end_pos_m: rampEndM,
        shape: 'linear',
        params: { start_force_n: forceNFromMassKg(minKg), end_force_n: forceNFromMassKg(maxKg) },
      },
    ]
    if (rampEndM < maxTravelM) {
      segments.push({
        start_pos_m: rampEndM,
        end_pos_m: maxTravelM,
        shape: 'constant',
        params: { force_n: forceNFromMassKg(maxKg) },
      })
    }
    return { profile: { name: 'GYM band', segments } }
  }

  // Concentric/eccentric (sub-phase 4): no position-based profile at all --
  // core/cable/train_mode.py's phase detector picks whichever of these two
  // forces is currently active by movement direction, blending smoothly
  // between them on a flip. Cap/shape validation (both non-negative, delta
  // within PHASE_FORCE_DELTA_MAX_N) happens server-side
  // (TrainMode._coerce_phase_forces) -- surfaced back through the existing
  // buildError path on Start/Apply, same as every other backend-only
  // validation in this editor (e.g. inertia_kg's own cap).
  const concentricKg = Number(fields.concentricKg)
  const eccentricKg = Number(fields.eccentricKg)
  if (!Number.isFinite(concentricKg) || concentricKg < 0) {
    throw new Error('Concentric force must be a non-negative number')
  }
  if (!Number.isFinite(eccentricKg) || eccentricKg < 0) {
    throw new Error('Eccentric force must be a non-negative number')
  }
  return {
    phaseForces: {
      concentric_force_n: forceNFromMassKg(concentricKg),
      eccentric_force_n: forceNFromMassKg(eccentricKg),
    },
  }
}

const TARGET_STRETCH_PCT_DEFAULT = '90'
const TARGET_REPS_DEFAULT = '8'

const GymProfileEditor = ({ onStart, onApply, sessionRunning, busy, positionRangeM, liveExtra, cable }) => {
  const inertiaKgMax = cable?.inertia_kg_max ?? INERTIA_KG_MAX_FALLBACK
  // GYM dashboard (sub-phase 5) tolerances/zones -- fallbacks mirror
  // board_constants.py's own *_DEFAULT values (the same ones a fresh
  // CableState seeds itself with), same "briefly stale by a network
  // round-trip, never visibly wrong" reasoning as inertiaKgMax above.
  // Configurable from GYM's Settings sub-tab, not hardcoded here.
  const forceToleranceFraction = cable?.constant_force_tolerance_fraction ?? 0.1
  const bandStretchTolerancePct = cable?.band_stretch_tolerance_pct ?? 10.0
  const repSpeedZones = {
    low: cable?.rep_speed_low_m_s ?? 0.15,
    high: cable?.rep_speed_high_m_s ?? 0.6,
    max: cable?.rep_speed_max_m_s ?? 1.0,
  }

  const [mode, setMode] = useState('constant')
  const [weightKg, setWeightKg] = useState('10')
  const [inertiaKg, setInertiaKg] = useState(0)
  const [minKg, setMinKg] = useState('2')
  const [maxKg, setMaxKg] = useState('8')
  const [lengthM, setLengthM] = useState('0.5')
  const [targetStretchPct, setTargetStretchPct] = useState(TARGET_STRETCH_PCT_DEFAULT)
  const [concentricKg, setConcentricKg] = useState('5')
  const [eccentricKg, setEccentricKg] = useState('3')
  const [targetReps, setTargetReps] = useState(TARGET_REPS_DEFAULT)

  const [buildError, setBuildError] = useState(null)
  const [previewError, setPreviewError] = useState(null)

  const domain = useMemo(() => positionRangeM ?? [0, 1], [positionRangeM])
  const fields = useMemo(
    () => ({ weightKg, inertiaKg, minKg, maxKg, lengthM, concentricKg, eccentricKg }),
    [weightKg, inertiaKg, minKg, maxKg, lengthM, concentricKg, eccentricKg]
  )
  // Length's slider drags across the actual calibrated travel range (domain's
  // own upper bound) rather than an arbitrary fixed max -- "the whole pull"
  // is a meaningful bound here in a way a hardcoded number wouldn't be.
  // Clamped into [min, max] so a value typed directly into the numeric field
  // above (which has no such ceiling) never throws the slider thumb off its
  // own track.
  const lengthSliderMaxM = Math.max(domain[1], LENGTH_SLIDER_MIN_M)
  const lengthSliderValue = Math.min(Math.max(Number(lengthM) || 0, LENGTH_SLIDER_MIN_M), lengthSliderMaxM)

  // Debounced validation against the current draft -- same builder/evaluator
  // (core/cable/train_profiles.py, via previewTrainProfile) TrainProfileEditor
  // uses, so a field that's fine client-side but rejected server-side (e.g. a
  // cap only TrainMode enforces) still surfaces before Start/Apply is even
  // clicked. The resulting curve itself is no longer rendered here (GYM's
  // dashboard panels below are the primary view once a set is running; the
  // pre-start position-vs-force preview chart this used to always show was
  // the "default view we're moving away from" per the dashboard redesign) --
  // this effect now runs purely for its error-surfacing side effect.
  const debounceRef = useRef(null)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      try {
        const payload = buildGymPayload(mode, fields, domain)
        setBuildError(null)
        if (payload.profile) {
          await previewTrainProfile(payload.profile, domain, 150)
        }
        setPreviewError(null)
      } catch (e) {
        if (e.message?.startsWith('POST')) setPreviewError(e.message)
        else setBuildError(e.message)
      }
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [mode, fields, domain])

  // Constant mode only -- classifies each tick's commanded force against
  // this mode's own live target+tolerance for the "time in range" ring/bar-
  // chart band (useGymRepTracking.js). Returns null (not applicable) for
  // every other mode/target, which the hook treats as "don't count this
  // tick toward time-in-range" rather than as "out of range".
  const targetForceN = forceNFromMassKg(Number(weightKg) || 0)
  const classifyInRange = useCallback(
    (forceN) => {
      if (mode !== 'constant' || targetForceN <= 0) return null
      return Math.abs(forceN - targetForceN) <= targetForceN * forceToleranceFraction
    },
    [mode, targetForceN, forceToleranceFraction]
  )
  const { repHistory, currentRepPeaks, speedMS, sessionSummary } = useGymRepTracking(liveExtra, sessionRunning, classifyInRange)

  const applyBandPreset = (preset) => {
    setMinKg(String(massKgFromForceN(preset.start_force_n)))
    setMaxKg(String(massKgFromForceN(preset.end_force_n)))
  }

  const handleStart = () => {
    try {
      const payload = buildGymPayload(mode, fields, domain)
      setBuildError(null)
      onStart(payload)
    } catch (e) {
      setBuildError(e.message)
    }
  }

  const handleApply = () => {
    try {
      const payload = buildGymPayload(mode, fields, domain)
      setBuildError(null)
      onApply(payload)
    } catch (e) {
      setBuildError(e.message)
    }
  }

  return (
    <VStack align="stretch" spacing={4}>
      <Card bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
        <CardHeader>
        <Heading size="md" color="paper.textPrimary">Resistance</Heading>
      </CardHeader>
      <CardBody>
        <VStack align="stretch" spacing={5}>
          {(buildError || previewError) && (
            <Alert status="error" variant="left-accent">
              <AlertIcon />
              <AlertDescription>{buildError || previewError}</AlertDescription>
            </Alert>
          )}

          <ButtonGroup size="sm" isAttached variant="outline" alignSelf="flex-start" flexWrap="wrap">
            <Button
              colorScheme={mode === 'constant' ? 'accent' : 'gray'}
              variant={mode === 'constant' ? 'solid' : 'outline'}
              onClick={() => setMode('constant')}
            >
              Constant
            </Button>
            <Button
              colorScheme={mode === 'band' ? 'accent' : 'gray'}
              variant={mode === 'band' ? 'solid' : 'outline'}
              onClick={() => setMode('band')}
            >
              Band
            </Button>
            <Button
              colorScheme={mode === 'concentric_eccentric' ? 'accent' : 'gray'}
              variant={mode === 'concentric_eccentric' ? 'solid' : 'outline'}
              onClick={() => setMode('concentric_eccentric')}
            >
              Concentric/Eccentric
            </Button>
          </ButtonGroup>

          {mode === 'constant' && (
            <VStack align="stretch" spacing={4}>
              <Box>
                <Text fontSize="xs" color="paper.textSecondary" mb={1}>Weight</Text>
                <InputGroup size="sm" maxW="160px">
                  <Input
                    type="text"
                    inputMode="decimal"
                    fontFamily="mono"
                    value={weightKg}
                    onChange={(e) => setWeightKg(e.target.value)}
                  />
                  <InputRightAddon px={2} fontSize="xs">kg</InputRightAddon>
                </InputGroup>
              </Box>
              <Box>
                <HStack justify="space-between" mb={1}>
                  <Text fontSize="xs" color="paper.textSecondary">Inertia</Text>
                  <Text fontSize="xs" fontFamily="mono" color="accent.600">{inertiaKg.toFixed(1)} kg</Text>
                </HStack>
                <Slider
                  min={0}
                  max={inertiaKgMax}
                  step={0.1}
                  value={Math.min(inertiaKg, inertiaKgMax)}
                  onChange={setInertiaKg}
                  colorScheme="accent"
                  maxW="320px"
                >
                  <SliderTrack bg="paper.bg"><SliderFilledTrack /></SliderTrack>
                  <SliderThumb boxSize={4} />
                </Slider>
                <Text fontSize="0.65rem" color="paper.textSecondary" mt={1}>
                  Adds a "heavy" feel on top of Weight, proportional to how fast you're
                  accelerating the cable -- 0 is a plain constant pull. Drag while pulling
                  to feel it out. Max range set in GYM's Settings sub-tab.
                </Text>
              </Box>
              <ConstantPanel
                speedMS={speedMS}
                currentRepPeaks={currentRepPeaks}
                repHistory={repHistory}
                targetForceN={targetForceN}
                forceToleranceFraction={forceToleranceFraction}
                repSpeedZones={repSpeedZones}
              />
            </VStack>
          )}

          {mode === 'band' && (
            <VStack align="stretch" spacing={4}>
              <Box>
                <Text fontSize="xs" color="paper.textSecondary" mb={1}>Preset</Text>
                <HStack spacing={1}>
                  {BAND_PRESETS.map((preset) => (
                    <IconButton
                      key={preset.name}
                      aria-label={`Apply ${preset.name} band preset`}
                      title={preset.name}
                      icon={<Box boxSize="14px" borderRadius="full" bg={preset.color} />}
                      size="sm"
                      variant="outline"
                      borderColor="paper.border"
                      onClick={() => applyBandPreset(preset)}
                    />
                  ))}
                </HStack>
              </Box>
              <HStack spacing={3} wrap="wrap">
                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Min</Text>
                  <InputGroup size="sm" w="110px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={minKg}
                      onChange={(e) => setMinKg(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">kg</InputRightAddon>
                  </InputGroup>
                </Box>
                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Max</Text>
                  <InputGroup size="sm" w="110px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={maxKg}
                      onChange={(e) => setMaxKg(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">kg</InputRightAddon>
                  </InputGroup>
                </Box>
                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Length</Text>
                  <InputGroup size="sm" w="110px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={lengthM}
                      onChange={(e) => setLengthM(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                  </InputGroup>
                </Box>
                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Target stretch</Text>
                  <InputGroup size="sm" w="110px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={targetStretchPct}
                      onChange={(e) => setTargetStretchPct(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">%</InputRightAddon>
                  </InputGroup>
                </Box>
              </HStack>
              <Box>
                <HStack justify="space-between" mb={1}>
                  <Text fontSize="xs" color="paper.textSecondary">Length</Text>
                  <Text fontSize="xs" fontFamily="mono" color="accent.600">{lengthSliderValue.toFixed(2)} m</Text>
                </HStack>
                <Slider
                  min={LENGTH_SLIDER_MIN_M}
                  max={lengthSliderMaxM}
                  step={0.01}
                  value={lengthSliderValue}
                  onChange={(v) => setLengthM(String(v))}
                  colorScheme="accent"
                  maxW="320px"
                >
                  <SliderTrack bg="paper.bg"><SliderFilledTrack /></SliderTrack>
                  <SliderThumb boxSize={4} />
                </Slider>
              </Box>
              <Text fontSize="0.65rem" color="paper.textSecondary">
                Resistance ramps from Min to Max over the first Length metres of cable
                travel, then holds steady at Max for the rest of the pull. Target stretch
                is a goal marker for the panel below (% of Length), separate from Length
                itself -- it doesn't change what resistance is actually applied.
              </Text>
              <BandPanel
                currentRepPeaks={currentRepPeaks}
                repHistory={repHistory}
                lengthM={Number(lengthM) || 0}
                targetStretchPct={Number(targetStretchPct) || 0}
                bandStretchTolerancePct={bandStretchTolerancePct}
              />
            </VStack>
          )}

          {mode === 'concentric_eccentric' && (
            <VStack align="stretch" spacing={4}>
              <HStack spacing={3} wrap="wrap">
                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Concentric</Text>
                  <InputGroup size="sm" w="110px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={concentricKg}
                      onChange={(e) => setConcentricKg(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">kg</InputRightAddon>
                  </InputGroup>
                </Box>
                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Eccentric</Text>
                  <InputGroup size="sm" w="110px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={eccentricKg}
                      onChange={(e) => setEccentricKg(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">kg</InputRightAddon>
                  </InputGroup>
                </Box>
              </HStack>
              <Text fontSize="0.65rem" color="paper.textSecondary">
                Resistance always opposes whichever direction you're currently moving --
                Concentric while pulling out, Eccentric while lowering back. Switches
                smoothly between the two, not instantly, on a real direction change.
              </Text>
              <ConcentricEccentricPanel liveExtra={liveExtra} speedMS={speedMS} repHistory={repHistory} />
            </VStack>
          )}

          <HStack>
            {!sessionRunning ? (
              <Button size="sm" colorScheme="green" onClick={handleStart} isDisabled={busy}>
                Start GYM session
              </Button>
            ) : (
              <Button size="sm" colorScheme="accent" onClick={handleApply} isDisabled={busy}>
                Apply
              </Button>
            )}
          </HStack>
        </VStack>
      </CardBody>
    </Card>
      <GymFooter
        repHistory={repHistory}
        currentRepPeaks={currentRepPeaks}
        sessionSummary={sessionSummary}
        targetReps={Number(targetReps) || 0}
        onTargetRepsChange={setTargetReps}
      />
    </VStack>
  )
}

export default GymProfileEditor
