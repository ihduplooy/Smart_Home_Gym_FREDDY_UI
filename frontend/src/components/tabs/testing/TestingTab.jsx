import { useMemo, useState } from 'react'
import {
  Box, VStack, HStack, Text, Heading, Badge, Button, Card, CardHeader, CardBody,
  SimpleGrid, Stat, StatLabel, StatNumber, Input, InputGroup, InputRightAddon, Select,
  Alert, AlertIcon, AlertTitle, AlertDescription, List, ListItem,
} from '@chakra-ui/react'
import { useTestingTelemetry } from '../../../hooks/useTestingTelemetry'
import { startControlSession, setControlTarget, stopControlSession } from '../../../api/control'
import { recordTorqueCalibrationPoint, clearTorqueCalibration } from '../../../api/exercise'
import {
  turnsDeltaFromLength, createSpoolGeometry, torqueFromForce, rawTorqueNmForCorrected, GRAVITY_M_S2,
} from '../../../utils/cableGeometry'
import TelemetryTimeSeriesChart from '../../shared/TelemetryTimeSeriesChart'
import TorqueModelDiagnostics from './TorqueModelDiagnostics'

// Item 2: rebuilt on Control tab's own `mode: "position"` session (see
// useTestingTelemetry.js's header comment) instead of a dedicated
// "experiment" ControlSession mode -- change a field, hit Update, see the
// effect immediately, keep adjusting without stopping. Known Weight/Move
// Distance(+unit)/Move Velocity/Torque Limit(+unit) mirror Control tab's own
// Position-mode fields exactly (frontend/src/components/tabs/control/ControlTab.jsx),
// plus the calibration-specific additions (items 6/7) below the telemetry.
const CHART_LINES = [
  { key: 'position_m', label: 'Position (actual)', color: '#63B3ED', unit: 'm', defaultOn: true, side: 'left' },
  { key: 'target_position_m', label: 'Target position', color: '#63B3ED', unit: 'm', defaultOn: true, side: 'left', axisKey: 'position_m', dashed: true },
  { key: 'corrected_torque_nm', label: 'Torque (calibrated)', color: '#F6AD55', unit: 'Nm', defaultOn: true, side: 'right' },
  { key: 'torque_est_nm', label: 'Torque (raw estimate)', color: '#ED8936', unit: 'Nm', defaultOn: false, side: 'right' },
  { key: 'force_est_n', label: 'Force (calculated)', color: '#4FD1C5', unit: 'N', defaultOn: true, side: 'right' },
  { key: 'current_iq_a', label: 'Phase current', color: '#68D391', unit: 'A', defaultOn: false, side: 'right' },
  { key: 'bus_voltage_v', label: 'Bus voltage', color: '#B794F4', unit: 'V', defaultOn: false, side: 'right' },
  { key: 'estimated_power_w', label: 'Estimated power', color: '#FC8181', unit: 'W', defaultOn: false, side: 'right' },
]

// Not user-facing (item 2: "we don't need acceleration or deceleration
// controls for now") -- matches board_constants.TRAP_TRAJ_ACCEL_LIMIT, the
// same default ExerciseMode._apply_move/PositionMode fall back to.
const DEFAULT_ACCEL_DECEL = 1.0

