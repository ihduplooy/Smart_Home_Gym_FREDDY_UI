import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Box, VStack, HStack, Text, Heading, Button, IconButton, Card, CardHeader, CardBody,
  Input, InputGroup, InputRightAddon, Select, Alert, AlertIcon, AlertDescription,
} from '@chakra-ui/react'
import { AddIcon, DeleteIcon } from '@chakra-ui/icons'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts'
import { previewTrainProfile } from '../../../api/train'
import { listTrainProfiles, saveTrainProfile, deleteTrainProfile } from '../../../utils/trainProfilesManager'
import { forceNFromMassKg, massKgFromForceN } from '../../../utils/cableGeometry'

// Resistance display unit preference (item 2, 5 Aug 2026, set in the Setup
// tab) -- force is always stored/evaluated in Newtons server-side
// (core/cable/train_profiles.py); these two convert at this component's own
// input/output boundary only, same "convert at the edge, keep the core
// unchanged" precedent as the Testing tab's Torque Limit unit selector.
// Every params key that carries a force value ends in "force_n" (force_n,
// start_force_n, end_force_n, peak_force_n) -- peak_pos_m is the only
// non-force param key, and is deliberately left untouched by both.
const isForceKey = (key) => key.endsWith('force_n')
const displayForceFromN = (n, resistanceUnitKg) => (resistanceUnitKg ? massKgFromForceN(n) : n)
const nFromDisplayForce = (v, resistanceUnitKg) => (resistanceUnitKg ? forceNFromMassKg(v) : v)

const SHAPES = [
  { value: 'constant', label: 'Constant' },
  { value: 'linear', label: 'Linear' },
  { value: 'bell', label: 'Bell' },
]

let nextId = 1

// Split-in-place needs a segment narrower than this to be rejected outright
// -- otherwise the two halves could round-trip to an invalid (end <= start)
// TrainSegment before the user gets a chance to hand-edit either boundary.
const MIN_SPLITTABLE_SPAN_M = 1e-6

function defaultSegment(startPosM, startForce, resistanceUnitKg) {
  const fallback = startForce ?? displayForceFromN(50, resistanceUnitKg)
  return {
    id: nextId++,
    start_pos_m: String(startPosM),
    end_pos_m: String(startPosM + 0.3),
    shape: 'constant',
    params: { force_n: String(fallback) },
  }
}

// The force a segment ends on, at its own end_pos_m -- used to auto-continue
// force the same way addSegment() already auto-continues position (spec:
// "calibration overhaul" item 4b). Constant has no start/end distinction
// (force_n is the whole segment); linear/bell both expose an explicit
// end_force_n. Returns null (falls back to defaultSegment's own hardcoded
// default) if the segment's own value isn't a finite number yet -- e.g. the
// user is mid-edit on a blank field.
function endForceOf(segment) {
  const key = segment.shape === 'constant' ? 'force_n' : 'end_force_n'
  const n = Number(segment.params[key])
  return Number.isFinite(n) ? n : null
}

function paramFields(shape, resistanceUnitKg) {
  const forceUnit = resistanceUnitKg ? 'kg' : 'N'
  if (shape === 'constant') return [{ key: 'force_n', label: 'Force', unit: forceUnit }]
  if (shape === 'linear') return [{ key: 'start_force_n', label: 'Start force', unit: forceUnit }, { key: 'end_force_n', label: 'End force', unit: forceUnit }]
  return [
    { key: 'peak_pos_m', label: 'Peak position', unit: 'm' },
    { key: 'peak_force_n', label: 'Peak force', unit: forceUnit },
    { key: 'start_force_n', label: 'Start force', unit: forceUnit },
    { key: 'end_force_n', label: 'End force', unit: forceUnit },
  ]
}

