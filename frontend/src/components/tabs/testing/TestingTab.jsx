import { useMemo, useState } from 'react'
import {
  Box, VStack, HStack, Text, Heading, Badge, Button, Card, CardHeader, CardBody,
  SimpleGrid, Stat, StatLabel, StatNumber, Input, InputGroup, InputRightAddon, Select,
  Alert, AlertIcon, AlertTitle, AlertDescription, List, ListItem,
  Tabs, TabList, TabPanels, Tab, TabPanel,
} from '@chakra-ui/react'
import { useTestingTelemetry } from '../../../hooks/useTestingTelemetry'
import { startControlSession, setControlTarget, stopControlSession } from '../../../api/control'
import { analyzeTorqueCalibrationRun, recordTorqueCalibrationPoint, clearTorqueCalibration } from '../../../api/exercise'
import {
  turnsDeltaFromLength, createSpoolGeometry, torqueFromForce, rawTorqueNmForCorrected, GRAVITY_M_S2,
} from '../../../utils/cableGeometry'
import TelemetryTimeSeriesChart from '../../shared/TelemetryTimeSeriesChart'
import TorqueModelDiagnostics from './TorqueModelDiagnostics'
import RepetitiveTesting from './RepetitiveTesting'

// Item 2: rebuilt on Control tab's own `mode: "position"` session (see
// useTestingTelemetry.js's header comment) instead of a dedicated
// "experiment" ControlSession mode -- change a field, hit Update, see the
// effect immediately, keep adjusting without stopping. Known Weight/Move
// Distance(+unit)/Move Velocity/Torque Limit(+unit) mirror Control tab's own
// Position-mode fields exactly (frontend/src/components/tabs/control/ControlTab.jsx),
// plus the calibration-specific additions (items 6/7) below the telemetry.
const CHART_LINES = [
  { key: 'position_m', label: 'Position (actual)', color: '#2563eb', unit: 'm', defaultOn: true, side: 'left' },
  { key: 'target_position_m', label: 'Target position', color: '#2563eb', unit: 'm', defaultOn: true, side: 'left', axisKey: 'position_m', dashed: true },
  { key: 'corrected_torque_nm', label: 'Torque (calibrated)', color: '#eb6834', unit: 'Nm', defaultOn: true, side: 'right' },
  { key: 'torque_est_nm', label: 'Torque (raw estimate)', color: '#1baf7a', unit: 'Nm', defaultOn: false, side: 'right' },
  { key: 'force_est_n', label: 'Force (calculated)', color: '#eda100', unit: 'N', defaultOn: true, side: 'right' },
  { key: 'current_iq_a', label: 'Phase current', color: '#e87ba4', unit: 'A', defaultOn: false, side: 'right' },
  { key: 'bus_voltage_v', label: 'Bus voltage', color: '#008300', unit: 'V', defaultOn: false, side: 'right' },
  { key: 'estimated_power_w', label: 'Estimated power', color: '#4a3aa7', unit: 'W', defaultOn: false, side: 'right' },
]

