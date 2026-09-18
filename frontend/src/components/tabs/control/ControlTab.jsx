import { useEffect, useMemo, useState } from 'react'
import { useSelector } from 'react-redux'
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
  Slider,
  SliderTrack,
  SliderFilledTrack,
  SliderThumb,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  List,
  ListItem,
} from '@chakra-ui/react'

import { useControlTelemetry, CONTROL_TELEMETRY_BUFFER_S } from '../../../hooks/useControlTelemetry'
import { startControlSession, stopControlSession, setControlTarget } from '../../../api/control'
import { readProperties, writeProperties, invokeCommand } from '../../../api/backend'
import { turnsDeltaFromLength, rawTorqueNmForCorrected } from '../../../utils/cableGeometry'
import TelemetryTimeSeriesChart from '../../shared/TelemetryTimeSeriesChart'

const UNIT_BY_MODE = { velocity: 'turns/s', torque: 'Nm' }

// Line config for the shared TelemetryTimeSeriesChart (components/shared/,
// same component/style Train's tab uses -- "same graphs everywhere" pass,
// 29 July 2026) -- keys match useControlTelemetry.js's raw ring-buffer
// sample shape directly (position/velocity/torque_est, turns/turns-per-s/
// Nm; no client-side unit conversion the way Train's cable-length keys
// need, since Control operates directly in encoder/motor units). Target
// position shares Position's own Y axis (axisKey) rather than getting its
// own -- it's the same quantity, just a second series -- and is dashed to
// stay visually distinct; only present (non-null) while Position mode is
// running, same as it was via MiniChart's old secondaryKey mechanism.
const CONTROL_CHART_LINES = [
  { key: 'position', label: 'Position (actual)', color: '#2563eb', unit: 'turns', defaultOn: true, side: 'left' },
  { key: 'target_position', label: 'Target position', color: '#2563eb', unit: 'turns', defaultOn: true, side: 'left', axisKey: 'position', dashed: true, lineType: 'stepAfter' },
  { key: 'velocity', label: 'Velocity (actual)', color: '#1baf7a', unit: 'turns/s', defaultOn: false, side: 'right' },
  // Calibrated by default (item 1: "calibration becomes the single source
  // of truth") -- raw torque_est (motor-constant-only estimate) kept
  // available as an off-by-default secondary line, same precedent as
  // TestingTab.jsx's CHART_LINES. Each gets its own axis (no axisKey
  // pairing, unlike target_position above), so they need genuinely
  // distinct hues rather than a shared-hue-plus-dash pair.
  { key: 'torque_est_corrected', label: 'Torque (calibrated)', color: '#eb6834', unit: 'Nm', defaultOn: false, side: 'right' },
  { key: 'torque_est', label: 'Torque (raw estimate)', color: '#eda100', unit: 'Nm', defaultOn: false, side: 'right' },
]

// Modes this tab's own UI understands (its Select only ever offers these
// three). The backend's ControlSession is shared with Profiles/Exercise/
// Force, whose modes ("profile"/"exercise"/"force") this tab has no target
// shape for -- syncing `mode` to one of those and then submitting whatever
// this tab's own fields currently hold produced "Exercise target must be a
// dict, got 0.5"-style errors. Bug found live, 23 July 2026.
const KNOWN_MODES = ['velocity', 'torque', 'position']

// This board is axis0-only (see config/board_constants.py). Ranges are centered
// around the live-tuned values there (pos_gain 6.0, vel_gain 0.05,
// vel_integrator_gain 0.1) with headroom either side for further tuning.
const GAIN_FIELDS = [
  { key: 'pos_gain', label: 'Position Gain', unit: '(turns/s)/turn', min: 0, max: 20, step: 0.1, decimals: 2 },
  { key: 'vel_gain', label: 'Velocity Gain', unit: 'Nm/(turns/s)', min: 0, max: 0.3, step: 0.001, decimals: 4 },
  { key: 'vel_integrator_gain', label: 'Velocity Integrator Gain', unit: 'Nm·s/(turns/s)', min: 0, max: 0.5, step: 0.005, decimals: 3 },
]
const gainPath = (key) => `axis0.controller.config.${key}`

