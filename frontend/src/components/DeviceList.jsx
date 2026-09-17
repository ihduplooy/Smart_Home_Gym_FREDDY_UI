import { useState, useEffect, useCallback, memo } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import {
  Box,
  VStack,
  HStack,
  Text,
  Card,
  CardBody,
  Button,
  Alert,
  AlertIcon,
  Badge,
  Divider,
  Icon,
  Tooltip,
  Collapse,
  useDisclosure,
  useToast,
} from '@chakra-ui/react'
import { InfoIcon, ChevronDownIcon, ChevronUpIcon } from '@chakra-ui/icons'
import { fetchDevices, connectDevice, disconnectDevice } from '../store/slices/deviceSlice'
import { useMotorControl } from '../hooks/useMotorControl'
import { getAxisStateName, getAxisStateDescription } from '../utils/configEnums'
import { getErrorDescription, getErrorColor, isErrorCritical, describeErrors } from '../utils/odriveErrors'
import { troubleshootingFor } from '../utils/troubleshooting'
import { createSpoolGeometry } from '../utils/cableGeometry'
import ErrorTroubleshootingModal from './modals/ErrorTroubleshootingModal'
import * as backend from '../api/backend'
import { getExerciseStatus, startExerciseSession, homeExercise, goHomeExercise, stopExercise } from '../api/exercise'
import '../styles/DeviceList.css'

// Slow poll, just to gate/inform the "Go Home" jog button below -- this
// component is mounted for the entire app lifetime, so this deliberately
// runs far below the 150ms rate an active Train/Control tab polls at.
const CABLE_STATUS_POLL_MS = 2000

const StatusBadge = memo(({ connected }) => (
  <Badge colorScheme={connected ? 'green' : 'gray'} variant="solid" fontSize="xs" px={2} py={1}>
    {connected ? 'Connected' : 'Available'}
  </Badge>
))
StatusBadge.displayName = 'StatusBadge'

const DeviceCard = memo(({ device, connected, connecting, onConnect, onDisconnect }) => (
  <Card w="100%" className="device-card" bg={connected ? 'odrive.700' : 'gray.700'} variant="elevated">
    <CardBody p={2}>
      <VStack align="stretch" spacing={1}>
        <HStack justify="space-between" align="center">
          <HStack spacing={2}>
            <Text fontSize="sm" fontWeight="bold">{device.path || 'ODrive'}</Text>
            <StatusBadge connected={connected} />
          </HStack>
          {connected ? (
            <Button size="xs" colorScheme="red" onClick={onDisconnect}>Disconnect</Button>
          ) : (
            <Button size="xs" colorScheme="green" onClick={() => onConnect(device)} isLoading={connecting} loadingText="Connecting">Connect</Button>
          )}
        </HStack>
        <Text fontSize="xs" color="gray.300" fontFamily="mono" noOfLines={1}>
          SR: {device.serial_number || 'Unknown'}
        </Text>
      </VStack>
    </CardBody>
  </Card>
))
DeviceCard.displayName = 'DeviceCard'

const ErrorRow = memo(({ label, code, kind, onClick }) => {
  if (!code) {
    return (
      <HStack justify="space-between">
        <Text fontSize="sm" color="gray.300">{label}:</Text>
        <Text fontSize="sm" fontWeight="bold" color="green.300">OK</Text>
      </HStack>
    )
  }
  const colorScheme = getErrorColor(code, kind)
  const critical = isErrorCritical(code, kind)
  return (
    <VStack spacing={1} align="stretch">
      <HStack justify="space-between">
        <Text fontSize="sm" color="gray.300">{label}:</Text>
        <HStack>
          <Badge
            colorScheme={colorScheme}
            variant="solid"
            fontSize="xs"
            cursor="pointer"
            _hover={{ opacity: 0.8 }}
            onClick={() => onClick(code, kind)}
          >
            0x{code.toString(16).toUpperCase()}
          </Badge>
          {critical && (
            <Tooltip label="Critical error - immediate attention required">
              <Icon as={InfoIcon} color="red.400" boxSize={3} />
            </Tooltip>
          )}
        </HStack>
      </HStack>
      <Text fontSize="xs" color={`${colorScheme}.300`} textAlign="right" maxW="220px">
        {getErrorDescription(code, kind)}
      </Text>
    </VStack>
  )
})
ErrorRow.displayName = 'ErrorRow'