// Not user-facing (item 2: "we don't need acceleration or deceleration
// controls for now") -- matches board_constants.TRAP_TRAJ_ACCEL_LIMIT, the
// same default ExerciseMode._apply_move/PositionMode fall back to.
export const DEFAULT_ACCEL_DECEL = 1.0

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
  // Result of the last analyze_torque_calibration_run call -- { log_path,
  // up: {...} | null, down: {...} | null }. null until Analyze is clicked.
  // Read-only preview; nothing is saved until Insert is pressed for a
  // direction (recordTorqueCalibrationPoint below). insertedDirections
  // tracks which of this analysis's directions have already been inserted,
  // so re-clicking Insert is guarded and the button can show it happened.
  const [analysis, setAnalysis] = useState(null)
  const [insertedDirections, setInsertedDirections] = useState(() => new Set())

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

  const handleAnalyzeRun = async () => {
    if (!knownWeightValid) {
      setCalibError('Enter a valid known weight first')
      return
    }
    setCalibError(null)
    setCalibBusy(true)
    try {
      const result = await analyzeTorqueCalibrationRun(knownWeightNumber)
      setAnalysis(result)
      setInsertedDirections(new Set())
    } catch (e) {
      setCalibError(e.message)
      setAnalysis(null)
    } finally {
      setCalibBusy(false)
    }
  }

  const handleInsert = async (direction) => {
    const result = analysis?.[direction]
    if (!result) return
    setCalibError(null)
    setCalibBusy(true)
    try {
      await recordTorqueCalibrationPoint({
        knownWeightKg: result.known_weight_kg,
        rawTorqueNm: result.raw_torque_nm,
        rEffM: result.r_eff_m,
        direction: result.direction,
      })
      setInsertedDirections((prev) => new Set(prev).add(direction))
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
      setAnalysis(null)
      setInsertedDirections(new Set())
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

        <Card bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="paper.textPrimary">Testing — Torque/Force Calibration</Heading>
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
                  <StatLabel color="paper.textPrimary">Home</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{cable?.home_turns != null ? cable.home_turns.toFixed(3) : '—'}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">turns</Text>
                </Stat>
                <Stat>
                  <StatLabel color="paper.textPrimary">Max extension</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{cable?.max_extension_length_m != null ? cable.max_extension_length_m.toFixed(3) : '—'}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">m, from home</Text>
                </Stat>
                <Stat>
                  <StatLabel color="paper.textPrimary">Spool radius (r0)</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{r0 != null ? r0.toFixed(4) : '—'}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">m</Text>
                </Stat>
                <Stat>
                  <StatLabel color="paper.textPrimary">Effective radius (r_eff)</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{rEffAtCurrent != null ? rEffAtCurrent.toFixed(4) : '—'}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">m, at current position</Text>
                </Stat>
                <Stat>
                  <StatLabel color="paper.textPrimary">Correction (k)</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{cable?.k != null ? cable.k.toExponential(2) : '—'}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">m/rad</Text>
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

        <Card bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
          <Tabs colorScheme="accent" isLazy lazyBehavior="keepMounted">
            <CardHeader pb={0}>
              <TabList border="none">
                <Tab color="paper.textPrimary" _selected={{ color: 'accent.600', borderColor: 'accent.600' }}>Configure move</Tab>
                <Tab color="paper.textPrimary" _selected={{ color: 'accent.600', borderColor: 'accent.600' }}>Repetitive testing</Tab>
              </TabList>
            </CardHeader>
            <CardBody>
              <TabPanels>
                <TabPanel p={0}>
            <VStack align="stretch" spacing={4}>
              <HStack spacing={4} wrap="wrap">
                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Known weight</Text>
                  <InputGroup size="sm" w="140px">
                    <Input type="text" inputMode="decimal" fontFamily="mono" value={knownWeightText} onChange={(e) => setKnownWeightText(e.target.value)} />
                    <InputRightAddon px={2} fontSize="xs">kg</InputRightAddon>
                  </InputGroup>
                </Box>

                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Move Distance</Text>
                  <HStack spacing={1}>
                    <InputGroup size="sm" w="110px">
                      <Input type="text" inputMode="decimal" fontFamily="mono" value={moveDistanceText} onChange={(e) => setMoveDistanceText(e.target.value)} />
                    </InputGroup>
                    <Select size="sm" w="80px" value={moveUnit} onChange={(e) => setMoveUnit(e.target.value)}>
                      <option value="m">m</option>
                      <option value="turns">turns</option>
                    </Select>
                  </HStack>
                  <Text fontSize="0.65rem" color="paper.textSecondary" mt={0.5}>
                    relative to current position
                    {moveUnit === 'm' && (
                      moveDistanceTurnsEstimate != null
                        ? ` (≈ ${moveDistanceTurnsEstimate.toFixed(3)} turns)`
                        : r0 == null ? ' (loading cable calibration…)' : ' (out of range for current calibration)'
                    )}
                  </Text>
                </Box>

                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Move Velocity</Text>
                  <InputGroup size="sm" w="140px">
                    <Input type="text" inputMode="decimal" fontFamily="mono" value={moveVelocityText} onChange={(e) => setMoveVelocityText(e.target.value)} />
                    <InputRightAddon px={2} fontSize="xs">turns/s</InputRightAddon>
                  </InputGroup>
                </Box>

                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Torque Limit</Text>
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
                    <Text fontSize="0.65rem" color="paper.textSecondary" mt={0.5}>
                      {torqueLimitNm != null ? `≈ ${torqueLimitNm.toFixed(4)} Nm` : 'loading cable calibration…'}
                    </Text>
                  )}
                </Box>

                <VStack align="stretch" spacing={1} justify="flex-end">
                  <Text fontSize="xs" color="transparent" userSelect="none">.</Text>
                  {running ? (
                    <Button size="sm" colorScheme="accent" onClick={handleRetarget} isDisabled={!targetValid}>
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
                  <StatLabel color="paper.textPrimary">Position</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{latestSample?.position_m != null ? latestSample.position_m.toFixed(4) : '—'}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">m, from home</Text>
                </Stat>
                <Stat>
                  <StatLabel color="paper.textPrimary">Measured torque</StatLabel>
                  {/* Magnitude, not signed (item 3): the sign of torque_est/corrected_torque_nm
                      encodes direction, meaningful for control/debugging (see
                      TorqueModelDiagnostics' Developer panel, which shows the raw signed
                      value) -- but resistance itself isn't "negative", so this main
                      user-facing stat shows how much torque is being felt, not which way. */}
                  <StatNumber color="accent.600" fontSize="xl">{latestSample?.corrected_torque_nm != null ? Math.abs(latestSample.corrected_torque_nm).toFixed(3) : '—'}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">Nm, calibrated</Text>
                </Stat>
                <Stat>
                  <StatLabel color="paper.textPrimary">Phase current</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{status?.latest_sample?.current_iq != null ? status.latest_sample.current_iq.toFixed(3) : '—'}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">A (Iq_measured)</Text>
                </Stat>
                <Stat>
                  <StatLabel color="paper.textPrimary">Measured force</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{latestSample?.force_est_n != null ? Math.abs(latestSample.force_est_n).toFixed(2) : '—'}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">
                    N{expectedForceN != null ? ` — expected ${expectedForceN.toFixed(2)} N` : ''}
                  </Text>
                </Stat>
              </SimpleGrid>
            </VStack>
                </TabPanel>
                <TabPanel p={0}>
                  <RepetitiveTesting
                    status={status}
                    cable={cable}
                    running={running}
                    anotherModeRunning={anotherModeRunning}
                    isHomed={isHomed}
                    rEffAtCurrent={rEffAtCurrent}
                    latestSample={latestSample}
                  />
                </TabPanel>
              </TabPanels>
            </CardBody>
          </Tabs>
        </Card>

        <Card bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="sm" color="paper.textPrimary">Torque/Force calibration</Heading>
              <Badge colorScheme={calibrationPoints.length > 0 ? 'green' : 'gray'} variant="outline">
                {calibrationPoints.length > 0 ? `${calibrationPoints.length} point${calibrationPoints.length === 1 ? '' : 's'} recorded` : 'not calibrated'}
              </Badge>
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={3}>
              <Text fontSize="xs" color="paper.textSecondary">
                Hang the Known Weight above and run it through several reps (e.g. Repetitive testing above, or a
                few manual up/down moves) -- friction makes lifting and lowering read differently, so this fits a
                separate line for each direction from the steady-state (constant-velocity) part of every rep,
                not a single static hold. Stop the run, then Analyze last run: it reads back that run's telemetry
                and shows a candidate point per direction below, for review before inserting either into the
                saved calibration. Repeat at a few different known weights (e.g. 5/10/15 kg) for a better fit.
              </Text>
              {calibError && (
                <Alert status="error" variant="left-accent"><AlertIcon /><AlertDescription>{calibError}</AlertDescription></Alert>
              )}
              <HStack>
                <Button size="sm" colorScheme="accent" onClick={handleAnalyzeRun} isLoading={calibBusy} isDisabled={!isHomed || running}>
                  Analyze last run
                </Button>
                <Button size="sm" variant="outline" colorScheme="red" onClick={handleClearCalibration} isLoading={calibBusy} isDisabled={calibrationPoints.length === 0}>
                  Clear calibration
                </Button>
              </HStack>

              {analysis && (
                <VStack align="stretch" spacing={2} fontSize="xs">
                  <Text color="paper.textSecondary" fontFamily="mono" noOfLines={1}>log: {analysis.log_path}</Text>
                  {['up', 'down'].map((direction) => {
                    const result = analysis[direction]
                    const inserted = insertedDirections.has(direction)
                    return (
                      <HStack key={direction} justify="space-between" bg="paper.bg" px={3} py={2} borderRadius="md">
                        <VStack align="stretch" spacing={0} fontFamily="mono" color="paper.textPrimary">
                          <Text color="paper.textPrimary" fontWeight="bold">
                            {direction === 'up' ? 'Up (lifting)' : 'Down (lowering)'}
                          </Text>
                          {result ? (
                            <>
                              <Text>{result.rep_count} rep{result.rep_count === 1 ? '' : 's'} -- raw torque {result.raw_torque_nm.toFixed(4)} Nm (expected {result.expected_torque_nm.toFixed(4)} Nm), r_eff {result.r_eff_m.toFixed(4)} m</Text>
                              <Text color="paper.textSecondary">per-rep: {result.per_rep_raw_torque_nm.map((v) => v.toFixed(3)).join(', ')}</Text>
                            </>
                          ) : (
                            <Text color="paper.textSecondary">No qualifying reps found in this direction in the last run.</Text>
                          )}
                        </VStack>
                        <Button
                          size="sm"
                          colorScheme={inserted ? 'green' : 'odrive'}
                          variant={inserted ? 'outline' : 'solid'}
                          onClick={() => handleInsert(direction)}
                          isLoading={calibBusy}
                          isDisabled={!result || inserted}
                        >
                          {inserted ? 'Inserted' : 'Insert'}
                        </Button>
                      </HStack>
                    )
                  })}
                </VStack>
              )}

              {calibrationPoints.length > 0 && (
                <VStack align="stretch" spacing={1} fontSize="xs" fontFamily="mono" color="paper.textPrimary">
                  <HStack justify="space-between" color="paper.textSecondary">
                    <Text w="70px">weight</Text>
                    <Text w="55px">dir</Text>
                    <Text w="90px">raw torque</Text>
                    <Text w="90px">r_eff</Text>
                    <Text w="90px">expected</Text>
                  </HStack>
                  {calibrationPoints.map((p, i) => (
                    <HStack key={i} justify="space-between">
                      <Text w="70px">{p.known_weight_kg.toFixed(2)} kg</Text>
                      <Text w="55px">{p.direction}</Text>
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