// startForce seeds the shape's start-of-segment force from the previous
// segment's end force (see endForceOf) so switching a segment's shape stays
// continuous with what comes before it, the same way addSegment() already
// keeps newly-added constant segments continuous. Falls back to the
// original hardcoded defaults when there's no previous segment (or its
// value isn't numeric yet).
function defaultParams(shape, startForce, resistanceUnitKg) {
  const start = String(startForce ?? displayForceFromN(0, resistanceUnitKg))
  const eighty = String(displayForceFromN(80, resistanceUnitKg))
  if (shape === 'constant') return { force_n: String(startForce ?? displayForceFromN(50, resistanceUnitKg)) }
  if (shape === 'linear') return { start_force_n: start, end_force_n: eighty }
  // end defaults to 0 -- the original "bell returns to zero at its far
  // edge" shape -- but can be raised independently (e.g. 3 -> 10 -> 4).
  return { peak_pos_m: '0.5', peak_force_n: eighty, start_force_n: start, end_force_n: String(displayForceFromN(0, resistanceUnitKg)) }
}

// Inverse of buildProfilePayload's segment shape: turns a saved/loaded
// {start_pos_m, end_pos_m, shape, params} (numeric, always Newtons) back
// into this editor's internal text-field segment state, with fresh local
// ids. Force-valued params are converted to the current display unit here
// (item 2) -- a profile saved while in kg mode and loaded back in N mode
// (or vice versa) should still show the SAME physical resistance, in
// whichever unit is currently selected, not the raw number as-saved.
function segmentsFromPayload(payloadSegments, resistanceUnitKg) {
  return payloadSegments.map((s) => ({
    id: nextId++,
    start_pos_m: String(s.start_pos_m),
    end_pos_m: String(s.end_pos_m),
    shape: s.shape,
    params: Object.fromEntries(
      Object.entries(s.params).map(([k, v]) => [k, String(isForceKey(k) ? displayForceFromN(v, resistanceUnitKg) : v)])
    ),
  }))
}

// Parses the editor's text-field segments into the {name, segments}
// TrainProfile.from_dict() shape, or throws with a human-readable message —
// validation itself stays server-side (core/cable/train_profiles.py); this
// only checks values are numeric enough to send. Force-valued params are
// converted from the current display unit back to Newtons here (item 2) --
// the wire format/server are always Newtons regardless of what's selected.
function buildProfilePayload(name, segments, resistanceUnitKg) {
  return {
    name,
    segments: segments.map((seg) => {
      const start = Number(seg.start_pos_m)
      const end = Number(seg.end_pos_m)
      if (!Number.isFinite(start) || !Number.isFinite(end)) {
        throw new Error('Every segment needs numeric start/end positions')
      }
      const params = {}
      for (const [key, value] of Object.entries(seg.params)) {
        const n = Number(value)
        if (!Number.isFinite(n)) throw new Error(`Segment parameter '${key}' must be a number`)
        params[key] = isForceKey(key) ? nFromDisplayForce(n, resistanceUnitKg) : n
      }
      return { start_pos_m: start, end_pos_m: end, shape: seg.shape, params }
    }),
  }
}

