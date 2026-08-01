import { useEffect, useRef, useState } from 'react'
import {
  Box, VStack, HStack, Text, Heading, Badge, Button, Card, CardHeader, CardBody,
  Input, InputGroup, InputRightAddon, Alert, AlertIcon, AlertDescription,
  Collapse, useDisclosure, Switch, FormControl, FormLabel,
} from '@chakra-ui/react'
import { ChevronDownIcon, ChevronRightIcon } from '@chakra-ui/icons'
import {
  startExerciseSession, homeExercise, abortHoming,
  startMaxCalibration, confirmMax, cancelMaxCalibration,
  stopExercise, calibrateSpoolK, updateHomingSettings,
  updateSpoolRadius, updateSpoolK, setMaxExtensionManual,
} from '../../../api/exercise'
import { updateTrainSettings } from '../../../api/train'
import SpoolGrowthCalibration from './SpoolGrowthCalibration'
import SpoolModelDiagnostics from './SpoolModelDiagnostics'

// Train's Settings/Startup section (spec §3) -- reuses Exercise's existing
// homing/max-extension/spool-calibration routes directly rather than
// duplicating that machinery: they all operate on the one shared
// cable_state regardless of which ControlSession mode is currently active,
// and `status` here is the same /api/train/status response TrainTab already
// polls, so `status.control.mode` reads "exercise" while this section's
// setup flow is driving the shared session, and "train" once a Train
// session is running -- no second poll loop needed.
//
// Manual jogging used to live in this section too; removed 25 July 2026 at
// the user's request -- it was coupled to a running Train session in a way
// that didn't make sense, and the Control tab's own Position mode already
// covers manual moves better. See docs/decisions.md ("Train tab
// refinements").
const HOMING_STATE_LABEL = {
  startup_grace: 'Starting…',
  detecting: 'Reeling in…',
  homed: 'Homed',
  fault_travel_exceeded: 'Fault: travel bound exceeded',
  fault_timeout: 'Fault: timed out',
  aborted: 'Aborted',
}

