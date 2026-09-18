import { useEffect, useRef, useState } from 'react'
import {
  Box, VStack, HStack, Text, Heading, Badge, Button, Card, CardHeader, CardBody,
  Input, InputGroup, InputRightAddon, Alert, AlertIcon, AlertDescription,
  Switch, FormControl, FormLabel,
  AlertDialog, AlertDialogOverlay, AlertDialogContent, AlertDialogHeader,
  AlertDialogBody, AlertDialogFooter, useDisclosure,
} from '@chakra-ui/react'
import { useAnticoggingStatus } from '../hooks/useAnticoggingStatus'
import { getBoardConstants } from '../api/backend'
import {
  startAnticoggingCalibration, abortAnticoggingCalibration, setAnticoggingEnabled,
} from '../api/anticogging'

// Lives in the Configuration tab's "Motor Controls" sub-tab (frontend/src/
// components/tabs/config wizard/ConfigurationTab.jsx), alongside
// MotorControlsCard -- same family of quick hardware actions (enable/
// disable, motor/encoder calibration, clear errors, save & reboot), even
// though it's wired independently rather than through useCalibration's
// axis-state-polling mechanism (that hook watches the axis return to IDLE;
// anti-cogging calibration instead polls a dedicated
// controller.config.anticogging.calib_anticogging boolean and needs its own
// gain-raise/restore + save+reboot sequence -- see
// backend/app/anticogging_routes.py).
//
// Deliberately independent of any ControlSession mode/experiment -- it's a
// one-shot, firmware-driven routine (the motor spins autonomously once
// controller.start_anticogging_calibration() is called; nothing here
// commands it tick by tick) that writes NVM config and reboots the board.
// Reads `control_session_running` from its own polled status (backend
// already computes it) rather than taking it as a prop, so this card has no
// dependency on whichever tab happens to render it.
const STATE_COLORS = { idle: 'gray', running: 'yellow', done: 'green', aborted: 'orange', failed: 'red' }

