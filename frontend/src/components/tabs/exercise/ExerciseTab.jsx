import { useEffect, useMemo, useState } from 'react'
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
} from '../../../api/exercise'
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

const ExerciseTab = ({ isActive = true }) => {
  const { status, series, connected } = useExerciseStatus(isActive)
  const control = status?.control
  const cable = status?.cable

  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [targetLengthText, setTargetLengthText] = useState('0.3')
  const [measuredLengthText, setMeasuredLengthText] = useState('')
  const [calibError, setCalibError] = useState(null)
  const [calibBusy, setCalibBusy] = useState(false)
  const [boardConstants, setBoardConstants] = useState(null)

  const { isOpen: resetOpen, onOpen: openReset, onClose: closeReset } = useDisclosure()
  const { isOpen: advancedOpen, onToggle: toggleAdvanced } = useDisclosure()

  useEffect(() => {
    getBoardConstants().then(setBoardConstants).catch(() => {})
  }, [])

  const sessionRunning = Boolean(control?.running && control?.mode === 'exercise')
  const anotherModeRunning = Boolean(control?.running && control?.mode !== 'exercise')
  const action = control?.extra?.action ?? null
  const homingState = control?.extra?.homing_state ?? null
  const busyAction = action === 'homing' || action === 'max_calibrating'

  const isHomed = cable?.is_homed ?? false
  const hasMax = cable?.has_max ?? false

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
  const handleMove = () => {
    if (!targetLengthValid) {
      setActionError('Target length must be a non-negative number')
      return
    }
    run(moveCable, targetLengthNumber)
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
              A {control?.mode} session is running from another tab — stop it before starting Exercise.
            </AlertDescription>
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

              <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                <Stat>
                  <StatLabel color="gray.300">Cable length</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">
                    {control?.extra?.cable_length_m != null ? control.extra.cable_length_m.toFixed(3) : '—'}
                  </StatNumber>
                  <Text fontSize="xs" color="gray.400">m</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Position</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{(latest?.position ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="gray.400">turns</Text>
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

        {/* Homing -- first live run must be attended, abortable, observable (spec §10) */}
        <Card bg="gray.800" variant="elevated">
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
            </VStack>
          </CardBody>
        </Card>

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
            </VStack>
          </CardBody>
        </Card>

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
              <HStack spacing={4} align="flex-end">
                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Target length</Text>
                  <InputGroup size="sm" w="160px">
                    <Input
                      type="text"
                      inputMode="decimal"
                      fontFamily="mono"
                      value={targetLengthText}
                      onChange={(e) => setTargetLengthText(e.target.value)}
                    />
                    <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                  </InputGroup>
                </Box>
                <Button
                  size="sm"
                  colorScheme="odrive"
                  onClick={handleMove}
                  isDisabled={!sessionRunning || !isHomed || !hasMax || busyAction || !targetLengthValid || busy}
                >
                  Move
                </Button>
              </HStack>
            </VStack>
          </CardBody>
        </Card>

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
                    <Stat>
                      <StatLabel color="gray.300">Spool radius (r0)</StatLabel>
                      <StatNumber color="odrive.300" fontSize="md">
                        {cable?.r0 != null ? cable.r0.toFixed(4) : '—'}
                      </StatNumber>
                      <Text fontSize="xs" color="gray.400">m</Text>
                    </Stat>
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
    </Box>
  )
}

export default ExerciseTab
