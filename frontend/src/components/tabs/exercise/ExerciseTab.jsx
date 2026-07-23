import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Box,
  VStack,
  HStack,
  Text,
  Heading,
  Badge,
  Button,
  Card,
  CardHeader,
  CardBody,
  SimpleGrid,
  Stat,
  StatLabel,
  StatNumber,
  Input,
  InputGroup,
  InputRightAddon,
  Select,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  List,
  ListItem,
  Collapse,
  useDisclosure,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalCloseButton,
  ModalBody,
  ModalFooter,
} from '@chakra-ui/react'
import { ChevronDownIcon, ChevronRightIcon } from '@chakra-ui/icons'

import { useExerciseStatus } from '../../../hooks/useExerciseStatus'
import {
  startExerciseSession,
  homeExercise,
  abortHoming,
  startMaxCalibration,
  confirmMax,
  cancelMaxCalibration,
  moveCable,
  stopExercise,
  resetExercisePosition,
  calibrateSpoolK,
  updateHomingSettings,
  updateSpoolRadius,
  updateCalibHoldForce,
} from '../../../api/exercise'
import {
  startForceSession,
  engageForce,
  updateForceParams,
  disengageForce,
  resumeForce,
  stopForce,
} from '../../../api/force'
import { getBoardConstants } from '../../../api/backend'
import MiniChart from '../control/MiniChart'

const HOMING_STATE_LABEL = {
  startup_grace: 'Starting…',
  detecting: 'Reeling in…',
  homed: 'Homed',
  fault_travel_exceeded: 'Fault: travel bound exceeded',
  fault_timeout: 'Fault: timed out',
  aborted: 'Aborted',
}

const FORCE_STATE_LABEL = {
  armed: 'Armed',
  engaged_concentric: 'Engaged',
  holding: 'Holding',
  fault: 'FAULT',
}

const FORCE_STATE_COLOR = {
  armed: 'gray',
  engaged_concentric: 'orange',
  holding: 'yellow',
  fault: 'red',
}

const N_PER_KGF = 9.80665

