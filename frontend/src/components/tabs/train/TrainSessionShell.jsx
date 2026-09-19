import { useEffect, useMemo, useState } from 'react'
import {
  Box, VStack, HStack, Text, Heading, Badge, Button, Card, CardHeader, CardBody,
  SimpleGrid, Stat, StatLabel, StatNumber, Alert, AlertIcon, AlertTitle, AlertDescription, List, ListItem,
  useDisclosure,
} from '@chakra-ui/react'
import { useTrainTelemetry } from '../../../hooks/useTrainTelemetry'
import { startTrainSession, stopTrainSession, setTrainProfile, previewTrainProfile } from '../../../api/train'
import TelemetryTimeSeriesChart from '../../shared/TelemetryTimeSeriesChart'
import TrainPositionChart from './TrainPositionChart'
import TrainResetModal from '../../modals/TrainResetModal'

// Everything session/hardware-side (status card, Start/Stop/Reset, live
// telemetry + position charts) that Train and GYM both need identically --
// they're two UIs onto the literal same "train" control-session/hardware
// underneath (no new backend mode/routes for GYM). `title` only relabels the
// on-screen text; `EditorComponent` is the one genuinely different piece --
// TrainTab passes TrainProfileEditor (the general multi-segment/multi-shape
// builder), GymTab passes GymProfileEditor (its own bespoke, single-
// resistance-type builder) -- both receive the identical prop contract
// (onStart/onApply/sessionRunning/busy/positionRangeM/resistanceUnitKg) so
// they're interchangeable here.
const TRAIN_CHART_LINES = [
  { key: 'position_m', label: 'Position (actual)', color: '#2563eb', unit: 'm', defaultOn: true, side: 'left' },
  { key: 'velocity_m_s', label: 'Velocity (actual)', color: '#1baf7a', unit: 'm/s', defaultOn: false, side: 'right' },
  { key: 'torque_est_nm', label: 'Torque (actual)', color: '#eb6834', unit: 'Nm', defaultOn: false, side: 'right' },
]