const AnticoggingCalibrationCard = ({ isActive = true }) => {
  const status = useAnticoggingStatus(isActive)

  const [defaults, setDefaults] = useState(null)
  const [posGainMultText, setPosGainMultText] = useState('')
  const [velIntegGainMultText, setVelIntegGainMultText] = useState('')
  const [calibPosThresholdText, setCalibPosThresholdText] = useState('')
  const [calibVelThresholdText, setCalibVelThresholdText] = useState('')
  const initialized = useRef(false)

  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [enabledBusy, setEnabledBusy] = useState(false)

  const { isOpen, onOpen, onClose } = useDisclosure()
  const cancelRef = useRef(null)

  useEffect(() => {
    getBoardConstants()
      .then((bc) => {
        const a = bc?.anticogging
        setDefaults(a)
        if (!initialized.current && a) {
          setPosGainMultText(String(a.pos_gain_multiplier_default))
          setVelIntegGainMultText(String(a.vel_integrator_gain_multiplier_default))
          setCalibPosThresholdText(String(a.calib_pos_threshold_default))
          setCalibVelThresholdText(String(a.calib_vel_threshold_default))
          initialized.current = true
        }
      })
      .catch(() => {})
  }, [])

  const state = status?.state ?? 'idle'
  const running = state === 'running'
  const terminal = state === 'done' || state === 'aborted' || state === 'failed'
  const controlSessionRunning = Boolean(status?.control_session_running)

  const posGainMult = Number(posGainMultText)
  const velIntegGainMult = Number(velIntegGainMultText)
  const calibPosThreshold = Number(calibPosThresholdText)
  const calibVelThreshold = Number(calibVelThresholdText)
  const paramsValid =
    Number.isFinite(posGainMult) && posGainMult > 0 &&
    Number.isFinite(velIntegGainMult) && velIntegGainMult > 0 &&
    Number.isFinite(calibPosThreshold) && calibPosThreshold > 0 &&
    Number.isFinite(calibVelThreshold) && calibVelThreshold > 0

  const startDisabledReason = controlSessionRunning
    ? 'A Control/Train/Testing session is running — stop it first.'
    : running
      ? 'Calibration already in progress.'
      : !paramsValid
        ? 'Gain multipliers and thresholds must all be positive numbers.'
        : null

  const confirmStart = async () => {
    onClose()
    setActionError(null)
    setBusy(true)
    try {
      await startAnticoggingCalibration({
        pos_gain_multiplier: posGainMult,
        vel_integrator_gain_multiplier: velIntegGainMult,
        calib_pos_threshold: calibPosThreshold,
        calib_vel_threshold: calibVelThreshold,
      })
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleAbort = async () => {
    setActionError(null)
    setBusy(true)
    try {
      await abortAnticoggingCalibration()
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleToggleEnabled = async () => {
    setEnabledBusy(true)
    setActionError(null)
    try {
      await setAnticoggingEnabled(!status?.anticogging_enabled)
    } catch (e) {
      setActionError(e.message)
    } finally {
      setEnabledBusy(false)
    }
  }

  return (
    <Card bg="paper.bg" variant="outline" borderColor="paper.border">
      <CardHeader>
        <HStack justify="space-between">
          <Heading size="sm" color="accent.600">Anti-cogging Calibration</Heading>
          <HStack>
            <Badge colorScheme={STATE_COLORS[state] ?? 'gray'} variant="solid">{state}</Badge>
            <Badge colorScheme={status?.pre_calibrated ? 'green' : 'gray'} variant="outline">
              {status?.pre_calibrated ? 'map saved' : 'no map saved'}
            </Badge>
            {status?.pre_calibrated && (
              <Badge colorScheme={status?.anticogging_valid ? 'green' : 'red'} variant="outline">
                {status?.anticogging_valid ? 'map valid' : 'map invalid'}
              </Badge>
            )}
          </HStack>
        </HStack>
      </CardHeader>
      <CardBody>
        <VStack align="stretch" spacing={4}>
          <Text fontSize="xs" color="paper.textSecondary">
            Runs ODrive's built-in cogging-torque compensation calibration: the motor spins slowly through
            ~1 turn under temporarily stiffened gains while ODrive builds a correction map, then the map is
            saved and the board reboots to load it. Requires the axis's motor and encoder to already be
            calibrated (config/odrive_config.py, or the Full Calibration button above) — this never re-runs
            that itself.
          </Text>

          {actionError && (
            <Alert status="error" variant="left-accent">
              <AlertIcon /><AlertDescription>{actionError}</AlertDescription>
            </Alert>
          )}
          {status?.error_message && (
            <Alert status="error" variant="left-accent">
              <AlertIcon /><AlertDescription>{status.error_message}</AlertDescription>
            </Alert>
          )}
          {controlSessionRunning && !running && (
            <Alert status="warning" variant="left-accent">
              <AlertIcon />
              <AlertDescription>A Control/Train/Testing session is running — stop it before calibrating.</AlertDescription>
            </Alert>
          )}

          <HStack spacing={3} wrap="wrap" align="flex-end">
            <Box>
              <Text fontSize="xs" color="paper.textSecondary" mb={1}>pos_gain multiplier</Text>
              <InputGroup size="sm" w="110px">
                <Input
                  type="text" inputMode="decimal" fontFamily="mono"
                  value={posGainMultText} onChange={(e) => setPosGainMultText(e.target.value)}
                  isDisabled={running}
                />
                <InputRightAddon px={2} fontSize="xs">x</InputRightAddon>
              </InputGroup>
            </Box>
            <Box>
              <Text fontSize="xs" color="paper.textSecondary" mb={1}>vel_integrator_gain multiplier</Text>
              <InputGroup size="sm" w="110px">
                <Input
                  type="text" inputMode="decimal" fontFamily="mono"
                  value={velIntegGainMultText} onChange={(e) => setVelIntegGainMultText(e.target.value)}
                  isDisabled={running}
                />
                <InputRightAddon px={2} fontSize="xs">x</InputRightAddon>
              </InputGroup>
            </Box>
            <Box>
              <Text fontSize="xs" color="paper.textSecondary" mb={1}>calib_pos_threshold</Text>
              <InputGroup size="sm" w="110px">
                <Input
                  type="text" inputMode="decimal" fontFamily="mono"
                  value={calibPosThresholdText} onChange={(e) => setCalibPosThresholdText(e.target.value)}
                  isDisabled={running}
                />
              </InputGroup>
            </Box>
            <Box>
              <Text fontSize="xs" color="paper.textSecondary" mb={1}>calib_vel_threshold</Text>
              <InputGroup size="sm" w="110px">
                <Input
                  type="text" inputMode="decimal" fontFamily="mono"
                  value={calibVelThresholdText} onChange={(e) => setCalibVelThresholdText(e.target.value)}
                  isDisabled={running}
                />
              </InputGroup>
            </Box>
          </HStack>
          {defaults && (
            <Text fontSize="xs" color="paper.textSecondary">
              Defaults: {defaults.pos_gain_multiplier_default}x / {defaults.vel_integrator_gain_multiplier_default}x
              gain multipliers, calib_pos_threshold={defaults.calib_pos_threshold_default}, calib_vel_threshold=
              {defaults.calib_vel_threshold_default} (config/board_constants.py — unmeasured placeholders, verify
              at the bench). Larger thresholds calibrate faster but produce a less accurate map.
            </Text>
          )}

          <HStack spacing={3}>
            {!running ? (
              <Button
                size="sm" colorScheme="orange" fontWeight="bold"
                onClick={onOpen}
                isDisabled={busy || Boolean(startDisabledReason)}
                title={startDisabledReason ?? undefined}
              >
                Calibrate anti-cogging
              </Button>
            ) : (
              <Button size="sm" colorScheme="red" variant="solid" fontWeight="bold" onClick={handleAbort} isLoading={busy}>
                Abort
              </Button>
            )}
          </HStack>

          {running && (
            <Text fontSize="xs" color="yellow.300">
              Calibrating — motor is energized and moving. Watch the axis; use Abort or the sidebar's
              EMERGENCY STOP (or press Space) if anything looks wrong.
            </Text>
          )}
          {terminal && state === 'done' && (
            <Text fontSize="xs" color="green.300">
              Map saved — the board rebooted to load it. The device connection will reconnect automatically
              within a few seconds.
            </Text>
          )}
          {terminal && state === 'aborted' && (
            <Text fontSize="xs" color="orange.300">Aborted — gains restored, nothing was saved.</Text>
          )}

          <FormControl display="flex" alignItems="center" pt={2} borderTop="1px solid" borderColor="paper.border">
            <FormLabel htmlFor="anticogging-enabled" mb="0" fontSize="sm" color="paper.textPrimary">
              Apply saved anti-cogging map (anticogging_enabled)
            </FormLabel>
            <Switch
              id="anticogging-enabled"
              colorScheme="accent"
              isChecked={Boolean(status?.anticogging_enabled)}
              onChange={handleToggleEnabled}
              isDisabled={enabledBusy || status?.anticogging_enabled == null}
            />
          </FormControl>
          <Text fontSize="xs" color="paper.textSecondary">
            Turning this off does not erase the saved map — useful for isolating whether the map itself is
            causing bad behavior, independent of everything else.
          </Text>
        </VStack>
      </CardBody>

      <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose} isCentered>
        <AlertDialogOverlay>
          <AlertDialogContent bg="paper.bg">
            <AlertDialogHeader color="orange.300">Run anti-cogging calibration?</AlertDialogHeader>
            <AlertDialogBody>
              The motor will energize, gains will be temporarily raised well above their normal tuned values, and
              the axis will spin slowly through about one full turn. Confirm the area is clear before continuing.
              On success the board will reboot to save the calibration map.
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} variant="ghost" onClick={onClose}>Cancel</Button>
              <Button colorScheme="orange" onClick={confirmStart} ml={3}>Confirm &amp; Energize Motor</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Card>
  )
}

export default AnticoggingCalibrationCard