const DeviceList = () => {
  const dispatch = useDispatch()
  const { availableDevices, connectedDevice, isConnected, isLoading } = useSelector((s) => s.device)
  const live = useSelector((s) => s.live)
  const { clearErrors } = useMotorControl()
  const toast = useToast()

  const { isOpen, onOpen, onClose } = useDisclosure()
  const [selectedError, setSelectedError] = useState(null)
  const [eStopBusy, setEStopBusy] = useState(false)
  const [resetBusy, setResetBusy] = useState(false)
  const [connectBusy, setConnectBusy] = useState(false)
  const [errorsExpanded, setErrorsExpanded] = useState(false)
  const [cableStatus, setCableStatus] = useState(null)
  const [goHomeBusy, setGoHomeBusy] = useState(false)
  const [homingBusy, setHomingBusy] = useState(false)

  // Slow background poll (see CABLE_STATUS_POLL_MS) so the "Go Home" button
  // below knows is_homed/r0/k/current position without needing a Train or
  // Control tab mounted -- this is the one place that info is needed outside
  // those tabs.
  useEffect(() => {
    if (!isConnected) {
      setCableStatus(null)
      return undefined
    }
    let cancelled = false
    let timer = null
    const poll = async () => {
      try {
        const s = await getExerciseStatus()
        if (!cancelled) setCableStatus(s)
      } catch {
        // Transient poll failure -- keep the last known status rather than
        // flickering the Go Home button's enabled state off and on.
      }
      if (!cancelled) timer = setTimeout(poll, CABLE_STATUS_POLL_MS)
    }
    poll()
    return () => {
      cancelled = true
      clearTimeout(timer)
      setCableStatus(null)
    }
  }, [isConnected])

  // Stable callbacks so the memoized DeviceCard / ErrorRow children can bail out
  // of re-rendering when only live-status numbers change.
  //
  // Verifies the device actually answers before flipping to "Connected" --
  // `d` here is just whatever the last Scan happened to return, which can be
  // stale (found live, 20 Aug 2026: a physically-unplugged board can still
  // be reported by discover_and_index()'s cache-first read for a while, and
  // this used to accept that at face value and celebrate a "Connected" toast
  // regardless -- readings then sit at zero with no indication anything's
  // wrong until you try to actually do something). A cheap vbus_voltage
  // read through the same /read route every other tab already uses is
  // enough to distinguish "actually reachable right now" from "was in the
  // last Scan's list."
  const handleConnect = useCallback(
    async (d) => {
      setConnectBusy(true)
      try {
        const result = await backend.readProperties(d.serial_number, ['vbus_voltage'])
        const probe = result?.vbus_voltage
        if (probe && typeof probe === 'object' && 'error' in probe) {
          throw new Error(probe.error)
        }
      } catch (e) {
        toast({
          title: 'Connect failed',
          description: e.message || 'Device did not respond. It may be unplugged, or the USB link may need a Restart Freddy.',
          status: 'error',
          duration: 6000,
        })
        return
      } finally {
        setConnectBusy(false)
      }
      dispatch(connectDevice(d))
      toast({ title: 'Connected', description: `ODrive ${d.serial_number || ''}`.trim(), status: 'success', duration: 2000 })
    },
    [dispatch, toast]
  )
  const handleDisconnect = useCallback(() => {
    dispatch(disconnectDevice())
    toast({ title: 'Disconnected', status: 'info', duration: 2000 })
  }, [dispatch, toast])

  // Always available regardless of which tab is open (this component lives in
  // the persistent sidebar) — idles the axis immediately, independent of
  // whatever put it in closed loop (a Control session or Dashboard's Enable).
  // Guards re-entrancy via the functional setState form (not a stale
  // `eStopBusy` closure read) so the button click and the spacebar shortcut
  // below can never both fire a request at once.
  const handleEmergencyStop = useCallback(async () => {
    let alreadyBusy = false
    setEStopBusy((busy) => {
      alreadyBusy = busy
      return true
    })
    if (alreadyBusy) return
    try {
      await backend.emergencyStop()
      toast({ title: 'Emergency stop sent', description: 'Axis idled.', status: 'warning', duration: 3000 })
    } catch (e) {
      toast({ title: 'Emergency stop failed', description: e.message, status: 'error', duration: 5000 })
    } finally {
      setEStopBusy(false)
    }
  }, [toast])

  // Spacebar shortcut (requested so the emergency stop is reachable without
  // aiming for the button) — attached at the window level so it fires from
  // any tab, not gated on isConnected: the backend route itself is an
  // "always-available panic button" regardless of connection state (see
  // /api/emergency-stop's own docstring), so the keyboard path matches that,
  // not the button's isConnected-gated visibility. Ignores the keypress
  // while focus is inside a text input/textarea/select/contenteditable so it
  // doesn't hijack normal typing (e.g. a numeric config field), and ignores
  // key-repeat (holding the key down) so one press only fires once.
  useEffect(() => {
    const isEditableTarget = (el) => {
      if (!el) return false
      const tag = el.tagName
      return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
    }
    const onKeyDown = (event) => {
      if (event.code !== 'Space' || event.repeat) return
      if (isEditableTarget(event.target)) return
      event.preventDefault() // space's default is page scroll / re-activating a focused button
      handleEmergencyStop()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [handleEmergencyStop])

  // Soft recovery for a stuck connection: forgets the backend's cached device
  // handle/lock and drops the frontend's own connection state, so the next
  // Connect starts completely fresh without needing a full backend restart.
  // Lighter-weight than "Restart Freddy" (top of sidebar) — doesn't touch the
  // motor, calibration, or the backend process; reach for Restart Freddy
  // instead if this doesn't clear things up.
  const handleResetInterface = useCallback(async () => {
    setResetBusy(true)
    try {
      await backend.resetInterface()
      dispatch(disconnectDevice())
      toast({ title: 'Interface reset', description: 'Reconnect when ready.', status: 'info', duration: 3000 })
    } catch (e) {
      toast({ title: 'Reset failed', description: e.message, status: 'error', duration: 5000 })
    } finally {
      setResetBusy(false)
    }
  }, [dispatch, toast])

  // Jog the cable back to its home position from anywhere in the app --
  // requested so a cable left "out" mid-task doesn't require reopening the
  // Train tab's Settings/Startup section and re-homing. Calls the same
  // current-threshold "go_home" action the Train tab's own Go Home button
  // uses (core/cable/exercise_mode.py's _apply_go_home) -- one "Go Home"
  // behavior everywhere, not a separate plain position-move like this used
  // to do. Arms a session first if none is running; releases it again once
  // the cable arrives so this doesn't leave a lingering Exercise session
  // behind for the Train tab's Settings/Startup to trip over.
  const handleGoHome = useCallback(async () => {
    setGoHomeBusy(true)
    try {
      let s = await getExerciseStatus()
      if (!s.cable.is_homed) throw new Error('Cable is not homed yet.')
      if (s.control.running && s.control.mode !== 'exercise') {
        throw new Error(`A ${s.control.mode} session is running — stop it first.`)
      }
      if (!(s.control.running && s.control.mode === 'exercise')) {
        await startExerciseSession()
      }
      await goHomeExercise()
      for (let i = 0; i < 300; i++) {
        await new Promise((r) => setTimeout(r, 200))
        s = await getExerciseStatus()
        setCableStatus(s)
        if (!(s.control.running && s.control.mode === 'exercise')) break
        if (s.control.extra?.action !== 'homing') break
      }
      if (s.control.running && s.control.mode === 'exercise') await stopExercise()
      setCableStatus(await getExerciseStatus())
      toast({ title: 'Cable back at home', status: 'success', duration: 2000 })
    } catch (e) {
      toast({ title: 'Go Home failed', description: e.message, status: 'error', duration: 5000 })
    } finally {
      setGoHomeBusy(false)
    }
  }, [toast])

  // Perform a fresh Home (reel in until current threshold, latch a NEW home
  // reference) from anywhere in the app -- so the very first home of a
  // session doesn't require opening the Setup tab. Same
  // arm-session/poll/release shape as handleGoHome above, just the "home"
  // action (core/cable/exercise_mode.py's _apply_home) instead of
  // "go_home" -- and, unlike Go Home, doesn't require an existing home
  // first (that's the point).
  const handleHoming = useCallback(async () => {
    setHomingBusy(true)
    try {
      let s = await getExerciseStatus()
      if (s.control.running && s.control.mode !== 'exercise') {
        throw new Error(`A ${s.control.mode} session is running — stop it first.`)
      }
      if (!(s.control.running && s.control.mode === 'exercise')) {
        await startExerciseSession()
      }
      await homeExercise()
      for (let i = 0; i < 300; i++) {
        await new Promise((r) => setTimeout(r, 200))
        s = await getExerciseStatus()
        setCableStatus(s)
        if (!(s.control.running && s.control.mode === 'exercise')) break
        if (s.control.extra?.action !== 'homing') break
      }
      if (s.control.running && s.control.mode === 'exercise') await stopExercise()
      setCableStatus(await getExerciseStatus())
      toast({ title: 'Homed', status: 'success', duration: 2000 })
    } catch (e) {
      toast({ title: 'Homing failed', description: e.message, status: 'error', duration: 5000 })
    } finally {
      setHomingBusy(false)
    }
  }, [toast])

  // Scanning is manual only (Scan button below) — no scan on mount and no
  // periodic re-scan. Press Scan once the device is connected and powered on.

  const errors = {
    axis: live.axis_error,
    motor: live.motor_error,
    encoder: live.encoder_error,
    controller: live.controller_error,
    sensorless: live.sensorless_error,
  }
  const hasAnyErrors = Object.values(errors).some((e) => e !== 0)
  const activeErrorCount = Object.values(errors).filter((e) => e !== 0).length

  const handleErrorClick = useCallback((code, kind) => {
    const decoded = describeErrors(kind, code)[0]
    if (decoded) {
      setSelectedError({ ...decoded, group: kind })
      onOpen()
    }
  }, [onOpen])

  const axisColor = (state) => {
    if (state === 8) return 'green'
    if (state === 1) return 'blue'
    if (state >= 2 && state <= 7) return 'yellow'
    return 'red'
  }

  const isHomed = cableStatus?.cable?.is_homed ?? false
  const anotherModeRunning = Boolean(cableStatus?.control?.running && cableStatus?.control?.mode !== 'exercise')
  const homeTurns = cableStatus?.cable?.home_turns
  const r0 = cableStatus?.cable?.r0
  // Computed from the fast, always-on `live.encoder_pos` (150ms, same
  // WebSocket telemetry Encoder Pos below reads) combined with the
  // slow-polled calibration constants above -- NOT from
  // cableStatus.cable.cable_position_turns, which is only as fresh as the
  // 2s cableStatus poll and was the reason this lagged Train tab's own
  // Cable Position (which recomputes from its own fast poll). Same
  // createSpoolGeometry/lengthFromTurnsDelta growth-aware conversion
  // useTrainTelemetry.js already uses, so both stay in sync.
  const cablePositionM =
    isHomed && homeTurns != null && r0
      ? createSpoolGeometry(
          r0,
          cableStatus.cable.k ?? 0,
          (cableStatus.cable.spool_model?.growth_points ?? []).map((p) => [p.turns_from_home, p.length_m]),
          cableStatus.cable.spool_model?.min_effective_radius_m ?? 0
        ).lengthFromTurnsDelta(live.encoder_pos - homeTurns)
      : null
  const goHomeDisabledReason = !isHomed
    ? 'Home the cable first (Homing button below, or the Setup tab).'
    : anotherModeRunning
      ? `A ${cableStatus.control.mode} session is running — stop it first.`
      : 'Jog the cable back to its home position.'
  const homingDisabledReason = anotherModeRunning
    ? `A ${cableStatus?.control?.mode} session is running — stop it first.`
    : 'Reel in and set this as the new home position.'

  return (
    <Box className="device-list">
      <VStack spacing={4} align="stretch">
        <HStack justify="space-between">
          <Text fontSize="lg" fontWeight="bold" color="odrive.300">ODrive Device</Text>
          <HStack spacing={2}>
            <Tooltip label="Forget the cached connection and start fresh, without restarting the backend. If that doesn't help, use Restart Freddy (top of sidebar) instead.">
              <Button size="sm" variant="outline" onClick={handleResetInterface} isLoading={resetBusy} loadingText="Resetting">
                Reset
              </Button>
            </Tooltip>
            <Button size="sm" colorScheme="odrive" onClick={() => dispatch(fetchDevices())} isLoading={isLoading} loadingText="Scanning">
              Scan
            </Button>
          </HStack>
        </HStack>

        <Box>
          {availableDevices.length === 0 ? (
            <Alert status="info" variant="subtle">
              <AlertIcon />
              No ODrive device found. Make sure your device is connected.
            </Alert>
          ) : (
            <DeviceCard
              device={availableDevices[0]}
              connected={isConnected && connectedDevice?.serial_number === availableDevices[0].serial_number}
              connecting={connectBusy}
              onConnect={handleConnect}
              onDisconnect={handleDisconnect}
            />
          )}
        </Box>

        {isConnected && (
          <>
            <Divider />
            <Box>
              <Button
                width="100%"
                size="md"
                colorScheme="red"
                variant="solid"
                fontWeight="bold"
                mb={3}
                onClick={handleEmergencyStop}
                isLoading={eStopBusy}
                loadingText="Stopping"
              >
                EMERGENCY STOP
              </Button>
              <Text fontSize="xs" color="gray.500" textAlign="center" mt={-2} mb={3}>
                or press Space anywhere
              </Text>
              <Text fontSize="md" fontWeight="bold" mb={2} color="white">Device Status</Text>
              <VStack spacing={2} align="stretch">
                <HStack justify="space-between">
                  <Text fontSize="sm" color="gray.300">Vbus Voltage:</Text>
                  <Text fontSize="sm" fontWeight="bold">{live.vbus_voltage.toFixed(1)} V</Text>
                </HStack>
                <Box>
                  <HStack justify="space-between">
                    <Text fontSize="sm" color="gray.300">Axis 0 State:</Text>
                    <Badge colorScheme={axisColor(live.axis_state)}>{getAxisStateName(live.axis_state)}</Badge>
                  </HStack>
                  <Text fontSize="xs" color="gray.500" textAlign="right">{getAxisStateDescription(live.axis_state)}</Text>
                </Box>
                <Box>
                  <Text fontSize="sm" color="gray.300" mb={1}>Current:</Text>
                  <HStack justify="space-between">
                    <VStack spacing={0} align="start">
                      <Text fontSize="2xs" color="gray.500">Motor</Text>
                      <Text fontSize="sm" fontWeight="bold">{live.motor_current.toFixed(2)} A</Text>
                    </VStack>
                    <VStack spacing={0} align="end">
                      <Text fontSize="2xs" color="gray.500">Supply</Text>
                      <Text fontSize="sm" fontWeight="bold">{live.ibus.toFixed(2)} A</Text>
                    </VStack>
                  </HStack>
                </Box>
                <Box>
                  <Text fontSize="sm" color="gray.300" mb={1}>Position:</Text>
                  <HStack justify="space-between">
                    <VStack spacing={0} align="start">
                      <Text fontSize="2xs" color="gray.500">Encoder</Text>
                      <Text fontSize="sm" fontWeight="bold">{live.encoder_pos.toFixed(2)}</Text>
                    </VStack>
                    <VStack spacing={0} align="end">
                      <Text fontSize="2xs" color="gray.500">Cable</Text>
                      <Text fontSize="sm" fontWeight="bold">{cablePositionM != null ? `${cablePositionM.toFixed(3)} m` : '—'}</Text>
                    </VStack>
                  </HStack>
                </Box>
              </VStack>

              <HStack mt={3} spacing={2}>
                <Tooltip label={homingDisabledReason}>
                  <Button
                    flex={1}
                    size="sm"
                    variant="outline"
                    colorScheme="odrive"
                    onClick={handleHoming}
                    isLoading={homingBusy}
                    loadingText="Homing…"
                    isDisabled={anotherModeRunning}
                  >
                    Homing
                  </Button>
                </Tooltip>
                <Tooltip label={goHomeDisabledReason}>
                  <Button
                    flex={1}
                    size="sm"
                    variant="outline"
                    colorScheme="odrive"
                    onClick={handleGoHome}
                    isLoading={goHomeBusy}
                    loadingText="Going home…"
                    isDisabled={!isHomed || anotherModeRunning}
                  >
                    Go Home
                  </Button>
                </Tooltip>
              </HStack>

              {hasAnyErrors && (
                <Button size="xs" colorScheme="red" variant="outline" width="100%" mt={3} onClick={clearErrors}>
                  Clear All Errors
                </Button>
              )}

              <Box mt={3}>
                <HStack
                  justify="space-between"
                  cursor="pointer"
                  onClick={() => setErrorsExpanded((v) => !v)}
                >
                  <HStack spacing={1}>
                    <Icon as={errorsExpanded ? ChevronUpIcon : ChevronDownIcon} color="gray.400" />
                    <Text fontSize="sm" color="gray.300">Errors:</Text>
                  </HStack>
                  <Badge colorScheme={hasAnyErrors ? 'red' : 'green'} variant="solid" fontSize="xs">
                    {hasAnyErrors ? `${activeErrorCount} Active` : 'None'}
                  </Badge>
                </HStack>
                <Collapse in={errorsExpanded} animateOpacity>
                  <VStack spacing={2} align="stretch" mt={2} pl={2} borderLeft="2px solid" borderColor="gray.600">
                    <ErrorRow label="Axis" code={errors.axis} kind="axis" onClick={handleErrorClick} />
                    <ErrorRow label="Motor" code={errors.motor} kind="motor" onClick={handleErrorClick} />
                    <ErrorRow label="Encoder" code={errors.encoder} kind="encoder" onClick={handleErrorClick} />
                    <ErrorRow label="Controller" code={errors.controller} kind="controller" onClick={handleErrorClick} />
                    <ErrorRow label="Sensorless" code={errors.sensorless} kind="sensorless" onClick={handleErrorClick} />
                  </VStack>
                </Collapse>
              </Box>
            </Box>
          </>
        )}
      </VStack>

      <ErrorTroubleshootingModal
        isOpen={isOpen}
        onClose={onClose}
        error={selectedError}
        guide={selectedError ? troubleshootingFor(selectedError.group, selectedError.flag) : null}
      />
    </Box>
  )
}

export default DeviceList