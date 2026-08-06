import { useEffect, useMemo, useState } from 'react'
import {
  Box, VStack, HStack, Text, Heading, Badge, Button, Card, CardHeader, CardBody,
  SimpleGrid, Stat, StatLabel, StatNumber, Alert, AlertIcon, AlertTitle, AlertDescription, List, ListItem,
  useDisclosure,
} from '@chakra-ui/react'
import { useTrainTelemetry } from '../../../hooks/useTrainTelemetry'
import { startTrainSession, stopTrainSession, setTrainProfile, previewTrainProfile } from '../../../api/train'
import TrainProfileEditor from './TrainProfileEditor'
import TelemetryTimeSeriesChart from '../../shared/TelemetryTimeSeriesChart'
import TrainPositionChart from './TrainPositionChart'
import TrainResetModal from '../../modals/TrainResetModal'

// Line config for the shared TelemetryTimeSeriesChart (components/shared/) --
// same 3 quantities/keys useTrainTelemetry.js's samples already carry.
const TRAIN_CHART_LINES = [
  { key: 'position_m', label: 'Position (actual)', color: '#63B3ED', unit: 'm', defaultOn: true, side: 'left' },
  { key: 'velocity_m_s', label: 'Velocity (actual)', color: '#68D391', unit: 'm/s', defaultOn: false, side: 'right' },
  { key: 'torque_est_nm', label: 'Torque (actual)', color: '#F6AD55', unit: 'Nm', defaultOn: false, side: 'right' },
]

