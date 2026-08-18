import { useEffect, useRef, useState } from 'react'
import {
  Box, VStack, HStack, Text, Badge, Button, IconButton,
  SimpleGrid, Stat, StatLabel, StatNumber, Input, InputGroup, InputRightAddon, Select,
  Alert, AlertIcon, AlertDescription,
} from '@chakra-ui/react'
import { X } from 'lucide-react'
import { startControlSession, setControlTarget, stopControlSession } from '../../../api/control'
import { turnsDeltaFromLength, torqueFromForce, rawTorqueNmForCorrected, GRAVITY_M_S2 } from '../../../utils/cableGeometry'
import { DEFAULT_ACCEL_DECEL } from './TestingTab'

// Runs the same position-mode move Configure Move uses (Control tab's own
// `mode: "position"` ControlSession, see TestingTab.jsx's header comment),
// just a client-driven sequence of them: no known weight (not a calibration
// workflow), a torque limit per move instead of one shared value, and a
// repeat count. There's no backend "move finished" signal (position moves
// are fire-and-forget trapezoidal trajectories -- confirmed nothing in
// ControlSession/PositionMode/OdriveHardware exposes trajectory_done), so
// "settled" is inferred client-side from telemetry: position within
// tolerance of the commanded target AND velocity near zero, sustained for a
// few consecutive polls (debounces normal trajectory-following noise before
// the move actually stops). A timeout guards against a move that never
// settles (e.g. torque-limited against a real load) hanging the sequence
// forever.
//
// The position tolerance is user-adjustable (Settle tolerance, below) --
// tight tolerances can leave a real (non-mock) rig chasing the last
// fraction of a turn for a while before every move is allowed to advance,
// so a looser value trades precision for a faster-cycling sequence. The
// velocity threshold isn't exposed separately; it scales with the same
// input (at the ratio the two were originally fixed at) so the one field
// loosens both halves of "settled" together.
const DEFAULT_SETTLE_TOLERANCE_TURNS = 0.02
const VELOCITY_TOLERANCE_RATIO = 1.5 // velocity threshold = position tolerance * this
const SETTLE_POLLS_REQUIRED = 3
const MOVE_TIMEOUT_MS = 20000

const makeMove = (overrides = {}) => ({
  distanceText: '0.2',
  unit: 'm', // 'm' | 'turns'
  velocityText: '0.5',
  torqueLimitText: '', // blank = unlimited
  torqueLimitUnit: 'Nm', // 'Nm' | 'N' | 'kg'
  ...overrides,
})

// Mirrors TestingTab.jsx's own moveDistanceTurnsEstimate/torqueLimitNm/
// moveValid/torqueLimitValid, just parameterized per-move instead of over
// this component's own single set of fields.
function evaluateMove(move, cable, rEffAtCurrent) {
  const r0 = cable?.r0
  const k = cable?.k ?? 0
  const distanceNumber = Number(move.distanceText)
  const velocityNumber = Number(move.velocityText)

  let distanceTurnsEstimate = null
  if (move.unit === 'm' && r0 != null && Number.isFinite(distanceNumber)) {
    try {
      const magnitude = turnsDeltaFromLength(Math.abs(distanceNumber), r0, k)
      distanceTurnsEstimate = Math.sign(distanceNumber) * magnitude
    } catch {
      distanceTurnsEstimate = null
    }
  }

  const moveOk =
    move.distanceText !== '' && Number.isFinite(distanceNumber) &&
    (move.unit === 'turns' || distanceTurnsEstimate != null) &&
    move.velocityText !== '' && Number.isFinite(velocityNumber) && velocityNumber > 0

  const torqueLimitNumber = move.torqueLimitText === '' ? null : Number(move.torqueLimitText)
  let torqueLimitNm = null
  if (torqueLimitNumber != null && Number.isFinite(torqueLimitNumber)) {
    if (move.torqueLimitUnit === 'Nm') {
      torqueLimitNm = torqueLimitNumber
    } else if (rEffAtCurrent != null) {
      const forceN = move.torqueLimitUnit === 'kg' ? torqueLimitNumber * GRAVITY_M_S2 : torqueLimitNumber
      const realTorqueNm = torqueFromForce(forceN, rEffAtCurrent)
      torqueLimitNm = rawTorqueNmForCorrected(realTorqueNm, cable?.torque_model?.scale ?? 1.0, cable?.torque_model?.offset ?? 0.0)
    }
  }
  const torqueOk =
    move.torqueLimitText === '' ||
    (Number.isFinite(torqueLimitNumber) && torqueLimitNumber >= 0 && (move.torqueLimitUnit === 'Nm' || torqueLimitNm != null))

  return { distanceNumber, distanceTurnsEstimate, torqueLimitNm, valid: moveOk && torqueOk }
}