const TrainSessionShell = (props) => {
  // Destructured here (not in the parameter list) so `EditorComponent` --
  // referenced only as a JSX tag name below, never inside a `{}` expression
  // -- picks up the same `no-unused-vars` `varsIgnorePattern: '^[A-Z_]'`
  // exemption every other component-as-variable in this codebase relies on
  // (e.g. MainTabs.jsx's `const Component = tabConfig.component`) -- this
  // project has no eslint-plugin-react `jsx-uses-vars`, so plain JS scope
  // analysis doesn't see a JSXIdentifier tag name as a "use" on its own;
  // destructured *parameters* aren't covered by that pattern (only `argsIgnorePattern`
  // governs those, and it isn't set), which is what flagged this when
  // `EditorComponent` was destructured directly in the signature instead.
  // showStats: the Cable position/Target force/Commanded torque/Max extension
  // stat grid -- raw engineering numbers Train's own users want but GYM's
  // "minimalistic" brief (see GymProfileEditor's own doc comment) explicitly
  // doesn't. showReset: the Reset button (full state wipe, see
  // TrainResetModal) -- GYM users use Train's own Reset if they ever need
  // one, no reason to duplicate it here. Both default on so Train itself is
  // unaffected; GymTab passes both false.
  const { isActive = true, title, EditorComponent, showStats = true, showReset = true } = props
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

  // Editors call these with { profile } (TrainProfileEditor) or
  // { phaseForces } (GymProfileEditor's Concentric/Eccentric mode) -- the two
  // alternative shapes TrainMode.validate_target() itself accepts (sub-phase
  // 4); forwarded straight through to the API client.
  const handleStart = async (payload) => {
    setActionError(null)
    setBusy(true)
    try {
      await startTrainSession(payload)
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleApply = async (payload) => {
    setActionError(null)
    setBusy(true)
    try {
      await setTrainProfile(payload)
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
  // reset callback down through the editor's own internal state), any
  // error/planned-curve leftovers, and an active telemetry freeze (item 5)
  // so Reset never leaves the chart pinned to stale data.
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
              A {control?.mode} session is running from another tab — stop it before starting {title}.
            </AlertDescription>
          </Alert>
        )}
        {!isHomed && !anotherModeRunning && (
          <Alert status="info" variant="left-accent">
            <AlertIcon />
            <AlertDescription>Cable is not homed yet — open the Setup tab to home before starting {title}.</AlertDescription>
          </Alert>
        )}

        <Card bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="paper.textPrimary">{title}</Heading>
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
                {showReset && (
                  <Button
                    size="sm"
                    variant="outline"
                    colorScheme="orange"
                    onClick={onResetOpen}
                    isDisabled={busy || trainSessionRunning || anotherModeRunning}
                  >
                    Reset
                  </Button>
                )}
              </HStack>
              {showStats && (
                <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                  <Stat>
                    <StatLabel color="paper.textPrimary">Cable position</StatLabel>
                    <StatNumber color="accent.600" fontSize="xl">
                      {control?.extra?.cable_length_m != null ? control.extra.cable_length_m.toFixed(3) : '—'}
                    </StatNumber>
                    <Text fontSize="xs" color="paper.textSecondary">m, from home</Text>
                  </Stat>
                  <Stat>
                    <StatLabel color="paper.textPrimary">Target force</StatLabel>
                    <StatNumber color="accent.600" fontSize="xl">
                      {control?.extra?.target_force_n != null ? control.extra.target_force_n.toFixed(1) : '—'}
                    </StatNumber>
                    <Text fontSize="xs" color="paper.textSecondary">N</Text>
                  </Stat>
                  <Stat>
                    <StatLabel color="paper.textPrimary">Commanded torque</StatLabel>
                    <StatNumber color="accent.600" fontSize="xl">
                      {control?.extra?.commanded_torque_nm != null ? control.extra.commanded_torque_nm.toFixed(3) : '—'}
                    </StatNumber>
                    <Text fontSize="xs" color="paper.textSecondary">Nm</Text>
                  </Stat>
                  <Stat>
                    <StatLabel color="paper.textPrimary">Max extension</StatLabel>
                    <StatNumber color="accent.600" fontSize="xl">
                      {cable?.has_max && cable?.max_extension_length_m != null ? cable.max_extension_length_m.toFixed(3) : '—'}
                    </StatNumber>
                    <Text fontSize="xs" color="paper.textSecondary">{cable?.has_max ? 'm, from home' : 'not calibrated'}</Text>
                  </Stat>
                </SimpleGrid>
              )}
            </VStack>
          </CardBody>
        </Card>

        {/* liveExtra: the raw tick() extra dict (target_force_n, phase, ...).
            cable: the raw status.cable object (inertia_kg_max,
            phase_velocity_deadband_m_s, ...). Both passed straight through so
            an editor CAN read live feedback/settings it cares about (GYM's
            Concentric/Eccentric mode reads liveExtra.phase for its live
            badge, and cable.inertia_kg_max for its Inertia slider's real
            configured range) without this shell needing to know about every
            field any given editor might care about. */}
        <EditorComponent
          key={`profile-editor-${profileEditorKey}`}
          onStart={handleStart}
          onApply={handleApply}
          sessionRunning={trainSessionRunning}
          busy={busy || anotherModeRunning || !isHomed}
          positionRangeM={positionRangeM}
          resistanceUnitKg={Boolean(cable?.resistance_display_unit_kg)}
          liveExtra={control?.extra}
          cable={cable}
        />

        <TelemetryTimeSeriesChart
          key={`telemetry-chart-${chartKey}`}
          series={series}
          lines={TRAIN_CHART_LINES}
          bufferS={cable?.train_telemetry_buffer_s ?? 90}
        />
        <TrainPositionChart plannedPoints={plannedPoints} actualPoints={actualPoints} positionRangeM={positionRangeM} />
      </VStack>

      {showReset && <TrainResetModal isOpen={isResetOpen} onClose={onResetClose} onReset={handleReset} />}
    </Box>
  )
}

export default TrainSessionShell