const TrainTab = ({ isActive = true }) => {
  const { status, series, connected } = useTrainTelemetry(isActive)
  const control = status?.control
  const cable = status?.cable

  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [plannedPoints, setPlannedPoints] = useState([])
  const [profileEditorKey, setProfileEditorKey] = useState(0)
  // Bumped on Reset to remount TelemetryTimeSeriesChart -- the chart owns
  // its own pause/freeze state internally (components/shared/
  // TelemetryTimeSeriesChart.jsx), so a fresh mount is how Reset clears an
  // active freeze from outside without the chart needing to expose an
  // imperative reset method. Both this and profileEditorKey are always
  // bumped together in handleReset (so they're always numerically equal) --
  // the `key` props built from them below are string-prefixed (not the bare
  // number) precisely so the two stay distinguishable as React `key`s:
  // they're direct siblings under the same parent VStack, and two sibling
  // elements sharing one key -- even non-mapped, explicitly-keyed ones --
  // is exactly the "two children with the same key" warning React would
  // otherwise raise (caught via a real-browser smoke check, not by the
  // test suite, which doesn't render this tree).
  const [chartKey, setChartKey] = useState(0)
  const { isOpen: isResetOpen, onOpen: onResetOpen, onClose: onResetClose } = useDisclosure()

  const trainSessionRunning = Boolean(control?.running && control?.mode === 'train')
  const anotherModeRunning = Boolean(control?.running && !trainSessionRunning)
  const isHomed = cable?.is_homed ?? false
  const backendErrors = control?.errors ?? []

  const positionRangeM = useMemo(
    () => [0, cable?.max_extension_length_m ?? 1.0],
    [cable?.max_extension_length_m]
  )

  // Re-derive the "planned" curve (Graph B) from the ACTIVE profile whenever
  // it changes -- same evaluator the profile editor's own draft preview
  // uses (spec §4: one source of truth), just against whatever was actually
  // applied via Start/Apply rather than the unsaved draft.
  const activeProfile = trainSessionRunning && (control?.target?.action === 'run' || control?.target?.action === 'set_profile')
    ? control.target.profile
    : null
  const activeProfileKey = activeProfile ? JSON.stringify(activeProfile) : null

  useEffect(() => {
    if (!activeProfile) {
      setPlannedPoints([])
      return
    }
    let cancelled = false
    previewTrainProfile(activeProfile, positionRangeM, 200)
      .then(({ points }) => { if (!cancelled) setPlannedPoints(points) })
      .catch(() => { if (!cancelled) setPlannedPoints([]) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProfileKey, positionRangeM[0], positionRangeM[1]])

  const actualPoints = useMemo(
    () =>
      series
        .filter((s) => s.position_m != null && s.force_est_n != null)
        .map((s) => ({ position_m: s.position_m, force_n: s.force_est_n })),
    [series]
  )

  const handleStart = async (profile) => {
    setActionError(null)
    setBusy(true)
    try {
      await startTrainSession(profile)
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleApply = async (profile) => {
    setActionError(null)
    setBusy(true)
    try {
      await setTrainProfile(profile)
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
      await stopTrainSession()
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  // Item 1's Reset -- a full state wipe distinct from re-homing (see
  // TrainResetModal's own docstring for exactly what it clears/preserves
  // server-side). The modal makes the actual reset_position call itself;
  // this callback only clears what's local to this tab's React state --
  // the draft profile (remounted via a fresh key, simpler than threading a
  // reset callback down through TrainProfileEditor's own internal state),
  // any error/planned-curve leftovers, and an active telemetry freeze
  // (item 5) so Reset never leaves the chart pinned to stale data.
  const handleReset = () => {
    setActionError(null)
    setPlannedPoints([])
    setProfileEditorKey((k) => k + 1)
    setChartKey((k) => k + 1)
  }

  return (
    <Box p={4} h="100%" maxW="1400px" mx="auto" overflow="auto">
      <VStack spacing={4} align="stretch">
        {actionError && (
          <Alert status="error" variant="left-accent">
            <AlertIcon /><AlertDescription>{actionError}</AlertDescription>
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
              <List fontSize="sm">{backendErrors.map((err) => <ListItem key={err}>{err}</ListItem>)}</List>
            </Box>
          </Alert>
        )}
        {anotherModeRunning && (
          <Alert status="warning" variant="left-accent">
            <AlertIcon />
            <AlertDescription>
              A {control?.mode} session is running from another tab — stop it before starting Train.
            </AlertDescription>
          </Alert>
        )}
        {!isHomed && !anotherModeRunning && (
          <Alert status="info" variant="left-accent">
            <AlertIcon />
            <AlertDescription>Cable is not homed yet — open the Setup tab to home before starting Train.</AlertDescription>
          </Alert>
        )}

        <Card bg="gray.800" variant="elevated">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="white">Train</Heading>
              <HStack>
                {trainSessionRunning && <Badge colorScheme="green" variant="solid">Running</Badge>}
                <Badge colorScheme={isHomed ? 'green' : 'gray'} variant="outline">{isHomed ? 'homed' : 'not homed'}</Badge>
                <Badge colorScheme={connected ? 'green' : 'gray'} variant="outline">{connected ? 'connected' : 'disconnected'}</Badge>
              </HStack>
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={4}>
              <HStack>
                {trainSessionRunning && (
                  <Button size="sm" colorScheme="red" variant="solid" fontWeight="bold" onClick={handleStop} isDisabled={busy}>
                    STOP
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  colorScheme="orange"
                  onClick={onResetOpen}
                  isDisabled={busy || trainSessionRunning || anotherModeRunning}
                >
                  Reset
                </Button>
              </HStack>
              <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                <Stat>
                  <StatLabel color="gray.300">Cable position</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">
                    {control?.extra?.cable_length_m != null ? control.extra.cable_length_m.toFixed(3) : '—'}
                  </StatNumber>
                  <Text fontSize="xs" color="gray.400">m, from home</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Target force</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">
                    {control?.extra?.target_force_n != null ? control.extra.target_force_n.toFixed(1) : '—'}
                  </StatNumber>
                  <Text fontSize="xs" color="gray.400">N</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Commanded torque</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">
                    {control?.extra?.commanded_torque_nm != null ? control.extra.commanded_torque_nm.toFixed(3) : '—'}
                  </StatNumber>
                  <Text fontSize="xs" color="gray.400">Nm</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Max extension</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">
                    {cable?.has_max && cable?.max_extension_length_m != null ? cable.max_extension_length_m.toFixed(3) : '—'}
                  </StatNumber>
                  <Text fontSize="xs" color="gray.400">{cable?.has_max ? 'm, from home' : 'not calibrated'}</Text>
                </Stat>
              </SimpleGrid>
            </VStack>
          </CardBody>
        </Card>

        <TrainProfileEditor
          key={`profile-editor-${profileEditorKey}`}
          onStart={handleStart}
          onApply={handleApply}
          sessionRunning={trainSessionRunning}
          busy={busy || anotherModeRunning || !isHomed}
          positionRangeM={positionRangeM}
          resistanceUnitKg={Boolean(cable?.resistance_display_unit_kg)}
        />

        <TelemetryTimeSeriesChart
          key={`telemetry-chart-${chartKey}`}
          series={series}
          lines={TRAIN_CHART_LINES}
          bufferS={cable?.train_telemetry_buffer_s ?? 90}
        />
        <TrainPositionChart plannedPoints={plannedPoints} actualPoints={actualPoints} positionRangeM={positionRangeM} />
      </VStack>

      <TrainResetModal isOpen={isResetOpen} onClose={onResetClose} onReset={handleReset} />
    </Box>
  )
}

export default TrainTab