const TrainProfileEditor = ({ onStart, onApply, sessionRunning, busy, positionRangeM, resistanceUnitKg = false }) => {
  const [name, setName] = useState('my profile')
  const [segments, setSegments] = useState(() => [defaultSegment(0, null, resistanceUnitKg)])
  const [buildError, setBuildError] = useState(null)
  const [previewPoints, setPreviewPoints] = useState([])
  const [previewError, setPreviewError] = useState(null)

  const [savedProfiles, setSavedProfiles] = useState(() => listTrainProfiles())
  const [loadSelection, setLoadSelection] = useState('')
  const [saveMessage, setSaveMessage] = useState(null)
  const saveMessageTimer = useRef(null)

  const domain = useMemo(() => positionRangeM ?? [0, 1], [positionRangeM])
  // previewPoints comes back from the backend in Newtons (core/cable/
  // train_profiles.py never changes unit) -- converted to the current
  // display unit here, at the chart's own boundary, same as every other
  // force value in this component (item 2).
  const chartPoints = useMemo(
    () => previewPoints.map((p) => ({ ...p, force_n: displayForceFromN(p.force_n, resistanceUnitKg) })),
    [previewPoints, resistanceUnitKg]
  )

  const updateSegment = (id, patch) => {
    setSegments((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)))
  }
  const updateParam = (id, key, value) => {
    setSegments((prev) => prev.map((s) => (s.id === id ? { ...s, params: { ...s.params, [key]: value } } : s)))
  }
  const changeShape = (id, shape) => {
    setSegments((prev) => {
      const index = prev.findIndex((s) => s.id === id)
      const prevSegment = index > 0 ? prev[index - 1] : null
      const startForce = prevSegment ? endForceOf(prevSegment) : null
      return prev.map((s) => (s.id === id ? { ...s, shape, params: defaultParams(shape, startForce, resistanceUnitKg) } : s))
    })
  }
  const addSegment = () => {
    const prevSegment = segments.length ? segments[segments.length - 1] : null
    const lastEnd = prevSegment ? Number(prevSegment.end_pos_m) || 0 : 0
    const prevEndForce = prevSegment ? endForceOf(prevSegment) : null
    setSegments((prev) => [...prev, defaultSegment(lastEnd, prevEndForce, resistanceUnitKg)])
  }
  const removeSegment = (id) => setSegments((prev) => prev.filter((s) => s.id !== id))

  // Split-in-place (spec: "calibration overhaul" item 4a) -- splits one
  // segment into two at its numeric midpoint, rather than requiring the
  // whole profile to be deleted and rebuilt to insert a segment in the
  // middle. Deliberately no split-point modal/prompt: both halves start as
  // full copies of the original (fresh ids) and are immediately editable
  // like any other segment, so retyping the exact boundary happens right
  // there in the existing Start/End fields instead of through new UI
  // surface for a value that's trivially adjustable right after.
  const splitSegment = (id) => {
    setSegments((prev) => {
      const index = prev.findIndex((s) => s.id === id)
      if (index === -1) return prev
      const seg = prev[index]
      const start = Number(seg.start_pos_m)
      const end = Number(seg.end_pos_m)
      if (!Number.isFinite(start) || !Number.isFinite(end) || end - start < 2 * MIN_SPLITTABLE_SPAN_M) return prev
      const mid = (start + end) / 2

      // Bell's peak_pos_m generally won't sit validly inside BOTH halves
      // (TrainSegment requires start < peak < end) -- recenter each half's
      // own peak to its own sub-range midpoint so both halves pass
      // validation immediately; peak_force_n/start_force_n/end_force_n
      // carry over unchanged. Constant/linear have no positional params, so
      // a plain copy is enough for them.
      const paramsFor = (segStart, segEnd) => {
        if (seg.shape !== 'bell') return { ...seg.params }
        return { ...seg.params, peak_pos_m: String((segStart + segEnd) / 2) }
      }

      const first = { id: nextId++, start_pos_m: String(start), end_pos_m: String(mid), shape: seg.shape, params: paramsFor(start, mid) }
      const second = { id: nextId++, start_pos_m: String(mid), end_pos_m: String(end), shape: seg.shape, params: paramsFor(mid, end) }
      return [...prev.slice(0, index), first, second, ...prev.slice(index + 1)]
    })
  }

  // Debounced live preview against the draft (not-yet-applied) profile --
  // same evaluator (core/cable/train_profiles.py) the applied profile's own
  // Graph B "planned" curve reads from (spec §4: one source of truth).
  const debounceRef = useRef(null)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      try {
        const payload = buildProfilePayload(name, segments, resistanceUnitKg)
        setBuildError(null)
        const { points } = await previewTrainProfile(payload, domain, 150)
        setPreviewPoints(points)
        setPreviewError(null)
      } catch (e) {
        setPreviewPoints([])
        if (e.message?.startsWith('POST')) setPreviewError(e.message)
        else setBuildError(e.message)
      }
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [name, segments, domain, resistanceUnitKg])

  const handleStart = () => {
    try {
      const payload = buildProfilePayload(name, segments, resistanceUnitKg)
      setBuildError(null)
      onStart(payload)
    } catch (e) {
      setBuildError(e.message)
    }
  }

  const handleApply = () => {
    try {
      const payload = buildProfilePayload(name, segments, resistanceUnitKg)
      setBuildError(null)
      onApply(payload)
    } catch (e) {
      setBuildError(e.message)
    }
  }

  // Save/load named profiles (localStorage, utils/trainProfilesManager.js) --
  // requested so a segment layout built here can be reused across sessions
  // instead of re-typing it every time. Saved/loaded profiles are always
  // Newtons on disk (buildProfilePayload/segmentsFromPayload's own doc
  // comments) regardless of which unit was selected when saved.
  const handleSaveProfile = () => {
    try {
      const payload = buildProfilePayload(name, segments, resistanceUnitKg)
      setBuildError(null)
      const updated = saveTrainProfile(payload)
      setSavedProfiles(updated)
      setLoadSelection(payload.name)
      clearTimeout(saveMessageTimer.current)
      setSaveMessage(`Saved "${payload.name}"`)
      saveMessageTimer.current = setTimeout(() => setSaveMessage(null), 2500)
    } catch (e) {
      setBuildError(e.message)
    }
  }

  const handleLoadProfile = () => {
    const profile = savedProfiles.find((p) => p.name === loadSelection)
    if (!profile) return
    setName(profile.name)
    setSegments(segmentsFromPayload(profile.segments, resistanceUnitKg))
    setBuildError(null)
  }

  const handleDeleteProfile = () => {
    const updated = deleteTrainProfile(loadSelection)
    setSavedProfiles(updated)
    setLoadSelection('')
  }

  return (
    <Card bg="gray.800" variant="elevated">
      <CardHeader>
        <HStack justify="space-between">
          <Heading size="md" color="white">Resistance profile</Heading>
        </HStack>
      </CardHeader>
      <CardBody>
        <VStack align="stretch" spacing={4}>
          {(buildError || previewError) && (
            <Alert status="error" variant="left-accent">
              <AlertIcon />
              <AlertDescription>{buildError || previewError}</AlertDescription>
            </Alert>
          )}

          <HStack>
            <Text fontSize="xs" color="gray.400" minW="60px">Name</Text>
            <Input size="sm" value={name} onChange={(e) => setName(e.target.value)} maxW="240px" />
            <Button size="sm" onClick={handleSaveProfile} isDisabled={!name.trim()}>Save</Button>
            {saveMessage && <Text fontSize="xs" color="green.300">{saveMessage}</Text>}
          </HStack>

          <HStack>
            <Text fontSize="xs" color="gray.400" minW="60px">Saved</Text>
            <Select
              size="sm"
              maxW="240px"
              placeholder="Select a saved profile"
              value={loadSelection}
              onChange={(e) => setLoadSelection(e.target.value)}
            >
              {savedProfiles.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
            </Select>
            <Button size="sm" onClick={handleLoadProfile} isDisabled={!loadSelection}>Load</Button>
            <IconButton
              aria-label="Delete saved profile"
              icon={<DeleteIcon />}
              size="sm"
              variant="ghost"
              colorScheme="red"
              onClick={handleDeleteProfile}
              isDisabled={!loadSelection}
            />
          </HStack>

          <VStack align="stretch" spacing={3}>
            {segments.map((seg, idx) => (
              <Box key={seg.id} borderWidth="1px" borderColor="gray.700" borderRadius="md" p={3}>
                <HStack justify="space-between" mb={2}>
                  <Text fontSize="xs" color="gray.400">Segment {idx + 1}</Text>
                  <HStack spacing={1}>
                    <Button
                      size="xs"
                      variant="ghost"
                      onClick={() => splitSegment(seg.id)}
                      isDisabled={Number(seg.end_pos_m) - Number(seg.start_pos_m) < 2 * MIN_SPLITTABLE_SPAN_M}
                    >
                      Split
                    </Button>
                    <IconButton
                      aria-label="Remove segment"
                      icon={<DeleteIcon />}
                      size="xs"
                      variant="ghost"
                      colorScheme="red"
                      onClick={() => removeSegment(seg.id)}
                      isDisabled={segments.length <= 1}
                    />
                  </HStack>
                </HStack>
                <HStack spacing={3} wrap="wrap" align="flex-end">
                  <Box>
                    <Text fontSize="xs" color="gray.400" mb={1}>Start</Text>
                    <InputGroup size="sm" w="110px">
                      <Input
                        type="text"
                        inputMode="decimal"
                        fontFamily="mono"
                        value={seg.start_pos_m}
                        onChange={(e) => updateSegment(seg.id, { start_pos_m: e.target.value })}
                      />
                      <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                    </InputGroup>
                  </Box>
                  <Box>
                    <Text fontSize="xs" color="gray.400" mb={1}>End</Text>
                    <InputGroup size="sm" w="110px">
                      <Input
                        type="text"
                        inputMode="decimal"
                        fontFamily="mono"
                        value={seg.end_pos_m}
                        onChange={(e) => updateSegment(seg.id, { end_pos_m: e.target.value })}
                      />
                      <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                    </InputGroup>
                  </Box>
                  <Box>
                    <Text fontSize="xs" color="gray.400" mb={1}>Shape</Text>
                    <Select
                      size="sm"
                      w="120px"
                      value={seg.shape}
                      onChange={(e) => changeShape(seg.id, e.target.value)}
                    >
                      {SHAPES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                    </Select>
                  </Box>
                  {paramFields(seg.shape, resistanceUnitKg).map((f) => (
                    <Box key={f.key}>
                      <Text fontSize="xs" color="gray.400" mb={1}>{f.label}</Text>
                      <InputGroup size="sm" w="110px">
                        <Input
                          type="text"
                          inputMode="decimal"
                          fontFamily="mono"
                          value={seg.params[f.key] ?? ''}
                          onChange={(e) => updateParam(seg.id, f.key, e.target.value)}
                        />
                        <InputRightAddon px={2} fontSize="xs">{f.unit}</InputRightAddon>
                      </InputGroup>
                    </Box>
                  ))}
                </HStack>
              </Box>
            ))}
          </VStack>

          <Button size="sm" leftIcon={<AddIcon />} variant="outline" onClick={addSegment} alignSelf="flex-start">
            Add segment
          </Button>

          <Box>
            <Text fontSize="xs" color="gray.400" mb={1}>Live preview (draft, not yet applied)</Text>
            <Box h="160px" bg="gray.900" borderRadius="md" p={2}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartPoints} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis
                    dataKey="position_m"
                    type="number"
                    domain={domain}
                    stroke="#9CA3AF"
                    tick={{ fill: '#9CA3AF', fontSize: 10 }}
                    tickFormatter={(v) => `${v.toFixed(2)}`}
                  />
                  <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF', fontSize: 10 }} domain={[0, 'auto']} width={40} />
                  <RechartsTooltip
                    contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '6px', color: '#F9FAFB', fontSize: '11px' }}
                    formatter={(v) => [`${Number(v).toFixed(2)} ${resistanceUnitKg ? 'kg' : 'N'}`, 'force']}
                  />
                  <Line type="linear" dataKey="force_n" stroke="#F6E05E" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </Box>

          <HStack>
            {!sessionRunning ? (
              <Button size="sm" colorScheme="green" onClick={handleStart} isDisabled={busy}>
                Start Train session
              </Button>
            ) : (
              <Button size="sm" colorScheme="odrive" onClick={handleApply} isDisabled={busy}>
                Apply profile
              </Button>
            )}
          </HStack>
        </VStack>
      </CardBody>
    </Card>
  )
}

export default TrainProfileEditor