function buildTargetForMove(move, cable, rEffAtCurrent) {
  const { distanceNumber, distanceTurnsEstimate, torqueLimitNm } = evaluateMove(move, cable, rEffAtCurrent)
  return {
    position: move.unit === 'm' ? distanceTurnsEstimate : distanceNumber,
    move_velocity: Number(move.velocityText),
    accel_decel: DEFAULT_ACCEL_DECEL,
    torque_limit: move.torqueLimitText === '' ? null : torqueLimitNm,
  }
}

const RepetitiveTesting = ({ status, cable, running, anotherModeRunning, isHomed, rEffAtCurrent, latestSample }) => {
  const [moves, setMoves] = useState([makeMove({ distanceText: '0.2' }), makeMove({ distanceText: '-0.2' })])
  const [repsText, setRepsText] = useState('5')
  const [settleToleranceText, setSettleToleranceText] = useState(String(DEFAULT_SETTLE_TOLERANCE_TURNS))
  const [runPhase, setRunPhase] = useState('idle') // 'idle' | 'running' | 'paused'
  const [currentMoveIndex, setCurrentMoveIndex] = useState(0)
  const [currentRep, setCurrentRep] = useState(0)
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)

  const settlePollCountRef = useRef(0)
  const moveStartedAtRef = useRef(null)

  const repsNumber = Number(repsText)
  const repsValid = repsText !== '' && Number.isInteger(repsNumber) && repsNumber >= 1
  const settleToleranceNumber = Number(settleToleranceText)
  const settleToleranceValid = settleToleranceText !== '' && Number.isFinite(settleToleranceNumber) && settleToleranceNumber > 0
  const moveEvaluations = moves.map((m) => evaluateMove(m, cable, rEffAtCurrent))
  const allMovesValid = moves.length >= 1 && moveEvaluations.every((e) => e.valid)
  const sequenceValid = allMovesValid && repsValid && settleToleranceValid
  const editable = runPhase === 'idle'

  const resetRunState = () => {
    setRunPhase('idle')
    setCurrentMoveIndex(0)
    setCurrentRep(0)
    settlePollCountRef.current = 0
    moveStartedAtRef.current = null
  }

  const handleAddMove = () => setMoves((prev) => [...prev, makeMove()])
  const handleRemoveMove = (index) => setMoves((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== index) : prev))
  const handleMoveFieldChange = (index, field, value) =>
    setMoves((prev) => prev.map((m, i) => (i === index ? { ...m, [field]: value } : m)))

  const sendMove = async (move) => {
    const target = buildTargetForMove(move, cable, rEffAtCurrent)
    if (running) {
      await setControlTarget(target)
    } else {
      await startControlSession('position', target)
    }
    moveStartedAtRef.current = Date.now()
    settlePollCountRef.current = 0
  }

  const handleStartSequence = async () => {
    if (!sequenceValid) {
      setActionError('Fill in every move (Distance and Velocity, and a valid Torque Limit if set), a whole-number Repetitions count of at least 1, and a Settle tolerance above 0')
      return
    }
    setActionError(null)
    setBusy(true)
    try {
      setCurrentRep(1)
      setCurrentMoveIndex(0)
      await sendMove(moves[0])
      setRunPhase('running')
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const advance = async () => {
    try {
      const nextMoveIndex = currentMoveIndex + 1
      if (nextMoveIndex < moves.length) {
        await sendMove(moves[nextMoveIndex])
        setCurrentMoveIndex(nextMoveIndex)
        return
      }
      const nextRep = currentRep + 1
      if (nextRep > repsNumber) {
        await stopControlSession()
        resetRunState()
        return
      }
      await sendMove(moves[0])
      setCurrentRep(nextRep)
      setCurrentMoveIndex(0)
    } catch (e) {
      setActionError(e.message)
      resetRunState()
    }
  }

  const handlePause = async () => {
    setActionError(null)
    setBusy(true)
    try {
      await stopControlSession()
      setRunPhase('paused')
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleResume = async () => {
    setActionError(null)
    setBusy(true)
    try {
      await sendMove(moves[currentMoveIndex])
      setRunPhase('running')
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleStop = async () => {
    setActionError(null)
    setBusy(true)
    try {
      await stopControlSession()
    } catch (e) {
      setActionError(e.message)
    } finally {
      resetRunState()
      setBusy(false)
    }
  }

  // Settle detection: on every new telemetry sample, check the live sample
  // against the target this component itself last commanded. Advancing only
  // from here (rather than off a timer) keeps it synced to real telemetry
  // instead of guessing move duration up front.
  //
  // Also doubles as the "stopped externally" safety net (top-level STOP,
  // another tab, a hardware auto-stop) -- checked against `status` directly
  // here, gated on a NEW sample having arrived, rather than off the
  // `running` prop in its own effect keyed on [running, busy]. That
  // approach shipped first and had a real race: `running` only updates on
  // the PARENT's own ~150ms poll cycle, which lags just behind our own
  // start/resume call finishing, so the effect fired inside that gap and
  // misread our own just-started session as an external stop (caught via
  // an actual browser run, not by lint/build). Gating on a fresh sample
  // instead guarantees `status` is at least as new as the render that
  // caused it, so it can only be evaluated once truly caught up.
  useEffect(() => {
    if (runPhase !== 'running') return
    const sample = status?.latest_sample
    if (!sample) return

    if (!status?.running || status?.mode !== 'position') {
      setActionError('Position session was stopped externally — sequence halted.')
      resetRunState()
      return
    }

    const target = status?.target
    if (!target || typeof target !== 'object') return

    const positionOk = Math.abs(sample.position - target.position) <= settleToleranceNumber
    const velocityOk = Math.abs(sample.velocity) <= settleToleranceNumber * VELOCITY_TOLERANCE_RATIO
    settlePollCountRef.current = positionOk && velocityOk ? settlePollCountRef.current + 1 : 0

    if (settlePollCountRef.current >= SETTLE_POLLS_REQUIRED) {
      advance()
      return
    }
    const timedOut = moveStartedAtRef.current != null && Date.now() - moveStartedAtRef.current > MOVE_TIMEOUT_MS
    if (timedOut) {
      setActionError(`Move ${currentMoveIndex + 1} didn't settle within ${MOVE_TIMEOUT_MS / 1000}s — sequence stopped.`)
      stopControlSession().catch(() => {})
      resetRunState()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.latest_sample?.t])

  useEffect(() => {
    if (runPhase === 'idle' || !status?.errored) return
    setActionError(status.error_message || 'Session auto-stopped')
    resetRunState()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.errored])

  return (
    <VStack align="stretch" spacing={4}>
      {actionError && (
        <Alert status="error" variant="left-accent">
          <AlertIcon /><AlertDescription>{actionError}</AlertDescription>
        </Alert>
      )}

      <VStack align="stretch" spacing={3}>
        {moves.map((move, index) => {
          const evaluation = moveEvaluations[index]
          return (
            <HStack key={index} spacing={4} wrap="wrap" bg="gray.900" p={2} borderRadius="md">
              <Text fontSize="xs" color="gray.400" w="50px">Move {index + 1}</Text>

              <Box>
                <Text fontSize="xs" color="gray.400" mb={1}>Move Distance</Text>
                <HStack spacing={1}>
                  <InputGroup size="sm" w="110px">
                    <Input
                      type="text" inputMode="decimal" fontFamily="mono"
                      value={move.distanceText}
                      isDisabled={!editable}
                      onChange={(e) => handleMoveFieldChange(index, 'distanceText', e.target.value)}
                    />
                  </InputGroup>
                  <Select
                    size="sm" w="80px" value={move.unit} isDisabled={!editable}
                    onChange={(e) => handleMoveFieldChange(index, 'unit', e.target.value)}
                  >
                    <option value="m">m</option>
                    <option value="turns">turns</option>
                  </Select>
                </HStack>
                <Text fontSize="0.65rem" color="gray.500" mt={0.5}>
                  relative to current position
                  {move.unit === 'm' && (
                    evaluation.distanceTurnsEstimate != null
                      ? ` (≈ ${evaluation.distanceTurnsEstimate.toFixed(3)} turns)`
                      : cable?.r0 == null ? ' (loading cable calibration…)' : ' (out of range for current calibration)'
                  )}
                </Text>
              </Box>

              <Box>
                <Text fontSize="xs" color="gray.400" mb={1}>Move Velocity</Text>
                <InputGroup size="sm" w="140px">
                  <Input
                    type="text" inputMode="decimal" fontFamily="mono"
                    value={move.velocityText}
                    isDisabled={!editable}
                    onChange={(e) => handleMoveFieldChange(index, 'velocityText', e.target.value)}
                  />
                  <InputRightAddon px={2} fontSize="xs">turns/s</InputRightAddon>
                </InputGroup>
              </Box>

              <Box>
                <Text fontSize="xs" color="gray.400" mb={1}>Torque Limit</Text>
                <HStack spacing={1}>
                  <InputGroup size="sm" w="110px">
                    <Input
                      type="text" inputMode="decimal" fontFamily="mono" placeholder="unlimited"
                      value={move.torqueLimitText}
                      isDisabled={!editable}
                      onChange={(e) => handleMoveFieldChange(index, 'torqueLimitText', e.target.value)}
                    />
                  </InputGroup>
                  <Select
                    size="sm" w="80px" value={move.torqueLimitUnit} isDisabled={!editable}
                    onChange={(e) => handleMoveFieldChange(index, 'torqueLimitUnit', e.target.value)}
                  >
                    <option value="Nm">Nm</option>
                    <option value="N">N</option>
                    <option value="kg">kg</option>
                  </Select>
                </HStack>
                {move.torqueLimitText !== '' && move.torqueLimitUnit !== 'Nm' && (
                  <Text fontSize="0.65rem" color="gray.500" mt={0.5}>
                    {evaluation.torqueLimitNm != null ? `≈ ${evaluation.torqueLimitNm.toFixed(4)} Nm` : 'loading cable calibration…'}
                  </Text>
                )}
              </Box>

              <IconButton
                aria-label="Remove move"
                size="sm"
                variant="outline"
                colorScheme="red"
                alignSelf="flex-end"
                icon={<X size={14} />}
                isDisabled={!editable || moves.length <= 1}
                onClick={() => handleRemoveMove(index)}
              />
            </HStack>
          )
        })}
        <Button size="sm" variant="outline" alignSelf="flex-start" isDisabled={!editable} onClick={handleAddMove}>
          + Add move
        </Button>
      </VStack>

      <HStack spacing={4} wrap="wrap" align="flex-end">
        <Box>
          <Text fontSize="xs" color="gray.400" mb={1}>Repetitions</Text>
          <InputGroup size="sm" w="100px">
            <Input
              type="text" inputMode="numeric" fontFamily="mono"
              value={repsText}
              isDisabled={!editable}
              onChange={(e) => setRepsText(e.target.value)}
            />
          </InputGroup>
        </Box>

        <Box>
          <Text fontSize="xs" color="gray.400" mb={1}>Settle tolerance</Text>
          <InputGroup size="sm" w="120px">
            <Input
              type="text" inputMode="decimal" fontFamily="mono"
              value={settleToleranceText}
              isDisabled={!editable}
              onChange={(e) => setSettleToleranceText(e.target.value)}
            />
            <InputRightAddon px={2} fontSize="xs">turns</InputRightAddon>
          </InputGroup>
          <Text fontSize="0.65rem" color="gray.500" mt={0.5}>
            how close counts as "arrived" — looser advances sooner
          </Text>
        </Box>

        <HStack spacing={2}>
          {runPhase === 'idle' && (
            <Button size="sm" colorScheme="green" onClick={handleStartSequence} isDisabled={!sequenceValid || busy || anotherModeRunning}>
              Start
            </Button>
          )}
          {runPhase === 'running' && (
            <Button size="sm" colorScheme="yellow" onClick={handlePause} isDisabled={busy}>
              Pause
            </Button>
          )}
          {runPhase === 'paused' && (
            <Button size="sm" colorScheme="green" onClick={handleResume} isDisabled={busy}>
              Resume
            </Button>
          )}
          {runPhase !== 'idle' && (
            <Button size="sm" colorScheme="red" onClick={handleStop} isDisabled={busy}>
              Stop
            </Button>
          )}
        </HStack>

        <HStack spacing={2}>
          {runPhase !== 'idle' && (
            <Badge colorScheme={runPhase === 'paused' ? 'yellow' : 'green'} variant="solid">
              {runPhase === 'paused' ? 'Paused' : 'Running'}
            </Badge>
          )}
          <Text fontSize="sm" color="gray.300" fontFamily="mono">
            {runPhase === 'idle' ? 'Not running' : `Repetition ${currentRep} / ${repsNumber} — Move ${currentMoveIndex + 1} / ${moves.length}`}
          </Text>
        </HStack>
      </HStack>

      {!isHomed && (
        <Alert status="info" variant="left-accent">
          <AlertIcon /><AlertDescription>Home the cable first (Setup tab) to enable r_eff/force conversions here.</AlertDescription>
        </Alert>
      )}

      <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
        <Stat>
          <StatLabel color="gray.300">Position</StatLabel>
          <StatNumber color="odrive.300" fontSize="xl">{latestSample?.position_m != null ? latestSample.position_m.toFixed(4) : '—'}</StatNumber>
          <Text fontSize="xs" color="gray.400">m, from home</Text>
        </Stat>
        <Stat>
          <StatLabel color="gray.300">Measured torque</StatLabel>
          <StatNumber color="odrive.300" fontSize="xl">{latestSample?.corrected_torque_nm != null ? Math.abs(latestSample.corrected_torque_nm).toFixed(3) : '—'}</StatNumber>
          <Text fontSize="xs" color="gray.400">Nm, calibrated</Text>
        </Stat>
        <Stat>
          <StatLabel color="gray.300">Phase current</StatLabel>
          <StatNumber color="odrive.300" fontSize="xl">{status?.latest_sample?.current_iq != null ? status.latest_sample.current_iq.toFixed(3) : '—'}</StatNumber>
          <Text fontSize="xs" color="gray.400">A (Iq_measured)</Text>
        </Stat>
        <Stat>
          <StatLabel color="gray.300">Measured force</StatLabel>
          <StatNumber color="odrive.300" fontSize="xl">{latestSample?.force_est_n != null ? Math.abs(latestSample.force_est_n).toFixed(2) : '—'}</StatNumber>
          <Text fontSize="xs" color="gray.400">N</Text>
        </Stat>
      </SimpleGrid>
    </VStack>
  )
}

export default RepetitiveTesting