const ControlTab = ({ isActive = true }) => {
  const { status, series, connected, cable } = useControlTelemetry(isActive)
  const { connectedDevice, isConnected } = useSelector((s) => s.device)
  const serial = connectedDevice?.serial_number

  const [mode, setMode] = useState('velocity')
  const [targetText, setTargetText] = useState('0.5')
  // Position mode's target is a small move spec, not a single number — kept
  // as separate fields rather than overloading targetText.
  const [posPositionText, setPosPositionText] = useState('1.0') // relative: turns (or metres, see posUnit) to move from wherever it is now
  const [posUnit, setPosUnit] = useState('turns') // 'turns' | 'm' -- metres converts via the live cable r0/k, same geometry Exercise/Train use
  const [posVelocityText, setPosVelocityText] = useState('1.0')
  const [posAccelText, setPosAccelText] = useState('1.0')
  const [posTorqueLimitText, setPosTorqueLimitText] = useState('') // blank = leave configured torque_lim untouched
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)

  // Cable geometry (r0/k) for the metres unit option (25 July 2026, requested
  // so Position mode isn't turns-only) -- read-only, from the same shared
  // CableState Exercise/Train already expose. Sourced from useControlTelemetry's
  // own `cable` poll (added for item 1's torque calibration) rather than a
  // second independent fetch of the same status -- one poll, two uses.
  // PositionMode itself stays hardware-turns-only; the conversion happens
  // here, client-side, before the target is ever sent.
  const cableGeometry = useMemo(
    () => (cable?.r0 != null ? { r0: cable.r0, k: cable.k ?? 0 } : null),
    [cable?.r0, cable?.k]
  )
  const torqueScale = cable?.torque_model?.scale ?? 1.0
  const torqueOffset = cable?.torque_model?.offset ?? 0.0

  const running = Boolean(status?.running && KNOWN_MODES.includes(status?.mode))
  // A Profiles/Exercise/Force session running on the shared backend session
  // looks identical to `status.running` -- distinguish it so this tab
  // doesn't think a mode it can't represent is "its own" run.
  const anotherModeRunning = Boolean(status?.running && !KNOWN_MODES.includes(status?.mode))

  // Sync local UI state (mode select) from the backend's authoritative status
  // once it starts arriving over the websocket -- only for a mode this tab's
  // own Select actually offers (see KNOWN_MODES above).
  useEffect(() => {
    if (!status) return
    if (status.running && KNOWN_MODES.includes(status.mode)) setMode(status.mode)
    // Deliberately narrow deps: `status` also carries latest_sample, which
    // changes every tick — depending on the whole object would re-run this
    // sync loop at telemetry rate for no reason.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.running, status?.mode])

  const targetNumber = Number(targetText)

  const posPositionNumber = Number(posPositionText)
  const posVelocityNumber = Number(posVelocityText)
  const posAccelNumber = Number(posAccelText)
  const posTorqueLimitNumber = posTorqueLimitText === '' ? null : Number(posTorqueLimitText)

  // Converts a signed cable-length input to signed turns -- turnsDeltaFromLength
  // (like its Python original, core/cable/geometry.py's turns_delta_from_length)
  // only ever returns a magnitude, so the sign is reapplied here, same
  // convention CABLE_SIGN-aware backend callers already follow.
  const posPositionTurnsEstimate = useMemo(() => {
    if (posUnit !== 'm' || !cableGeometry || !Number.isFinite(posPositionNumber)) return null
    try {
      const magnitude = turnsDeltaFromLength(Math.abs(posPositionNumber), cableGeometry.r0, cableGeometry.k)
      return Math.sign(posPositionNumber) * magnitude
    } catch {
      return null
    }
  }, [posUnit, cableGeometry, posPositionNumber])

  const posValid =
    posPositionText !== '' && Number.isFinite(posPositionNumber) &&
    (posUnit === 'turns' || posPositionTurnsEstimate != null) &&
    posVelocityText !== '' && Number.isFinite(posVelocityNumber) && posVelocityNumber > 0 &&
    posAccelText !== '' && Number.isFinite(posAccelNumber) && posAccelNumber > 0 &&
    (posTorqueLimitText === '' || (Number.isFinite(posTorqueLimitNumber) && posTorqueLimitNumber >= 0))

  const targetValid = mode === 'position' ? posValid : (targetText !== '' && Number.isFinite(targetNumber))

  // Item 1: every user-facing Nm value in this tab is meant to represent the
  // CALIBRATED, real physical torque (consistent with Train/Testing) -- the
  // raw value actually sent to hardware.set_torque_target()/torque_limit is
  // converted through the calibration's inverse correction right before
  // send, same as Train/Exercise/Testing already do server-side (there's no
  // CableState-aware mode backing plain Velocity/Torque/Position here, so
  // the conversion happens client-side instead, same precedent as the
  // posPositionTurnsEstimate m/turns conversion just above).
  const buildTarget = () => {
    if (mode === 'position') {
      const positionTurns = posUnit === 'm' ? posPositionTurnsEstimate : posPositionNumber
      return {
        position: positionTurns,
        move_velocity: posVelocityNumber,
        accel_decel: posAccelNumber,
        torque_limit: posTorqueLimitText === '' ? null : rawTorqueNmForCorrected(posTorqueLimitNumber, torqueScale, torqueOffset),
      }
    }
    if (mode === 'torque') {
      return rawTorqueNmForCorrected(targetNumber, torqueScale, torqueOffset)
    }
    return targetNumber
  }

  const handleStart = async () => {
    if (!targetValid) {
      setActionError(mode === 'position' ? 'Fill in Move Distance, Velocity and Accel/Decel' : 'Target must be a number')
      return
    }
    setActionError(null)
    setBusy(true)
    try {
      await startControlSession(mode, buildTarget())
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleStop = async () => {
    setBusy(true)
    try {
      await stopControlSession()
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleRetarget = async () => {
    if (!targetValid) {
      setActionError(mode === 'position' ? 'Fill in Move Distance, Velocity and Accel/Decel' : 'Target must be a number')
      return
    }
    setActionError(null)
    try {
      await setControlTarget(buildTarget())
    } catch (e) {
      setActionError(e.message)
    }
  }

  // Controller gains — read the live values once a device connects, then
  // write on every slider release (onChangeEnd), never on every drag tick.
  const [gains, setGains] = useState({})
  const [gainsLoaded, setGainsLoaded] = useState(false)
  const [gainsError, setGainsError] = useState(null)
  const [gainsSaving, setGainsSaving] = useState(false)
  const [gainsSaved, setGainsSaved] = useState(false)

  useEffect(() => {
    setGainsLoaded(false)
    setGainsSaved(false)
    if (!serial) return undefined
    let cancelled = false
    readProperties(serial, GAIN_FIELDS.map((f) => gainPath(f.key)))
      .then((res) => {
        if (cancelled) return
        const next = {}
        for (const f of GAIN_FIELDS) {
          const v = res[gainPath(f.key)]
          if (typeof v === 'number') next[f.key] = v
        }
        setGains(next)
        setGainsLoaded(true)
      })
      .catch((e) => setGainsError(e.message))
    return () => {
      cancelled = true
    }
  }, [serial])

  const handleGainChange = (key, value) => {
    setGains((prev) => ({ ...prev, [key]: value }))
  }

  const handleGainCommit = async (key, value, decimals) => {
    if (!serial) return
    const rounded = parseFloat(value.toFixed(decimals))
    setGainsError(null)
    setGainsSaved(false)
    try {
      await writeProperties(serial, [{ path: gainPath(key), value: rounded }])
    } catch (e) {
      setGainsError(e.message)
    }
  }

  const handleSaveGains = async () => {
    if (!serial) return
    setGainsSaving(true)
    setGainsError(null)
    try {
      await invokeCommand(serial, 'save_configuration', [])
      setGainsSaved(true)
    } catch (e) {
      setGainsError(e.message)
    } finally {
      setGainsSaving(false)
    }
  }

  const latest = status?.latest_sample
  const logFilename = status?.log_path ? status.log_path.split('/').pop() : null
  const backendErrors = status?.errors ?? []

  return (
    <Box p={4} h="100%" maxW="1400px" mx="auto" overflow="auto">
      <VStack spacing={4} align="stretch">
        {actionError && (
          <Alert status="error" variant="left-accent">
            <AlertIcon />
            <AlertDescription>{actionError}</AlertDescription>
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
              A {status?.mode} session is running from another tab — stop it before starting Control.
            </AlertDescription>
          </Alert>
        )}

        {/* Mode / target / run controls */}
        <Card bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="paper.textPrimary">Control</Heading>
              <Badge colorScheme={connected ? 'green' : 'gray'} variant="outline">
                {connected ? 'connected' : 'disconnected'}
              </Badge>
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={4}>
              <HStack spacing={4} wrap="wrap">
                <Box>
                  <Text fontSize="xs" color="paper.textSecondary" mb={1}>Mode</Text>
                  <Select
                    size="sm"
                    w="140px"
                    value={mode}
                    isDisabled={running}
                    onChange={(e) => setMode(e.target.value)}
                  >
                    <option value="velocity">Velocity</option>
                    <option value="torque">Torque</option>
                    <option value="position">Position</option>
                  </Select>
                </Box>

                {mode === 'position' ? (
                  <>
                    <Box>
                      <Text fontSize="xs" color="paper.textSecondary" mb={1}>Move Distance</Text>
                      <HStack spacing={1}>
                        <InputGroup size="sm" w="110px">
                          <Input
                            type="text"
                            inputMode="decimal"
                            fontFamily="mono"
                            value={posPositionText}
                            onChange={(e) => setPosPositionText(e.target.value)}
                          />
                        </InputGroup>
                        <Select size="sm" w="80px" value={posUnit} onChange={(e) => setPosUnit(e.target.value)}>
                          <option value="turns">turns</option>
                          <option value="m">m (cable)</option>
                        </Select>
                      </HStack>
                      <Text fontSize="0.65rem" color="paper.textSecondary" mt={0.5}>
                        relative to current position
                        {posUnit === 'm' && (
                          posPositionTurnsEstimate != null
                            ? ` (≈ ${posPositionTurnsEstimate.toFixed(3)} turns)`
                            : cableGeometry == null ? ' (loading cable calibration…)' : ' (out of range for current calibration)'
                        )}
                      </Text>
                    </Box>
                    <Box>
                      <Text fontSize="xs" color="paper.textSecondary" mb={1}>Move Velocity</Text>
                      <InputGroup size="sm" w="150px">
                        <Input
                          type="text"
                          inputMode="decimal"
                          fontFamily="mono"
                          value={posVelocityText}
                          onChange={(e) => setPosVelocityText(e.target.value)}
                        />
                        <InputRightAddon px={2} fontSize="xs">turns/s</InputRightAddon>
                      </InputGroup>
                    </Box>
                    <Box>
                      <Text fontSize="xs" color="paper.textSecondary" mb={1}>Accel / Decel</Text>
                      <InputGroup size="sm" w="150px">
                        <Input
                          type="text"
                          inputMode="decimal"
                          fontFamily="mono"
                          value={posAccelText}
                          onChange={(e) => setPosAccelText(e.target.value)}
                        />
                        <InputRightAddon px={2} fontSize="xs">turns/s²</InputRightAddon>
                      </InputGroup>
                    </Box>
                    <Box>
                      <Text fontSize="xs" color="paper.textSecondary" mb={1}>Torque Limit (optional)</Text>
                      <InputGroup size="sm" w="160px">
                        <Input
                          type="text"
                          inputMode="decimal"
                          fontFamily="mono"
                          placeholder="unchanged"
                          value={posTorqueLimitText}
                          onChange={(e) => setPosTorqueLimitText(e.target.value)}
                        />
                        <InputRightAddon px={2} fontSize="xs">Nm</InputRightAddon>
                      </InputGroup>
                      <Text fontSize="0.65rem" color="paper.textSecondary" mt={0.5}>calibrated (real) Nm</Text>
                    </Box>
                  </>
                ) : (
                  <Box>
                    <Text fontSize="xs" color="paper.textSecondary" mb={1}>Target{mode === 'torque' ? ' (calibrated Nm)' : ''}</Text>
                    <InputGroup size="sm" w="180px">
                      <Input
                        type="text"
                        inputMode="decimal"
                        fontFamily="mono"
                        value={targetText}
                        onChange={(e) => setTargetText(e.target.value)}
                      />
                      <InputRightAddon px={2} fontSize="xs">{UNIT_BY_MODE[mode]}</InputRightAddon>
                    </InputGroup>
                  </Box>
                )}

                <VStack align="stretch" spacing={1} justify="flex-end">
                  <Text fontSize="xs" color="transparent" userSelect="none">.</Text>
                  {running ? (
                    <Button size="sm" colorScheme="accent" onClick={handleRetarget} isDisabled={!targetValid}>
                      {mode === 'position' ? 'Move again' : 'Set target'}
                    </Button>
                  ) : (
                    <Button size="sm" colorScheme="green" onClick={handleStart} isDisabled={!targetValid || busy || anotherModeRunning}>
                      Start
                    </Button>
                  )}
                </VStack>

                <VStack align="stretch" spacing={1} justify="flex-end">
                  <Text fontSize="xs" color="transparent" userSelect="none">.</Text>
                  <Button
                    size="sm"
                    colorScheme="red"
                    variant="solid"
                    fontWeight="bold"
                    isDisabled={!running}
                    onClick={handleStop}
                  >
                    STOP
                  </Button>
                </VStack>
              </HStack>

              <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                <Stat>
                  <StatLabel color="paper.textPrimary">Position</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{(latest?.position ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">turns</Text>
                </Stat>
                <Stat>
                  <StatLabel color="paper.textPrimary">Velocity</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{(latest?.velocity ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">turns/s</Text>
                </Stat>
                <Stat>
                  <StatLabel color="paper.textPrimary">Torque (calibrated est.)</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{(latest?.torque_est_corrected ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">Nm — sign is direction, not resistance magnitude</Text>
                </Stat>
                <Stat>
                  <StatLabel color="paper.textPrimary">Current (Iq)</StatLabel>
                  <StatNumber color="accent.600" fontSize="xl">{(latest?.current_iq ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="paper.textSecondary">A</Text>
                </Stat>
              </SimpleGrid>

              <HStack justify="space-between">
                <Text fontSize="xs" color="paper.textSecondary">
                  CSV log: {logFilename ? <Text as="span" fontFamily="mono" color="paper.textPrimary">{logFilename}</Text> : '—'}
                </Text>
              </HStack>
            </VStack>
          </CardBody>
        </Card>

        {/* Controller gains — live tuning, straight to axis0.controller.config */}
        <Card bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="paper.textPrimary">Controller Gains</Heading>
              {!isConnected && <Badge colorScheme="gray" variant="outline">no device</Badge>}
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={5}>
              {gainsError && (
                <Alert status="error" variant="left-accent">
                  <AlertIcon />
                  <AlertDescription>{gainsError}</AlertDescription>
                </Alert>
              )}

              {!isConnected ? (
                <Text fontSize="sm" color="paper.textSecondary">Connect a device to adjust controller gains.</Text>
              ) : (
                GAIN_FIELDS.map((f) => (
                  <Box key={f.key}>
                    <HStack justify="space-between" mb={1}>
                      <Text fontSize="sm" color="paper.textPrimary">{f.label}</Text>
                      <Text fontSize="sm" fontFamily="mono" color="accent.600">
                        {gains[f.key] !== undefined ? gains[f.key].toFixed(f.decimals) : '—'} {f.unit}
                      </Text>
                    </HStack>
                    <Slider
                      min={f.min}
                      max={f.max}
                      step={f.step}
                      value={gains[f.key] ?? f.min}
                      isDisabled={!gainsLoaded}
                      onChange={(v) => handleGainChange(f.key, v)}
                      onChangeEnd={(v) => handleGainCommit(f.key, v, f.decimals)}
                      colorScheme="accent"
                    >
                      <SliderTrack bg="paper.bg"><SliderFilledTrack /></SliderTrack>
                      <SliderThumb boxSize={4} />
                    </Slider>
                  </Box>
                ))
              )}

              <HStack justify="flex-end" spacing={3}>
                {gainsSaved && <Text fontSize="xs" color="green.300">Saved to NVM</Text>}
                <Button
                  size="sm"
                  colorScheme="accent"
                  variant="outline"
                  isDisabled={!isConnected || !gainsLoaded || running}
                  isLoading={gainsSaving}
                  onClick={handleSaveGains}
                >
                  Save to NVM
                </Button>
              </HStack>
              <Text fontSize="0.65rem" color="paper.textSecondary">
                Slider changes take effect immediately on the live device. "Save to NVM" persists
                them across reboots — it briefly reboots the board, so it's disabled while a
                session is running.
              </Text>
            </VStack>
          </CardBody>
        </Card>

        {/* Live chart -- same shared component/style as the Train tab's
            (components/shared/TelemetryTimeSeriesChart.jsx): per-line
            enable/axis-range/invert/smoothing controls, range-duration
            buttons, and pause/freeze, all built in. */}
        <TelemetryTimeSeriesChart series={series} lines={CONTROL_CHART_LINES} bufferS={CONTROL_TELEMETRY_BUFFER_S} />
      </VStack>
    </Box>
  )
}

export default ControlTab