const TrainSettingsSection = ({ status, trainSessionRunning }) => {
  const { isOpen, onToggle } = useDisclosure({ defaultIsOpen: true })

  const [setupError, setSetupError] = useState(null)
  const [setupBusy, setSetupBusy] = useState(false)

  const [measuredLengthText, setMeasuredLengthText] = useState('')
  const [calibError, setCalibError] = useState(null)
  const [calibBusy, setCalibBusy] = useState(false)

  const [maxLengthText, setMaxLengthText] = useState('')
  const [maxLengthError, setMaxLengthError] = useState(null)
  const [maxLengthBusy, setMaxLengthBusy] = useState(false)

  const [r0Text, setR0Text] = useState('')
  const [r0Error, setR0Error] = useState(null)
  const [r0Busy, setR0Busy] = useState(false)

  const [kText, setKText] = useState('')
  const [kError, setKError] = useState(null)
  const [kBusy, setKBusy] = useState(false)

  const [enforcedBusy, setEnforcedBusy] = useState(false)
  const [homeEnforcedBusy, setHomeEnforcedBusy] = useState(false)
  const [bufferText, setBufferText] = useState('')
  const [bufferError, setBufferError] = useState(null)
  const [bufferBusy, setBufferBusy] = useState(false)

  const [homingVelocityText, setHomingVelocityText] = useState('')
  const [homingThresholdText, setHomingThresholdText] = useState('')
  const [homingSettingsError, setHomingSettingsError] = useState(null)
  const [homingSettingsBusy, setHomingSettingsBusy] = useState(false)

  const bufferInitialized = useRef(false)
  useEffect(() => {
    if (bufferInitialized.current || status?.cable?.train_telemetry_buffer_s == null) return
    setBufferText(String(status.cable.train_telemetry_buffer_s))
    bufferInitialized.current = true
  }, [status?.cable?.train_telemetry_buffer_s])

  const homingSettingsInitialized = useRef(false)
  useEffect(() => {
    if (homingSettingsInitialized.current || status?.cable?.homing_velocity_turns_s == null) return
    setHomingVelocityText(String(status.cable.homing_velocity_turns_s))
    setHomingThresholdText(String(status.cable.homing_current_threshold_a))
    homingSettingsInitialized.current = true
  }, [status?.cable?.homing_velocity_turns_s, status?.cable?.homing_current_threshold_a])

  const r0Initialized = useRef(false)
  useEffect(() => {
    if (r0Initialized.current || status?.cable?.r0 == null) return
    setR0Text(String(status.cable.r0))
    r0Initialized.current = true
  }, [status?.cable?.r0])

  const control = status?.control
  const cable = status?.cable
  const setupSessionRunning = Boolean(control?.running && control?.mode === 'exercise')
  const anotherModeRunning = Boolean(control?.running && !trainSessionRunning && !setupSessionRunning)
  const action = setupSessionRunning ? control?.extra?.action ?? null : null
  const homingState = setupSessionRunning ? control?.extra?.homing_state ?? null : null
  const isHomed = cable?.is_homed ?? false
  const hasMax = cable?.has_max ?? false

  const run = async (fn, ...args) => {
    setSetupError(null)
    setSetupBusy(true)
    try {
      await fn(...args)
    } catch (e) {
      setSetupError(e.message)
    } finally {
      setSetupBusy(false)
    }
  }

  const handleCalibrate = async () => {
    const measured = Number(measuredLengthText)
    if (measuredLengthText === '' || !Number.isFinite(measured) || measured < 0) {
      setCalibError('Measured length must be a non-negative number')
      return
    }
    setCalibError(null)
    setCalibBusy(true)
    try {
      await calibrateSpoolK(measured)
    } catch (e) {
      setCalibError(e.message)
    } finally {
      setCalibBusy(false)
    }
  }

  const handleSetMaxExtensionManual = async () => {
    const length = Number(maxLengthText)
    if (maxLengthText === '' || !Number.isFinite(length) || length < 0) {
      setMaxLengthError('Length must be a non-negative number')
      return
    }
    setMaxLengthError(null)
    setMaxLengthBusy(true)
    try {
      await setMaxExtensionManual(length)
      setMaxLengthText('')
    } catch (e) {
      setMaxLengthError(e.message)
    } finally {
      setMaxLengthBusy(false)
    }
  }

  const r0Number = Number(r0Text)
  const r0Valid = r0Text !== '' && Number.isFinite(r0Number) && r0Number > 0
  const handleUpdateR0 = async () => {
    if (!r0Valid) {
      setR0Error('Spool radius must be a positive number')
      return
    }
    setR0Error(null)
    setR0Busy(true)
    try {
      await updateSpoolRadius(r0Number)
    } catch (e) {
      setR0Error(e.message)
    } finally {
      setR0Busy(false)
    }
  }

  const kNumber = Number(kText)
  const kValid = kText !== '' && Number.isFinite(kNumber)
  const handleUpdateK = async () => {
    if (!kValid) {
      setKError('k must be a number')
      return
    }
    setKError(null)
    setKBusy(true)
    try {
      await updateSpoolK(kNumber)
    } catch (e) {
      setKError(e.message)
    } finally {
      setKBusy(false)
    }
  }

  const handleToggleEnforced = async () => {
    setEnforcedBusy(true)
    try {
      await updateTrainSettings({ maxExtensionEnforced: !cable?.train_max_extension_enforced })
    } catch (e) {
      setSetupError(e.message)
    } finally {
      setEnforcedBusy(false)
    }
  }

  const handleToggleHomeEnforced = async () => {
    setHomeEnforcedBusy(true)
    try {
      await updateTrainSettings({ homeGuardEnforced: !cable?.train_home_guard_enforced })
    } catch (e) {
      setSetupError(e.message)
    } finally {
      setHomeEnforcedBusy(false)
    }
  }

  const bufferNumber = Number(bufferText)
  const bufferValid = bufferText !== '' && Number.isFinite(bufferNumber) && bufferNumber > 0
  const handleUpdateBuffer = async () => {
    if (!bufferValid) {
      setBufferError('Buffer duration must be a positive number of seconds')
      return
    }
    setBufferError(null)
    setBufferBusy(true)
    try {
      await updateTrainSettings({ telemetryBufferS: bufferNumber })
    } catch (e) {
      setBufferError(e.message)
    } finally {
      setBufferBusy(false)
    }
  }

  const homingVelocityNumber = Number(homingVelocityText)
  const homingVelocityValid = homingVelocityText !== '' && Number.isFinite(homingVelocityNumber) && homingVelocityNumber > 0
  const homingThresholdNumber = Number(homingThresholdText)
  const homingThresholdValid = homingThresholdText !== '' && Number.isFinite(homingThresholdNumber) && homingThresholdNumber > 0
  const homingSettingsValid = homingVelocityValid && homingThresholdValid
  const handleUpdateHomingSettings = async () => {
    if (!homingSettingsValid) {
      setHomingSettingsError('Homing velocity and current threshold must both be positive numbers')
      return
    }
    setHomingSettingsError(null)
    setHomingSettingsBusy(true)
    try {
      await updateHomingSettings({ velocityTurnsS: homingVelocityNumber, currentThresholdA: homingThresholdNumber })
    } catch (e) {
      setHomingSettingsError(e.message)
    } finally {
      setHomingSettingsBusy(false)
    }
  }

  return (
    <Box>
      <Button variant="ghost" size="sm" leftIcon={isOpen ? <ChevronDownIcon /> : <ChevronRightIcon />} onClick={onToggle} color="odrive.300">
        {isOpen ? 'Hide' : 'Show'} Settings / Startup
      </Button>
      <Collapse in={isOpen} animateOpacity>
        <Card bg="gray.800" variant="elevated" mt={2}>
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="white">Settings / Startup</Heading>
              <HStack>
                <Badge colorScheme={isHomed ? 'green' : 'gray'} variant="outline">{isHomed ? 'homed' : 'not homed'}</Badge>
                {setupSessionRunning && (
                  <Button size="sm" colorScheme="red" onClick={() => run(stopExercise)} isDisabled={setupBusy}>
                    Stop setup session
                  </Button>
                )}
              </HStack>
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={4}>
              {setupError && (
                <Alert status="error" variant="left-accent">
                  <AlertIcon /><AlertDescription>{setupError}</AlertDescription>
                </Alert>
              )}
              {anotherModeRunning && (
                <Alert status="warning" variant="left-accent">
                  <AlertIcon />
                  <AlertDescription>
                    A {control?.mode} session is running from another tab — stop it before homing or calibrating here.
                  </AlertDescription>
                </Alert>
              )}
              {!setupSessionRunning && (
                <Text fontSize="xs" color="gray.500">
                  Start a setup session to home, calibrate, or adjust homing settings below.
                </Text>
              )}

              {/* Homing -- same routes/state machine ExerciseTab.jsx uses */}
              <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
                <HStack justify="space-between" mb={2}>
                  <Text fontSize="sm" fontWeight="semibold" color="gray.200">Homing</Text>
                  {setupSessionRunning && (
                    <Badge colorScheme={action === 'homing' ? 'orange' : isHomed ? 'green' : 'gray'} variant="solid">
                      {action === 'homing' ? (HOMING_STATE_LABEL[homingState] ?? 'Homing…') : isHomed ? 'Homed' : 'Not homed'}
                    </Badge>
                  )}
                </HStack>
                <HStack spacing={3} wrap="wrap" mb={3}>
                  {!setupSessionRunning ? (
                    <Button size="sm" colorScheme="odrive" onClick={() => run(startExerciseSession)} isDisabled={setupBusy || trainSessionRunning || anotherModeRunning}>
                      Start setup session
                    </Button>
                  ) : (
                    <>
                      <Button size="sm" colorScheme="odrive" onClick={() => run(homeExercise)} isDisabled={setupBusy || action === 'homing'}>Home</Button>
                      <Button size="sm" colorScheme="red" variant="outline" onClick={() => run(abortHoming)} isDisabled={setupBusy || action !== 'homing'}>Abort</Button>
                    </>
                  )}
                </HStack>

                {homingSettingsError && (
                  <Alert status="error" variant="left-accent" mb={2}><AlertIcon /><AlertDescription>{homingSettingsError}</AlertDescription></Alert>
                )}
                <Text fontSize="xs" color="gray.400" mb={2}>
                  Homing settings — live-adjustable, persisted, take effect on the next Home.
                </Text>
                <HStack spacing={3} align="flex-end">
                  <Box>
                    <Text fontSize="xs" color="gray.400" mb={1}>Homing velocity</Text>
                    <InputGroup size="sm" w="130px">
                      <Input type="text" inputMode="decimal" fontFamily="mono" value={homingVelocityText} onChange={(e) => setHomingVelocityText(e.target.value)} />
                      <InputRightAddon px={2} fontSize="xs">t/s</InputRightAddon>
                    </InputGroup>
                  </Box>
                  <Box>
                    <Text fontSize="xs" color="gray.400" mb={1}>Current threshold</Text>
                    <InputGroup size="sm" w="130px">
                      <Input type="text" inputMode="decimal" fontFamily="mono" value={homingThresholdText} onChange={(e) => setHomingThresholdText(e.target.value)} />
                      <InputRightAddon px={2} fontSize="xs">A</InputRightAddon>
                    </InputGroup>
                  </Box>
                  <Button size="sm" onClick={handleUpdateHomingSettings} isLoading={homingSettingsBusy}>Update</Button>
                </HStack>
              </Box>

              {/* Max-extension calibration + enforcement toggle, grouped together */}
              <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
                <HStack justify="space-between" mb={2}>
                  <Text fontSize="sm" fontWeight="semibold" color="gray.200">Max-extension calibration</Text>
                  <Badge colorScheme={hasMax ? 'green' : 'gray'} variant="outline">{hasMax ? 'calibrated' : 'not set'}</Badge>
                </HStack>
                <HStack spacing={3} wrap="wrap" mb={3}>
                  <Button size="sm" colorScheme="odrive" onClick={() => run(startMaxCalibration)} isDisabled={!setupSessionRunning || setupBusy || !isHomed || action === 'max_calibrating'}>
                    Start
                  </Button>
                  <Button size="sm" colorScheme="green" onClick={() => run(confirmMax)} isDisabled={!setupSessionRunning || setupBusy || action !== 'max_calibrating'}>
                    Confirm
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => run(cancelMaxCalibration)} isDisabled={!setupSessionRunning || setupBusy || action !== 'max_calibrating'}>
                    Cancel
                  </Button>
                </HStack>

                <Text fontSize="xs" color="gray.400" mb={1}>
                  Or enter the max extension directly, if it's already known (measured by hand, or set
                  previously on the same rig) -- no physical pull required.
                </Text>
                {maxLengthError && (
                  <Alert status="error" variant="left-accent" mb={2}><AlertIcon /><AlertDescription>{maxLengthError}</AlertDescription></Alert>
                )}
                <HStack spacing={3} align="flex-end" mb={3}>
                  <InputGroup size="sm" w="130px">
                    <Input type="text" inputMode="decimal" fontFamily="mono" value={maxLengthText} onChange={(e) => setMaxLengthText(e.target.value)} />
                    <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                  </InputGroup>
                  <Button size="sm" onClick={handleSetMaxExtensionManual} isLoading={maxLengthBusy} isDisabled={!isHomed}>
                    Set directly
                  </Button>
                </HStack>

                <FormControl display="flex" alignItems="center">
                  <FormLabel htmlFor="train-enforce-home" mb="0" fontSize="sm" color="gray.200">
                    Enforce home-side guard during Train
                  </FormLabel>
                  <Switch
                    id="train-enforce-home"
                    colorScheme="odrive"
                    isChecked={Boolean(cable?.train_home_guard_enforced)}
                    onChange={handleToggleHomeEnforced}
                    isDisabled={homeEnforcedBusy}
                  />
                </FormControl>
                <Text fontSize="xs" color="gray.500" mt={1} mb={3}>
                  When on, a Train session hard-stops if the cable goes past the home end of the calibrated range.
                  Independent of the max-extension toggle below.{' '}
                  <Text as="span" color="gray.400" fontStyle="italic">
                    Only takes effect once a Train session is running — has no effect on the setup session above
                    (homing/calibration), which always enforces its own always-on guard regardless of this toggle.
                  </Text>
                </Text>

                <FormControl display="flex" alignItems="center">
                  <FormLabel htmlFor="train-enforce-max" mb="0" fontSize="sm" color="gray.200">
                    Enforce max-extension guard during Train
                  </FormLabel>
                  <Switch
                    id="train-enforce-max"
                    colorScheme="odrive"
                    isChecked={Boolean(cable?.train_max_extension_enforced)}
                    onChange={handleToggleEnforced}
                    isDisabled={enforcedBusy}
                  />
                </FormControl>
                <Text fontSize="xs" color="gray.500" mt={1}>
                  When on, a Train session hard-stops if the cable goes past the max end of the calibrated range.{' '}
                  <Text as="span" color="gray.400" fontStyle="italic">
                    Only takes effect once a Train session is running — has no effect on the setup session above
                    (homing/calibration), which always enforces its own always-on guard regardless of this toggle.
                  </Text>
                </Text>
              </Box>

              {/* Spool calibration: radius (r0) + wrap-growth correction (k) */}
              <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
                <Text fontSize="sm" fontWeight="semibold" color="gray.200" mb={2}>Spool calibration</Text>

                <Text fontSize="xs" color="gray.400" mb={1}>Spool radius (r0)</Text>
                {r0Error && (
                  <Alert status="error" variant="left-accent" mb={2}><AlertIcon /><AlertDescription>{r0Error}</AlertDescription></Alert>
                )}
                <HStack spacing={3} align="flex-end" mb={4}>
                  <InputGroup size="sm" w="130px">
                    <Input type="text" inputMode="decimal" fontFamily="mono" value={r0Text} onChange={(e) => setR0Text(e.target.value)} />
                    <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                  </InputGroup>
                  <Button size="sm" onClick={handleUpdateR0} isLoading={r0Busy}>Update</Button>
                  <Text fontSize="xs" color="gray.400">
                    Bare spool radius, before any cable/webbing wrap builds up. Affects every force/velocity conversion.
                  </Text>
                </HStack>

                <Text fontSize="xs" color="gray.400" mb={1}>
                  Wrap-growth correction (k) — how much the effective radius grows per turn as cable wraps on top of itself.
                </Text>
                {calibError && (
                  <Alert status="error" variant="left-accent" mb={2}><AlertIcon /><AlertDescription>{calibError}</AlertDescription></Alert>
                )}
                <HStack spacing={3} align="flex-end" mb={3}>
                  <Box>
                    <Text fontSize="xs" color="gray.400" mb={1}>Measured length</Text>
                    <InputGroup size="sm" w="130px">
                      <Input type="text" inputMode="decimal" fontFamily="mono" value={measuredLengthText} onChange={(e) => setMeasuredLengthText(e.target.value)} />
                      <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
                    </InputGroup>
                  </Box>
                  <Button size="sm" onClick={handleCalibrate} isLoading={calibBusy} isDisabled={!setupSessionRunning || !isHomed}>
                    Calibrate from measurement
                  </Button>
                  <Text fontSize="xs" color="gray.400">current k: {cable?.k != null ? cable.k.toFixed(6) : '—'}</Text>
                </HStack>
                <Text fontSize="xs" color="gray.400" mb={1}>
                  Or set k directly (already know it from a previous calibration) — still checked against the same
                  physical-plausibility range as above.
                </Text>
                {kError && (
                  <Alert status="error" variant="left-accent" mb={2}><AlertIcon /><AlertDescription>{kError}</AlertDescription></Alert>
                )}
                <HStack spacing={3} align="flex-end">
                  <InputGroup size="sm" w="130px">
                    <Input type="text" inputMode="decimal" fontFamily="mono" value={kText} onChange={(e) => setKText(e.target.value)} />
                    <InputRightAddon px={2} fontSize="xs">m/rad</InputRightAddon>
                  </InputGroup>
                  <Button size="sm" onClick={handleUpdateK} isLoading={kBusy}>Set k</Button>
                </HStack>
              </Box>

              <SpoolGrowthCalibration status={status} trainSessionRunning={trainSessionRunning} />

              {/* Graph telemetry buffer duration */}
              <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
                <Text fontSize="sm" fontWeight="semibold" color="gray.200" mb={2}>Graph history buffer</Text>
                {bufferError && (
                  <Alert status="error" variant="left-accent" mb={2}><AlertIcon /><AlertDescription>{bufferError}</AlertDescription></Alert>
                )}
                <HStack spacing={3} align="flex-end">
                  <InputGroup size="sm" w="130px">
                    <Input type="text" inputMode="decimal" fontFamily="mono" value={bufferText} onChange={(e) => setBufferText(e.target.value)} />
                    <InputRightAddon px={2} fontSize="xs">s</InputRightAddon>
                  </InputGroup>
                  <Button size="sm" onClick={handleUpdateBuffer} isLoading={bufferBusy}>Update</Button>
                </HStack>
              </Box>

              <SpoolModelDiagnostics status={status} />
            </VStack>
          </CardBody>
        </Card>
      </Collapse>
    </Box>
  )
}

export default TrainSettingsSection