const ExerciseTab = ({ isActive = true }) => {
  const { status, series, connected } = useExerciseStatus(isActive)
  const control = status?.control
  const cable = status?.cable

  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [targetLengthText, setTargetLengthText] = useState('0.3')
  const [moveVelocityText, setMoveVelocityText] = useState('1.0')
  const [moveAccelText, setMoveAccelText] = useState('1.0')
  const [measuredLengthText, setMeasuredLengthText] = useState('')
  const [calibError, setCalibError] = useState(null)
  const [calibBusy, setCalibBusy] = useState(false)
  const [boardConstants, setBoardConstants] = useState(null)

  const [forceMode, setForceMode] = useState('constant')
  const [forceText, setForceText] = useState('20')
  const [velocityCapText, setVelocityCapText] = useState('1.0')
  const [rangeStartText, setRangeStartText] = useState('')
  const [rangeEndText, setRangeEndText] = useState('')
  const [forceError, setForceError] = useState(null)
  const [forceBusy, setForceBusy] = useState(false)

  const [homingThresholdText, setHomingThresholdText] = useState('')
  const [homingVelocityText, setHomingVelocityText] = useState('')
  const [homingLimitText, setHomingLimitText] = useState('')
  const [homingSettingsError, setHomingSettingsError] = useState(null)
  const [homingSettingsBusy, setHomingSettingsBusy] = useState(false)

  const [spoolRadiusText, setSpoolRadiusText] = useState('')
  const [spoolRadiusError, setSpoolRadiusError] = useState(null)
  const [spoolRadiusBusy, setSpoolRadiusBusy] = useState(false)

  const [calibHoldForceText, setCalibHoldForceText] = useState('')
  const [calibHoldForceError, setCalibHoldForceError] = useState(null)
  const [calibHoldForceBusy, setCalibHoldForceBusy] = useState(false)

  const { isOpen: resetOpen, onOpen: openReset, onClose: closeReset } = useDisclosure()
  const { isOpen: advancedOpen, onToggle: toggleAdvanced } = useDisclosure()
  const { isOpen: homingOpen, onToggle: toggleHoming } = useDisclosure({ defaultIsOpen: true })
  const { isOpen: resumeOpen, onOpen: openResume, onClose: closeResume } = useDisclosure()

  useEffect(() => {
    getBoardConstants().then(setBoardConstants).catch(() => {})
  }, [])

  // Prefill the editable settings fields from the backend's current values,
  // once, the first time they arrive -- not on every poll, so the field
  // doesn't fight the user while they're mid-edit.
  const settingsInitialized = useRef(false)
  useEffect(() => {
    if (settingsInitialized.current || !status?.cable) return
    const c = status.cable
    if (c.homing_current_threshold_a == null) return
    setHomingThresholdText(String(c.homing_current_threshold_a))
    setHomingVelocityText(String(c.homing_velocity_turns_s))
    setHomingLimitText(String(c.homing_current_limit_a))
    setSpoolRadiusText(String(c.r0))
    setCalibHoldForceText(String(c.calib_hold_force_n))
    settingsInitialized.current = true
  }, [status?.cable])

  const sessionRunning = Boolean(control?.running && control?.mode === 'exercise')
  const forceSessionRunning = Boolean(control?.running && control?.mode === 'force')
  // Exercise and Force are two mutually-exclusive modes sharing this one
  // tab -- "another mode running" means something OUTSIDE this tab's own
  // two, not just switching attention between its two sections.
  const anotherModeRunning = Boolean(control?.running && control?.mode !== 'exercise' && control?.mode !== 'force')
  const action = control?.extra?.action ?? null
  const homingState = control?.extra?.homing_state ?? null
  const busyAction = action === 'homing' || action === 'max_calibrating'

  const isHomed = cable?.is_homed ?? false
  const hasMax = cable?.has_max ?? false

  const forceState = forceSessionRunning ? control?.extra?.force_state ?? null : null
  const forceEngaged = forceState === 'engaged_concentric' || forceState === 'holding'
  const forceFaulted = forceState === 'fault'
  const torqueConstantIsEstimate = boardConstants?.force?.torque_constant_is_estimate ?? true

  const chartData = useMemo(() => {
    if (!series.length) return { position: [], velocity: [], current: [] }
    const t0 = series[0].t
    const position = []
    const velocity = []
    const current = []
    for (const s of series) {
      const t = s.t - t0
      position.push({ t, v: s.position })
      velocity.push({ t, v: s.velocity })
      current.push({ t, v: s.current_iq })
    }
    return { position, velocity, current }
  }, [series])

  const run = async (fn, ...args) => {
    setActionError(null)
    setBusy(true)
    try {
      await fn(...args)
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleStartSession = () => run(startExerciseSession)
  const handleHome = () => run(homeExercise)
  const handleAbortHoming = () => run(abortHoming)
  const handleStartMaxCal = () => run(startMaxCalibration)
  const handleConfirmMax = () => run(confirmMax)
  const handleCancelMaxCal = () => run(cancelMaxCalibration)
  const handleStop = () => run(stopExercise)

  const targetLengthNumber = Number(targetLengthText)
  const targetLengthValid = targetLengthText !== '' && Number.isFinite(targetLengthNumber) && targetLengthNumber >= 0
  const moveVelocityNumber = Number(moveVelocityText)
  const moveVelocityValid = moveVelocityText !== '' && Number.isFinite(moveVelocityNumber) && moveVelocityNumber > 0
  const moveAccelNumber = Number(moveAccelText)
  const moveAccelValid = moveAccelText !== '' && Number.isFinite(moveAccelNumber) && moveAccelNumber > 0
  const moveParamsValid = targetLengthValid && moveVelocityValid && moveAccelValid
  // r0-only estimate (ignores the k wrap-growth correction, same simplification
  // as the kgf estimate under Force below) -- informational, not authoritative.
  const targetLengthTurnsEstimate =
    targetLengthValid && cable?.r0 ? targetLengthNumber / (2 * Math.PI * cable.r0) : null
  const handleMove = () => {
    if (!moveParamsValid) {
      setActionError('Target length, velocity, and accel/decel must all be valid numbers')
      return
    }
    run(moveCable, targetLengthNumber, moveVelocityNumber, moveAccelNumber)
  }

  const homingThresholdNumber = Number(homingThresholdText)
  const homingVelocityNumber = Number(homingVelocityText)
  const homingLimitNumber = Number(homingLimitText)
  const homingSettingsValid =
    homingThresholdText !== '' && Number.isFinite(homingThresholdNumber) && homingThresholdNumber > 0 &&
    homingVelocityText !== '' && Number.isFinite(homingVelocityNumber) && homingVelocityNumber > 0 &&
    homingLimitText !== '' && Number.isFinite(homingLimitNumber) && homingLimitNumber > 0

  const handleUpdateHomingSettings = async () => {
    if (!homingSettingsValid) {
      setHomingSettingsError('Threshold, velocity, and current limit must all be positive numbers')
      return
    }
    setHomingSettingsError(null)
    setHomingSettingsBusy(true)
    try {
      await updateHomingSettings({
        currentThresholdA: homingThresholdNumber,
        velocityTurnsS: homingVelocityNumber,
        currentLimitA: homingLimitNumber,
      })
    } catch (e) {
      setHomingSettingsError(e.message)
    } finally {
      setHomingSettingsBusy(false)
    }
  }

  const spoolRadiusNumber = Number(spoolRadiusText)
  const spoolRadiusValid = spoolRadiusText !== '' && Number.isFinite(spoolRadiusNumber) && spoolRadiusNumber > 0
  const handleUpdateSpoolRadius = async () => {
    if (!spoolRadiusValid) {
      setSpoolRadiusError('Spool radius must be a positive number')
      return
    }
    setSpoolRadiusError(null)
    setSpoolRadiusBusy(true)
    try {
      await updateSpoolRadius(spoolRadiusNumber)
    } catch (e) {
      setSpoolRadiusError(e.message)
    } finally {
      setSpoolRadiusBusy(false)
    }
  }

  const calibHoldForceNumber = Number(calibHoldForceText)
  const calibHoldForceValid =
    calibHoldForceText !== '' && Number.isFinite(calibHoldForceNumber) && calibHoldForceNumber > 0
  const handleUpdateCalibHoldForce = async () => {
    if (!calibHoldForceValid) {
      setCalibHoldForceError('Hold force must be a positive number')
      return
    }
    setCalibHoldForceError(null)
    setCalibHoldForceBusy(true)
    try {
      await updateCalibHoldForce(calibHoldForceNumber)
    } catch (e) {
      setCalibHoldForceError(e.message)
    } finally {
      setCalibHoldForceBusy(false)
    }
  }

  const handleResetConfirmed = async () => {
    setActionError(null)
    setBusy(true)
    try {
      await resetExercisePosition()
      closeReset()
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const forceNumber = Number(forceText)
  const forceValid = forceText !== '' && Number.isFinite(forceNumber) && forceNumber >= 0
  const velocityCapNumber = Number(velocityCapText)
  const velocityCapValid = velocityCapText !== '' && Number.isFinite(velocityCapNumber) && velocityCapNumber > 0
  // Optional bounded sub-range of home->max travel (requested 23 July 2026)
  // -- blank on either side means "use the full range", not zero.
  const rangeStartNumber = rangeStartText !== '' ? Number(rangeStartText) : null
  const rangeStartValid = rangeStartText === '' || (Number.isFinite(rangeStartNumber) && rangeStartNumber >= 0)
  const rangeEndNumber = rangeEndText !== '' ? Number(rangeEndText) : null
  const rangeEndValid = rangeEndText === '' || (Number.isFinite(rangeEndNumber) && rangeEndNumber >= 0)
  const forceParamsValid =
    forceValid && (forceMode !== 'isokinetic' || velocityCapValid) && rangeStartValid && rangeEndValid

  const runForce = async (fn, ...args) => {
    setForceError(null)
    setForceBusy(true)
    try {
      await fn(...args)
    } catch (e) {
      setForceError(e.message)
    } finally {
      setForceBusy(false)
    }
  }

  const handleStartForceSession = () => runForce(startForceSession)
  const handleStopForce = () => runForce(stopForce)

  const forceParams = () => ({
    mode: forceMode,
    forceN: forceNumber,
    velocityTargetTurnsS: forceMode === 'isokinetic' ? velocityCapNumber : undefined,
    startLengthM: rangeStartNumber,
    endLengthM: rangeEndNumber,
  })

  const handleEngage = () => {
    if (!forceParamsValid) {
      setForceError('Force, velocity cap (for isokinetic), and range bounds must be valid numbers')
      return
    }
    runForce(engageForce, forceParams())
  }

  const handleUpdateForce = () => {
    if (!forceParamsValid) {
      setForceError('Force, velocity cap (for isokinetic), and range bounds must be valid numbers')
      return
    }
    runForce(updateForceParams, forceParams())
  }

  const handleDisengage = () => runForce(disengageForce)

  const handleResumeConfirmed = async () => {
    setForceError(null)
    setForceBusy(true)
    try {
      await resumeForce()
      closeResume()
    } catch (e) {
      setForceError(e.message)
    } finally {
      setForceBusy(false)
    }
  }

  const measuredLengthNumber = Number(measuredLengthText)
  const measuredLengthValid = measuredLengthText !== '' && Number.isFinite(measuredLengthNumber) && measuredLengthNumber >= 0
  const handleCalibrate = async () => {
    if (!measuredLengthValid) {
      setCalibError('Measured length must be a non-negative number')
      return
    }
    setCalibError(null)
    setCalibBusy(true)
    try {
      await calibrateSpoolK(measuredLengthNumber)
      setMeasuredLengthText('')
    } catch (e) {
      setCalibError(e.message)
    } finally {
      setCalibBusy(false)
    }
  }

  const latest = control?.latest_sample
  const logFilename = control?.log_path ? control.log_path.split('/').pop() : null
  const backendErrors = control?.errors ?? []
  const ex = boardConstants?.exercise
  const kBounds = ex?.spool_correction_k_bounds

  // Idle-gated (spec §3.5): reset must be unreachable while an Exercise
  // session is running at all, matching the backend's own check exactly.
  const resetDisabled = sessionRunning || busy || (!isHomed && !hasMax)

  return (
    <Box p={4} h="100%" maxW="1400px" mx="auto" overflow="auto">
      <VStack spacing={4} align="stretch">
        {actionError && (
          <Alert status="error" variant="left-accent">
            <AlertIcon />
            <AlertDescription>{actionError}</AlertDescription>
          </Alert>
        )}

        {control?.errored && (
          <Alert status="error" variant="left-accent">
            <AlertIcon />
            <Box>
              <AlertTitle>Session auto-stopped</AlertTitle>
              <AlertDescription>{control.error_message}</AlertDescription>
            </Box>
          </Alert>
        )}

        {backendErrors.length > 0 && (
          <Alert status="warning" variant="left-accent">
            <AlertIcon />
            <Box>
              <AlertTitle>Hardware errors</AlertTitle>
              <List fontSize="sm">
                {backendErrors.map((err) => <ListItem key={err}>{err}</ListItem>)}
              </List>
            </Box>
          </Alert>
        )}

        {anotherModeRunning && (
          <Alert status="warning" variant="left-accent">
            <AlertIcon />
            <AlertDescription>
              A {control?.mode} session is running from another tab — stop it before starting Exercise or Force
              Feedback.
            </AlertDescription>
          </Alert>
        )}

        {forceFaulted && (
          <Alert status="error" variant="left-accent">
            <AlertIcon />
            <Box>
              <AlertTitle>Force session faulted</AlertTitle>
              <AlertDescription>
                {control?.extra?.fault_reason || 'Resistance was hard-stopped.'} Resume to continue, or Stop to end
                the session.
              </AlertDescription>
            </Box>
          </Alert>
        )}

        {cable?.last_homing_fault && !sessionRunning && (
          <Alert status="warning" variant="left-accent">
            <AlertIcon />
            <AlertDescription>Last homing attempt failed: {cable.last_homing_fault}</AlertDescription>
          </Alert>
        )}

        {/* Session + status */}
        <Card bg="gray.800" variant="elevated">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="white">Exercise</Heading>
              <HStack>
                <Badge colorScheme={isHomed ? 'green' : 'gray'} variant="outline">
                  {isHomed ? 'homed' : 'not homed'}
                </Badge>
                <Badge colorScheme={connected ? 'green' : 'gray'} variant="outline">
                  {connected ? 'connected' : 'disconnected'}
                </Badge>
              </HStack>
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={4}>
              <HStack spacing={4} wrap="wrap">
                {!sessionRunning ? (
                  <Button
                    size="sm"
                    colorScheme="green"
                    onClick={handleStartSession}
                    isDisabled={busy || anotherModeRunning}
                  >
                    Start Exercise Session
                  </Button>
                ) : (
                  <Button size="sm" colorScheme="red" variant="solid" fontWeight="bold" onClick={handleStop}>
                    STOP
                  </Button>
                )}
              </HStack>

              <SimpleGrid columns={{ base: 2, md: 5 }} spacing={4}>
                <Stat>
                  <StatLabel color="gray.300">Cable length</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">
                    {control?.extra?.cable_length_m != null ? control.extra.cable_length_m.toFixed(3) : '—'}
                  </StatNumber>
                  <Text fontSize="xs" color="gray.400">m, from home</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Cable position</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">
                    {cable?.cable_position_turns != null ? cable.cable_position_turns.toFixed(3) : '—'}
                  </StatNumber>
                  <Text fontSize="xs" color="gray.400">turns, zeroed at home</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Encoder position</StatLabel>
                  <StatNumber color="gray.400" fontSize="xl">{(latest?.position ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="gray.400">turns, absolute</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Current (Iq)</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{(latest?.current_iq ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="gray.400">A</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Max extension</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{hasMax ? 'set' : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">{hasMax ? '' : 'not calibrated'}</Text>
                </Stat>
              </SimpleGrid>

              <HStack justify="space-between">
                <Text fontSize="xs" color="gray.400">
                  CSV log: {logFilename ? <Text as="span" fontFamily="mono" color="gray.300">{logFilename}</Text> : '—'}
                </Text>
              </HStack>
            </VStack>
          </CardBody>
        </Card>

        {/* Homing -- collapsible (requested 23 July 2026, declutter once set up);
            first live run must still be attended, abortable, observable (spec §10) */}
        <Box>
          <Button
            variant="ghost"
            size="sm"
            leftIcon={homingOpen ? <ChevronDownIcon /> : <ChevronRightIcon />}
            onClick={toggleHoming}
            color="odrive.300"
          >
            {homingOpen ? 'Hide' : 'Show'} Homing
          </Button>
          <Collapse in={homingOpen} animateOpacity>
            <Card bg="gray.800" variant="elevated" mt={2}>
              <CardHeader>
                <HStack justify="space-between">
                  <Heading size="md" color="white">Homing</Heading>
                  <Badge colorScheme={action === 'homing' ? 'orange' : isHomed ? 'green' : 'gray'} variant="solid">
                    {action === 'homing' ? (HOMING_STATE_LABEL[homingState] ?? 'Homing…') : isHomed ? 'Homed' : 'Not homed'}
                  </Badge>
                </HStack>
              </CardHeader>
              <CardBody>
                <VStack align="stretch" spacing={3}>
                  <Text fontSize="sm" color="gray.400">
                    Slow, current-limited reel-in until the cable goes taut. Watch position and current above —
                    Abort or the always-available STOP will halt it immediately.
                  </Text>
                  <HStack>
                    <Button
                      size="sm"
                      colorScheme="odrive"
                      onClick={handleHome}
                      isDisabled={!sessionRunning || busyAction || busy}
                    >
                      Home
                    </Button>
                    <Button
                      size="sm"
                      colorScheme="red"
                      variant="outline"
                      onClick={handleAbortHoming}
                      isDisabled={action !== 'homing' || busy}
                    >
                      Abort Homing
                    </Button>
                  </HStack>

                  <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
                    <Text fontSize="xs" color="gray.400" mb={2}>
                      Homing settings — live-adjustable, persisted, take effect on the next Home (not
                      retroactively on one already running).
                    </Text>
                    {homingSettingsError && (
                      <Alert status="error" variant="left-accent" mb={2}>
                        <AlertIcon />
                        <AlertDescription>{homingSettingsError}</AlertDescription>
                      </Alert>
                    )}
                    <HStack spacing={4} wrap="wrap" align="flex-end">
                      <Box>
                        <Text fontSize="xs" color="gray.400" mb={1}>Current threshold</Text>
                        <InputGroup size="sm" w="130px">
                          <Input
                            type="text"
                            inputMode="decimal"
                            fontFamily="mono"
                            value={homingThresholdText}
                            onChange={(e) => setHomingThresholdText(e.target.value)}
                          />
                          <InputRightAddon px={2} fontSize="xs">A</InputRightAddon>
                        </InputGroup>
                      </Box>
                      <Box>
                        <Text fontSize="xs" color="gray.400" mb={1}>Reel-in velocity</Text>
                        <InputGroup size="sm" w="140px">
                          <Input
                            type="text"
                            inputMode="decimal"
                            fontFamily="mono"
                            value={homingVelocityText}
                            onChange={(e) => setHomingVelocityText(e.target.value)}
                          />
                          <InputRightAddon px={2} fontSize="xs">turns/s</InputRightAddon>
                        </InputGroup>
                      </Box>
                      <Box>
                        <Text fontSize="xs" color="gray.400" mb={1}>Current limit</Text>
                        <InputGroup size="sm" w="130px">
                          <Input
                            type="text"
                            inputMode="decimal"
                            fontFamily="mono"
                            value={homingLimitText}
                            onChange={(e) => setHomingLimitText(e.target.value)}
                          />
                          <InputRightAddon px={2} fontSize="xs">A</InputRightAddon>
                        </InputGroup>
                      </Box>
                      <Button
                        size="sm"
                        colorScheme="odrive"
                        variant="outline"
                        onClick={handleUpdateHomingSettings}
                        isDisabled={!homingSettingsValid || homingSettingsBusy}
                      >
                        Update
                      </Button>
                    </HStack>
                  </Box>
                </VStack>
              </CardBody>
            </Card>
          </Collapse>
        </Box>

        {/* Max-extension calibration */}
        <Card bg="gray.800" variant="elevated">
          <CardHeader>
            <Heading size="md" color="white">Max Extension</Heading>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={3}>
              <Text fontSize="sm" color="gray.400">
                Applies a light constant tension so the cable stays taut, then pull it out by hand to a safe
                maximum and confirm. Requires homing first.
              </Text>
              {!isHomed && <Text fontSize="xs" color="orange.300">Home the cable before calibrating max extension.</Text>}
              {action === 'max_calibrating' ? (
                <HStack>
                  <Button size="sm" colorScheme="green" onClick={handleConfirmMax} isDisabled={busy}>
                    Set Max Here
                  </Button>
                  <Button size="sm" variant="outline" onClick={handleCancelMaxCal} isDisabled={busy}>
                    Cancel
                  </Button>
                </HStack>
              ) : (
                <Button
                  size="sm"
                  colorScheme="odrive"
                  onClick={handleStartMaxCal}
                  isDisabled={!sessionRunning || !isHomed || busyAction || busy}
                >
                  Start Max-Extension Calibration
                </Button>
              )}

              <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
                <Text fontSize="xs" color="gray.400" mb={2}>
                  Hold force — live-adjustable, persisted, takes effect on the next calibration start.
                </Text>
                {calibHoldForceError && (
                  <Alert status="error" variant="left-accent" mb={2} py={1}>
                    <AlertIcon />
                    <AlertDescription fontSize="xs">{calibHoldForceError}</AlertDescription>
                  </Alert>
                )}
                <HStack>
                  <InputGroup size="sm" w="130px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={calibHoldForceText}
                      onChange={(e) => setCalibHoldForceText(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">N</InputRightAddon>
                  </InputGroup>
                  <Button
                    size="sm"
                    colorScheme="odrive"
                    variant="outline"
                    onClick={handleUpdateCalibHoldForce}
                    isDisabled={!calibHoldForceValid || calibHoldForceBusy}
                  >
                    Update
                  </Button>
                </HStack>
              </Box>
            </VStack>
          </CardBody>
        </Card>

        {/* Move + Force Feedback -- side by side (requested 23 July 2026): kept as
            separate cards rather than merged, since they're mutually-exclusive
            modes sharing this tab, but used together often enough to want them
            visually adjacent. */}
        <SimpleGrid columns={{ base: 1, xl: 2 }} spacing={4}>
        {/* Length-based move */}
        <Card bg="gray.800" variant="elevated">
          <CardHeader>
            <Heading size="md" color="white">Move</Heading>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={3}>
              {(!isHomed || !hasMax) && (
                <Text fontSize="xs" color="orange.300">
                  {!isHomed ? 'Home the cable' : 'Calibrate max extension'} before commanding moves.
                </Text>
              )}
              <HStack spacing={4} wrap="wrap" align="flex-end">
                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Target length</Text>
                  <InputGroup size="sm" w="140px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={targetLengthText}
                      onChange={(e) => setTargetLengthText(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                  </InputGroup>
                  <Text fontSize="0.65rem" color="gray.500" mt={0.5}>
                    {targetLengthTurnsEstimate != null ? `≈ ${targetLengthTurnsEstimate.toFixed(2)} turns` : '—'}
                  </Text>
                </Box>
                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Move Velocity</Text>
                  <InputGroup size="sm" w="140px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={moveVelocityText}
                      onChange={(e) => setMoveVelocityText(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">turns/s</InputRightAddon>
                  </InputGroup>
                </Box>
                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Accel / Decel</Text>
                  <InputGroup size="sm" w="140px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={moveAccelText}
                      onChange={(e) => setMoveAccelText(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">turns/s²</InputRightAddon>
                  </InputGroup>
                </Box>
              </HStack>
              <Button
                size="sm"
                colorScheme="odrive"
                alignSelf="flex-start"
                onClick={handleMove}
                isDisabled={!sessionRunning || !isHomed || !hasMax || busyAction || !moveParamsValid || busy}
              >
                Move
              </Button>
            </VStack>
          </CardBody>
        </Card>

        {/* Force Feedback -- Layer B Session B1, concentric only (exercise_tab_build_spec_layerB.md) */}
        <Card bg="gray.800" variant="elevated" borderColor="purple.600" borderWidth="1px">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="white">Force Feedback</Heading>
              {forceSessionRunning && (
                <Badge colorScheme={FORCE_STATE_COLOR[forceState] || 'gray'} variant="solid">
                  {FORCE_STATE_LABEL[forceState] || forceState}
                </Badge>
              )}
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={4}>
              {torqueConstantIsEstimate && (
                <Alert status="warning" variant="left-accent">
                  <AlertIcon />
                  <AlertDescription fontSize="sm">
                    Displayed forces are <strong>uncalibrated estimates</strong> — the motor's torque constant has
                    not been bench-measured yet (open item #13). Treat exact Newton values as illustrative, not
                    exact.
                  </AlertDescription>
                </Alert>
              )}

              {forceError && (
                <Alert status="error" variant="left-accent">
                  <AlertIcon />
                  <AlertDescription>{forceError}</AlertDescription>
                </Alert>
              )}

              {(!isHomed || !hasMax) && (
                <Text fontSize="xs" color="orange.300">
                  {!isHomed ? 'Home the cable' : 'Calibrate max extension'} before starting force feedback.
                </Text>
              )}

              <HStack spacing={4} wrap="wrap">
                {!forceSessionRunning ? (
                  <Button
                    size="sm"
                    colorScheme="green"
                    onClick={handleStartForceSession}
                    isDisabled={forceBusy || anotherModeRunning || sessionRunning || !isHomed || !hasMax}
                  >
                    Start Force Session
                  </Button>
                ) : (
                  <Button size="sm" colorScheme="red" variant="solid" fontWeight="bold" onClick={handleStopForce}>
                    STOP
                  </Button>
                )}
              </HStack>

              <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
                <HStack spacing={4} wrap="wrap" align="flex-end">
                  <Box>
                    <Text fontSize="xs" color="gray.400" mb={1}>Mode</Text>
                    <Select
                      size="sm"
                      w="140px"
                      value={forceMode}
                      isDisabled={forceEngaged}
                      onChange={(e) => setForceMode(e.target.value)}
                    >
                      <option value="constant">Constant</option>
                      <option value="isokinetic">Isokinetic</option>
                    </Select>
                  </Box>
                  <Box>
                    <Text fontSize="xs" color="gray.400" mb={1}>Force</Text>
                    <InputGroup size="sm" w="140px">
                      <Input
                        type="text"
                        inputMode="decimal"
                        fontFamily="mono"
                        value={forceText}
                        onChange={(e) => setForceText(e.target.value)}
                      />
                      <InputRightAddon px={2} fontSize="xs">N</InputRightAddon>
                    </InputGroup>
                    <Text fontSize="0.65rem" color="gray.500" mt={0.5}>
                      {forceValid ? `≈ ${(forceNumber / N_PER_KGF).toFixed(1)} kgf` : '—'}
                    </Text>
                  </Box>
                  {forceMode === 'isokinetic' && (
                    <Box>
                      <Text fontSize="xs" color="gray.400" mb={1}>Velocity cap</Text>
                      <InputGroup size="sm" w="140px">
                        <Input
                          type="text"
                          inputMode="decimal"
                          fontFamily="mono"
                          value={velocityCapText}
                          onChange={(e) => setVelocityCapText(e.target.value)}
                        />
                        <InputRightAddon px={2} fontSize="xs">turns/s</InputRightAddon>
                      </InputGroup>
                    </Box>
                  )}
                </HStack>

                <Box mt={3}>
                  <Text fontSize="xs" color="gray.400" mb={1}>
                    Active range (optional) — resistance tapers off near these bounds, like the max-extension
                    taper. Blank on either side means the full home-to-max travel.
                  </Text>
                  <HStack spacing={4} wrap="wrap" align="flex-end">
                    <Box>
                      <Text fontSize="xs" color="gray.400" mb={1}>Start</Text>
                      <InputGroup size="sm" w="140px">
                        <Input
                          type="text"
                          inputMode="decimal"
                          fontFamily="mono"
                          placeholder="home"
                          value={rangeStartText}
                          onChange={(e) => setRangeStartText(e.target.value)}
                        />
                        <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                      </InputGroup>
                    </Box>
                    <Box>
                      <Text fontSize="xs" color="gray.400" mb={1}>End</Text>
                      <InputGroup size="sm" w="140px">
                        <Input
                          type="text"
                          inputMode="decimal"
                          fontFamily="mono"
                          placeholder="max"
                          value={rangeEndText}
                          onChange={(e) => setRangeEndText(e.target.value)}
                        />
                        <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                      </InputGroup>
                    </Box>
                  </HStack>
                  {forceEngaged && control?.extra?.range_start_length_m != null && (
                    <Text fontSize="0.65rem" color="gray.500" mt={1}>
                      Active: {control.extra.range_start_length_m.toFixed(2)}m – {control.extra.range_end_length_m.toFixed(2)}m
                    </Text>
                  )}
                </Box>

                {/* Engage/Disengage -- deliberately distinct (colour + placement) from
                    session Start/STOP above (spec §10.2) */}
                <HStack spacing={3} mt={4}>
                  {!forceEngaged ? (
                    <Button
                      size="sm"
                      colorScheme="purple"
                      onClick={handleEngage}
                      isDisabled={!forceSessionRunning || forceFaulted || !forceParamsValid || forceBusy}
                    >
                      Engage
                    </Button>
                  ) : (
                    <>
                      <Button size="sm" colorScheme="purple" variant="outline" onClick={handleUpdateForce} isDisabled={forceBusy}>
                        Update
                      </Button>
                      <Button size="sm" colorScheme="purple" onClick={handleDisengage} isDisabled={forceBusy}>
                        Disengage
                      </Button>
                    </>
                  )}
                  {forceFaulted && (
                    <Button size="sm" colorScheme="orange" onClick={openResume} isDisabled={forceBusy}>
                      Resume
                    </Button>
                  )}
                </HStack>
              </Box>

              {forceSessionRunning && (
                <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                  <Stat>
                    <StatLabel color="gray.300">Commanded force</StatLabel>
                    <StatNumber color="odrive.300" fontSize="xl">
                      {(control?.extra?.commanded_force_n ?? 0).toFixed(1)}
                    </StatNumber>
                    <Text fontSize="xs" color="gray.400">N</Text>
                  </Stat>
                  <Stat>
                    <StatLabel color="gray.300">Estimated force</StatLabel>
                    <StatNumber color="odrive.300" fontSize="xl">
                      {(control?.extra?.estimated_force_n ?? 0).toFixed(1)}
                    </StatNumber>
                    <Text fontSize="xs" color="gray.400">N</Text>
                  </Stat>
                  <Stat>
                    <StatLabel color="gray.300">Cable velocity</StatLabel>
                    <StatNumber color="odrive.300" fontSize="xl">
                      {(control?.extra?.cable_velocity_m_s ?? 0).toFixed(3)}
                    </StatNumber>
                    <Text fontSize="xs" color="gray.400">m/s</Text>
                  </Stat>
                  <Stat>
                    <StatLabel color="gray.300">Power limiter</StatLabel>
                    <Badge colorScheme={control?.extra?.power_limiter_active ? 'orange' : 'gray'} fontSize="sm" mt={1}>
                      {control?.extra?.power_limiter_active ? 'ACTIVE' : 'idle'}
                    </Badge>
                    <Text fontSize="xs" color="gray.400" mt={1}>
                      {(control?.extra?.regen_power_w ?? 0).toFixed(1)} W est.
                    </Text>
                  </Stat>
                </SimpleGrid>
              )}
            </VStack>
          </CardBody>
        </Card>
        </SimpleGrid>

        {/* Manual reset -- idle-gated + confirmation-gated (spec §3.5) */}
        <Card bg="gray.800" variant="elevated">
          <CardHeader>
            <Heading size="md" color="white">Manual Position Reset</Heading>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={3}>
              <Text fontSize="sm" color="gray.400">
                Clears the home reference and max-extension limit. Use this after cable slip or a bad homing
                run. Length-based control is unavailable until homing runs again. Only available while the
                Exercise session is stopped.
              </Text>
              <Button size="sm" colorScheme="red" variant="outline" onClick={openReset} isDisabled={resetDisabled}>
                Reset Position
              </Button>
            </VStack>
          </CardBody>
        </Card>

        {/* Advanced: spool calibration -- collapsed by default (spec §2.4), not reachable by accident */}
        <Box>
          <Button
            variant="ghost"
            size="sm"
            leftIcon={advancedOpen ? <ChevronDownIcon /> : <ChevronRightIcon />}
            onClick={toggleAdvanced}
            color="odrive.300"
          >
            {advancedOpen ? 'Hide' : 'Show'} Advanced: Spool Calibration
          </Button>
          <Collapse in={advancedOpen} animateOpacity>
            <Card bg="gray.800" variant="elevated" mt={2}>
              <CardBody>
                <VStack align="stretch" spacing={3}>
                  <Text fontSize="sm" color="gray.400">
                    Corrects for the spool's effective radius growing as cable wraps onto it. Reel out to some
                    position (via Move, above), physically measure the actual cable length, and enter it here —
                    the correction factor is back-computed, never entered directly.
                  </Text>
                  {calibError && (
                    <Alert status="error" variant="left-accent">
                      <AlertIcon />
                      <AlertDescription>{calibError}</AlertDescription>
                    </Alert>
                  )}
                  <HStack spacing={4} align="flex-end" wrap="wrap">
                    <Box>
                      <Text fontSize="xs" color="gray.400" mb={1}>Measured length</Text>
                      <InputGroup size="sm" w="160px">
                        <Input
                          type="text"
                          inputMode="decimal"
                          fontFamily="mono"
                          value={measuredLengthText}
                          onChange={(e) => setMeasuredLengthText(e.target.value)}
                        />
                        <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                      </InputGroup>
                    </Box>
                    <Button
                      size="sm"
                      colorScheme="odrive"
                      onClick={handleCalibrate}
                      isDisabled={!isHomed || !sessionRunning || !measuredLengthValid || calibBusy}
                    >
                      Calibrate
                    </Button>
                  </HStack>
                  <SimpleGrid columns={2} spacing={3}>
                    <Box>
                      <Text fontSize="xs" color="gray.400" mb={1}>Spool radius (r0)</Text>
                      {spoolRadiusError && (
                        <Alert status="error" variant="left-accent" mb={2} py={1}>
                          <AlertIcon />
                          <AlertDescription fontSize="xs">{spoolRadiusError}</AlertDescription>
                        </Alert>
                      )}
                      <HStack>
                        <InputGroup size="sm" w="130px">
                          <Input
                            type="text"
                            inputMode="decimal"
                            fontFamily="mono"
                            value={spoolRadiusText}
                            onChange={(e) => setSpoolRadiusText(e.target.value)}
                          />
                          <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                        </InputGroup>
                        <Button
                          size="sm"
                          colorScheme="odrive"
                          variant="outline"
                          onClick={handleUpdateSpoolRadius}
                          isDisabled={!spoolRadiusValid || spoolRadiusBusy}
                        >
                          Update
                        </Button>
                      </HStack>
                      <Text fontSize="0.65rem" color="gray.500" mt={1}>
                        Ruler-measured base radius. Affects Move, length telemetry, and Force Feedback
                        immediately.
                      </Text>
                    </Box>
                    <Stat>
                      <StatLabel color="gray.300">Correction factor (k)</StatLabel>
                      <StatNumber color="odrive.300" fontSize="md">
                        {cable?.k != null ? cable.k.toExponential(3) : '—'}
                      </StatNumber>
                      <Text fontSize="xs" color="gray.400">
                        m/rad{kBounds ? ` (bounds ${kBounds[0].toExponential(1)}..${kBounds[1].toExponential(1)})` : ''}
                      </Text>
                    </Stat>
                  </SimpleGrid>
                </VStack>
              </CardBody>
            </Card>
          </Collapse>
        </Box>

        {/* Live charts */}
        <SimpleGrid columns={{ base: 1, lg: 3 }} spacing={4}>
          <MiniChart label="Position" unit="turns" color="#63B3ED" data={chartData.position} />
          <MiniChart label="Velocity" unit="turns/s" color="#68D391" data={chartData.velocity} />
          <MiniChart label="Current (Iq)" unit="A" color="#F6AD55" data={chartData.current} />
        </SimpleGrid>
      </VStack>

      <Modal isOpen={resetOpen} onClose={closeReset} isCentered>
        <ModalOverlay />
        <ModalContent bg="gray.800">
          <ModalHeader color="odrive.300">Reset Cable Position?</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <Text color="gray.300" fontSize="sm">
              This clears the home reference and max-extension limit. Length-based control will be
              unavailable until homing runs again. The spool correction factor is not affected.
            </Text>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={closeReset}>Cancel</Button>
            <Button colorScheme="red" onClick={handleResetConfirmed} isLoading={busy} loadingText="Resetting…">
              Reset Position
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <Modal isOpen={resumeOpen} onClose={closeResume} isCentered>
        <ModalOverlay />
        <ModalContent bg="gray.800">
          <ModalHeader color="odrive.300">Resume Force Session?</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <Text color="gray.300" fontSize="sm">
              This clears the fault and returns to Armed (not re-engaged) — resistance stays off until you
              Engage again. The home reference and max-extension limit are not affected.
            </Text>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={closeResume}>Cancel</Button>
            <Button colorScheme="orange" onClick={handleResumeConfirmed} isLoading={forceBusy} loadingText="Resuming…">
              Resume
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  )
}

export default ExerciseTab