const TestingTab = ({ isActive = true }) => {
  const { status, cable, series, connected } = useTestingTelemetry(isActive)

  const [knownWeightText, setKnownWeightText] = useState('5')
  const [moveDistanceText, setMoveDistanceText] = useState('0.2')
  const [moveUnit, setMoveUnit] = useState('m') // 'm' | 'turns'
  const [moveVelocityText, setMoveVelocityText] = useState('0.5')
  const [torqueLimitText, setTorqueLimitText] = useState('') // blank = unlimited
  const [torqueLimitUnit, setTorqueLimitUnit] = useState('Nm') // 'Nm' | 'N' | 'kg'
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)

  const [calibError, setCalibError] = useState(null)
  const [calibBusy, setCalibBusy] = useState(false)

  const isHomed = cable?.is_homed ?? false
  const backendErrors = status?.errors ?? []
  const running = Boolean(status?.running && status?.mode === 'position')
  const anotherModeRunning = Boolean(status?.running && status?.mode !== 'position')

  const r0 = cable?.r0
  const k = cable?.k ?? 0
  const currentPositionTurns = status?.latest_sample?.position

  // Effective spool radius AT THE CURRENT POSITION, same growth-aware
  // conversion useTestingTelemetry.js uses for the chart -- needed here to
  // convert a Torque Limit typed in N/kg into the Nm value actually sent.
  const rEffAtCurrent = useMemo(() => {
    if (r0 == null || cable?.home_turns == null || currentPositionTurns == null) return null
    const growthPoints = (cable.spool_model?.growth_points ?? []).map((p) => [p.turns_from_home, p.length_m])
    const minREffM = cable.spool_model?.min_effective_radius_m ?? 0
    const geometry = createSpoolGeometry(r0, k, growthPoints, minREffM)
    return geometry.rEffAtTurnsDelta(currentPositionTurns - cable.home_turns)
  }, [r0, k, cable?.home_turns, cable?.spool_model, currentPositionTurns])

  const knownWeightNumber = Number(knownWeightText)
  const knownWeightValid = knownWeightText !== '' && Number.isFinite(knownWeightNumber) && knownWeightNumber >= 0
  const expectedForceN = knownWeightValid ? knownWeightNumber * GRAVITY_M_S2 : null

  const moveDistanceNumber = Number(moveDistanceText)
  const moveVelocityNumber = Number(moveVelocityText)
  // Converts a signed cable-length input to signed turns -- same convention
  // ControlTab.jsx's own Position-mode m/turns toggle already uses.
  const moveDistanceTurnsEstimate = useMemo(() => {
    if (moveUnit !== 'm' || r0 == null || !Number.isFinite(moveDistanceNumber)) return null
    try {
      const magnitude = turnsDeltaFromLength(Math.abs(moveDistanceNumber), r0, k)
      return Math.sign(moveDistanceNumber) * magnitude
    } catch {
      return null
    }
  }, [moveUnit, r0, k, moveDistanceNumber])

  const torqueLimitNumber = torqueLimitText === '' ? null : Number(torqueLimitText)
  // Torque Limit's 3-way unit select (item 2): Nm direct; N/kg convert via
  // the effective radius at the current position, THEN through the torque
  // calibration's inverse correction (items 6/7) so the raw Nm value
  // actually sent produces the intended real-world torque limit.
  const torqueLimitNm = useMemo(() => {
    if (torqueLimitNumber == null || !Number.isFinite(torqueLimitNumber)) return null
    if (torqueLimitUnit === 'Nm') return torqueLimitNumber
    if (rEffAtCurrent == null) return null
    const forceN = torqueLimitUnit === 'kg' ? torqueLimitNumber * GRAVITY_M_S2 : torqueLimitNumber
    const realTorqueNm = torqueFromForce(forceN, rEffAtCurrent)
    return rawTorqueNmForCorrected(realTorqueNm, cable?.torque_model?.scale ?? 1.0, cable?.torque_model?.offset ?? 0.0)
  }, [torqueLimitNumber, torqueLimitUnit, rEffAtCurrent, cable?.torque_model])

  const moveValid =
    moveDistanceText !== '' && Number.isFinite(moveDistanceNumber) &&
    (moveUnit === 'turns' || moveDistanceTurnsEstimate != null) &&
    moveVelocityText !== '' && Number.isFinite(moveVelocityNumber) && moveVelocityNumber > 0
  const torqueLimitValid =
    torqueLimitText === '' ||
    (Number.isFinite(torqueLimitNumber) && torqueLimitNumber >= 0 && (torqueLimitUnit === 'Nm' || torqueLimitNm != null))
  const targetValid = moveValid && torqueLimitValid

  const buildTarget = () => ({
    position: moveUnit === 'm' ? moveDistanceTurnsEstimate : moveDistanceNumber,
    move_velocity: moveVelocityNumber,
    accel_decel: DEFAULT_ACCEL_DECEL,
    torque_limit: torqueLimitText === '' ? null : torqueLimitNm,
  })

  const handleStart = async () => {
    if (!targetValid) {
      setActionError('Fill in Move Distance and Move Velocity (and a valid Torque Limit, if set)')
      return
    }
    setActionError(null)
    setBusy(true)
    try {
      await startControlSession('position', buildTarget())
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleRetarget = async () => {
    if (!targetValid) {
      setActionError('Fill in Move Distance and Move Velocity (and a valid Torque Limit, if set)')
      return
    }
    setActionError(null)
    try {
      await setControlTarget(buildTarget())
    } catch (e) {
      setActionError(e.message)
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
      setBusy(false)
    }
  }

  const handleRecordPoint = async () => {
    if (!knownWeightValid) {
      setCalibError('Enter a valid known weight first')
      return
    }
    setCalibError(null)
    setCalibBusy(true)
    try {
      await recordTorqueCalibrationPoint(knownWeightNumber)
    } catch (e) {
      setCalibError(e.message)
    } finally {
      setCalibBusy(false)
    }
  }

  const handleClearCalibration = async () => {
    setCalibError(null)
    setCalibBusy(true)
    try {
      await clearTorqueCalibration()
    } catch (e) {
      setCalibError(e.message)
    } finally {
      setCalibBusy(false)
    }
  }

  const latestSample = series.length ? series[series.length - 1] : null
  const calibrationPoints = cable?.torque_model?.points ?? []

  return (
    <Box p={4} h="100%" maxW="1400px" mx="auto" overflow="auto">
      <VStack spacing={4} align="stretch">
        {actionError && (
          <Alert status="error" variant="left-accent">
            <AlertIcon /><AlertDescription>{actionError}</AlertDescription>
          </Alert>
        )}
        {status?.errored && (
          <Alert status="error" variant="left-accent">
            <AlertIcon />
            <Box>
              <AlertTitle>Session auto-stopped</AlertTitle>
              <AlertDescription>{status.error_message}</AlertDescription>
            </Box>
          </Alert>
        )}
        {backendErrors.length > 0 && (
          <Alert status="warning" variant="left-accent">
            <AlertIcon />
            <Box>
              <AlertTitle>Hardware errors</AlertTitle>
              <List fontSize="sm">{backendErrors.map((err) => <ListItem key={err}>{err}</ListItem>)}</List>
            </Box>
          </Alert>
        )}
        {anotherModeRunning && (
          <Alert status="warning" variant="left-accent">
            <AlertIcon />
            <AlertDescription>
              A {status?.mode} session is running from another tab — stop it before starting a Testing-tab move.
            </AlertDescription>
          </Alert>
        )}
        {!isHomed && (
          <Alert status="info" variant="left-accent">
            <AlertIcon />
            <AlertDescription>Home the cable first (Setup tab) to enable r_eff/force conversions here.</AlertDescription>
          </Alert>
        )}

        <Card bg="gray.800" variant="elevated">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="white">Testing — Torque/Force Calibration</Heading>
              <HStack>
                {running && <Badge colorScheme="green" variant="solid">Running</Badge>}
                <Badge colorScheme={isHomed ? 'green' : 'gray'} variant="outline">{isHomed ? 'homed' : 'not homed'}</Badge>
                <Badge colorScheme={connected ? 'green' : 'gray'} variant="outline">{connected ? 'connected' : 'disconnected'}</Badge>
              </HStack>
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={4}>
              <SimpleGrid columns={{ base: 2, md: 5 }} spacing={4}>
                <Stat>
                  <StatLabel color="gray.300">Home</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{cable?.home_turns != null ? cable.home_turns.toFixed(3) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">turns</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Max extension</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{cable?.max_extension_length_m != null ? cable.max_extension_length_m.toFixed(3) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">m, from home</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Spool radius (r0)</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{r0 != null ? r0.toFixed(4) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">m</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Effective radius (r_eff)</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{rEffAtCurrent != null ? rEffAtCurrent.toFixed(4) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">m, at current position</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Correction (k)</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{cable?.k != null ? cable.k.toExponential(2) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">m/rad</Text>
                </Stat>
              </SimpleGrid>

              <HStack>
                <Button size="sm" colorScheme="red" variant="solid" fontWeight="bold" onClick={handleStop} isDisabled={busy || !running}>
                  STOP
                </Button>
              </HStack>
            </VStack>
          </CardBody>
        </Card>

        <Card bg="gray.800" variant="elevated">
          <CardHeader><Heading size="sm" color="white">Configure move</Heading></CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={4}>
              <HStack spacing={4} wrap="wrap">
                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Known weight</Text>
                  <InputGroup size="sm" w="140px">
                    <Input type="text" inputMode="decimal" fontFamily="mono" value={knownWeightText} onChange={(e) => setKnownWeightText(e.target.value)} />
                    <InputRightAddon px={2} fontSize="xs">kg</InputRightAddon>
                  </InputGroup>
                </Box>

                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Move Distance</Text>
                  <HStack spacing={1}>
                    <InputGroup size="sm" w="110px">
                      <Input type="text" inputMode="decimal" fontFamily="mono" value={moveDistanceText} onChange={(e) => setMoveDistanceText(e.target.value)} />
                    </InputGroup>
                    <Select size="sm" w="80px" value={moveUnit} onChange={(e) => setMoveUnit(e.target.value)}>
                      <option value="m">m</option>
                      <option value="turns">turns</option>
                    </Select>
                  </HStack>
                  <Text fontSize="0.65rem" color="gray.500" mt={0.5}>
                    relative to current position
                    {moveUnit === 'm' && (
                      moveDistanceTurnsEstimate != null
                        ? ` (≈ ${moveDistanceTurnsEstimate.toFixed(3)} turns)`
                        : r0 == null ? ' (loading cable calibration…)' : ' (out of range for current calibration)'
                    )}
                  </Text>
                </Box>

                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Move Velocity</Text>
                  <InputGroup size="sm" w="140px">
                    <Input type="text" inputMode="decimal" fontFamily="mono" value={moveVelocityText} onChange={(e) => setMoveVelocityText(e.target.value)} />
                    <InputRightAddon px={2} fontSize="xs">turns/s</InputRightAddon>
                  </InputGroup>
                </Box>

                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Torque Limit</Text>
                  <HStack spacing={1}>
                    <InputGroup size="sm" w="110px">
                      <Input
                        type="text"
                        inputMode="decimal"
                        fontFamily="mono"
                        placeholder="unlimited"
                        value={torqueLimitText}
                        onChange={(e) => setTorqueLimitText(e.target.value)}
                      />
                    </InputGroup>
                    <Select size="sm" w="80px" value={torqueLimitUnit} onChange={(e) => setTorqueLimitUnit(e.target.value)}>
                      <option value="Nm">Nm</option>
                      <option value="N">N</option>
                      <option value="kg">kg</option>
                    </Select>
                  </HStack>
                  {torqueLimitText !== '' && torqueLimitUnit !== 'Nm' && (
                    <Text fontSize="0.65rem" color="gray.500" mt={0.5}>
                      {torqueLimitNm != null ? `≈ ${torqueLimitNm.toFixed(4)} Nm` : 'loading cable calibration…'}
                    </Text>
                  )}
                </Box>

                <VStack align="stretch" spacing={1} justify="flex-end">
                  <Text fontSize="xs" color="transparent" userSelect="none">.</Text>
                  {running ? (
                    <Button size="sm" colorScheme="odrive" onClick={handleRetarget} isDisabled={!targetValid}>
                      Update
                    </Button>
                  ) : (
                    <Button size="sm" colorScheme="green" onClick={handleStart} isDisabled={!targetValid || busy || anotherModeRunning}>
                      Start
                    </Button>
                  )}
                </VStack>
              </HStack>

              <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                <Stat>
                  <StatLabel color="gray.300">Position</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{latestSample?.position_m != null ? latestSample.position_m.toFixed(4) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">m, from home</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Measured torque</StatLabel>
                  {/* Magnitude, not signed (item 3): the sign of torque_est/corrected_torque_nm
                      encodes direction, meaningful for control/debugging (see
                      TorqueModelDiagnostics' Developer panel, which shows the raw signed
                      value) -- but resistance itself isn't "negative", so this main
                      user-facing stat shows how much torque is being felt, not which way. */}
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
                  <Text fontSize="xs" color="gray.400">
                    N{expectedForceN != null ? ` — expected ${expectedForceN.toFixed(2)} N` : ''}
                  </Text>
                </Stat>
              </SimpleGrid>
            </VStack>
          </CardBody>
        </Card>

        <Card bg="gray.800" variant="elevated">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="sm" color="white">Torque/Force calibration</Heading>
              <Badge colorScheme={calibrationPoints.length > 0 ? 'green' : 'gray'} variant="outline">
                {calibrationPoints.length > 0 ? `${calibrationPoints.length} point${calibrationPoints.length === 1 ? '' : 's'} recorded` : 'not calibrated'}
              </Badge>
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={3}>
              <Text fontSize="xs" color="gray.400">
                Hang the Known Weight above, move it to a held position, then record a point once it's steady --
                the software pairs the live measured torque with that known weight. Repeat with other masses to
                improve the fit; see Developer diagnostics below for the model this builds.
              </Text>
              {calibError && (
                <Alert status="error" variant="left-accent"><AlertIcon /><AlertDescription>{calibError}</AlertDescription></Alert>
              )}
              <HStack>
                <Button size="sm" colorScheme="odrive" onClick={handleRecordPoint} isLoading={calibBusy} isDisabled={!isHomed || !running}>
                  Record calibration point
                </Button>
                <Button size="sm" variant="outline" colorScheme="red" onClick={handleClearCalibration} isLoading={calibBusy} isDisabled={calibrationPoints.length === 0}>
                  Clear calibration
                </Button>
              </HStack>

              {calibrationPoints.length > 0 && (
                <VStack align="stretch" spacing={1} fontSize="xs" fontFamily="mono" color="gray.300">
                  <HStack justify="space-between" color="gray.500">
                    <Text w="80px">weight</Text>
                    <Text w="90px">raw torque</Text>
                    <Text w="90px">r_eff</Text>
                    <Text w="90px">expected</Text>
                  </HStack>
                  {calibrationPoints.map((p, i) => (
                    <HStack key={i} justify="space-between">
                      <Text w="80px">{p.known_weight_kg.toFixed(2)} kg</Text>
                      <Text w="90px">{p.raw_torque_nm.toFixed(4)} Nm</Text>
                      <Text w="90px">{p.r_eff_m.toFixed(4)} m</Text>
                      <Text w="90px">{p.expected_torque_nm.toFixed(4)} Nm</Text>
                    </HStack>
                  ))}
                </VStack>
              )}
            </VStack>
          </CardBody>
        </Card>

        <TorqueModelDiagnostics cable={cable} />

        <TelemetryTimeSeriesChart series={series} lines={CHART_LINES} bufferS={90} title="Testing telemetry" />
      </VStack>
    </Box>
  )
}

export default TestingTab
