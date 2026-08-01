import { useEffect, useState } from 'react'
import {
  Box, VStack, HStack, Text, Heading, Badge, Button, Card, CardHeader, CardBody,
  SimpleGrid, Stat, StatLabel, StatNumber, Alert, AlertIcon, AlertTitle, AlertDescription,
  Select, List, ListItem,
} from '@chakra-ui/react'
import { useExperimentTelemetry } from '../../../hooks/useExperimentTelemetry'
import {
  listExperiments, configureExperiment, confirmStartExperiment, stopExperiment, getExperimentStatus,
} from '../../../api/experiments'
import ExperimentConfigForm from './ExperimentConfigForm'
import TelemetryTimeSeriesChart from '../../shared/TelemetryTimeSeriesChart'

// Charts torque_est ("measured/estimated"), not the literal commanded value
// -- the ring buffer doesn't historize commanded_torque_nm (see
// useExperimentTelemetry.js's header comment). The live readout panel below
// still shows the current commanded value from control.extra.
const CHART_LINES = [
  { key: 'position_m', label: 'Position (actual)', color: '#63B3ED', unit: 'm', defaultOn: true, side: 'left' },
  { key: 'target_position_m', label: 'Target position', color: '#63B3ED', unit: 'm', defaultOn: true, side: 'left', axisKey: 'position_m', dashed: true },
  { key: 'torque_est_nm', label: 'Torque (estimated)', color: '#F6AD55', unit: 'Nm', defaultOn: true, side: 'right' },
  { key: 'current_iq_a', label: 'Phase current', color: '#68D391', unit: 'A', defaultOn: false, side: 'right' },
  { key: 'bus_voltage_v', label: 'Bus voltage', color: '#B794F4', unit: 'V', defaultOn: false, side: 'right' },
  { key: 'estimated_power_w', label: 'Estimated power', color: '#FC8181', unit: 'W', defaultOn: false, side: 'right' },
]

const STATE_COLORS = {
  idle: 'gray', configured: 'blue', ramping: 'yellow', lifting: 'yellow',
  holding: 'green', complete: 'green', aborted: 'red',
}

const TestingTab = ({ isActive = true }) => {
  const { status, series, connected } = useExperimentTelemetry(isActive)
  const control = status?.control
  const cable = status?.cable

  const [experiments, setExperiments] = useState([])
  const [selectedName, setSelectedName] = useState(null)
  const [currentPositionM, setCurrentPositionM] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listExperiments()
      .then((list) => {
        setExperiments(list)
        if (list.length && !selectedName) setSelectedName(list[0].name)
      })
      .catch((e) => setActionError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshPosition = () => {
    getExperimentStatus()
      .then((s) => setCurrentPositionM(s.current_position_m))
      .catch(() => {})
  }
  useEffect(refreshPosition, [])

  const isHomed = cable?.is_homed ?? false
  const hasMax = cable?.has_max ?? false
  const prerequisitesReady = isHomed && hasMax
  const backendErrors = control?.errors ?? []

  const experimentRunning = Boolean(control?.running && control?.mode === 'experiment')
  const anotherModeRunning = Boolean(control?.running && !experimentRunning)
  const experimentState = control?.extra?.experiment_state ?? null
  const isConfigured = experimentRunning && experimentState === 'configured'
  const isTerminal = experimentState === 'complete' || experimentState === 'aborted'

  const selectedSchema = experiments.find((e) => e.name === selectedName)

  const handleConfigure = async (config) => {
    setActionError(null)
    setBusy(true)
    try {
      await configureExperiment(selectedName, config)
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleConfirmStart = async () => {
    setActionError(null)
    setBusy(true)
    try {
      await confirmStartExperiment()
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
      await stopExperiment()
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
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
              A {control?.mode} session is running from another tab — stop it before starting a Testing-tab experiment.
            </AlertDescription>
          </Alert>
        )}
        {!prerequisitesReady && (
          <Alert status="info" variant="left-accent">
            <AlertIcon />
            <AlertDescription>
              Complete calibration in the Train tab first — {!isHomed ? 'cable is not homed' : 'no max-extension calibration saved'}.
            </AlertDescription>
          </Alert>
        )}

        <Card bg="gray.800" variant="elevated">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="white">Testing</Heading>
              <HStack>
                {experimentState && (
                  <Badge colorScheme={STATE_COLORS[experimentState] ?? 'gray'} variant="solid">{experimentState}</Badge>
                )}
                <Badge colorScheme={prerequisitesReady ? 'green' : 'gray'} variant="outline">
                  {prerequisitesReady ? 'calibration ready' : 'calibration incomplete'}
                </Badge>
                <Badge colorScheme={connected ? 'green' : 'gray'} variant="outline">{connected ? 'connected' : 'disconnected'}</Badge>
              </HStack>
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={4}>
              <HStack>
                <Button size="sm" colorScheme="red" variant="solid" fontWeight="bold" onClick={handleStop} isDisabled={busy || !experimentRunning}>
                  STOP
                </Button>
              </HStack>

              {prerequisitesReady && (
                <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
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
                    <StatNumber color="odrive.300" fontSize="xl">{cable?.r0 != null ? cable.r0.toFixed(4) : '—'}</StatNumber>
                    <Text fontSize="xs" color="gray.400">m</Text>
                  </Stat>
                  <Stat>
                    <StatLabel color="gray.300">Correction (k)</StatLabel>
                    <StatNumber color="odrive.300" fontSize="xl">{cable?.k != null ? cable.k.toExponential(2) : '—'}</StatNumber>
                    <Text fontSize="xs" color="gray.400">m/rad</Text>
                  </Stat>
                </SimpleGrid>
              )}
            </VStack>
          </CardBody>
        </Card>

        {prerequisitesReady && !experimentRunning && (
          <Card bg="gray.800" variant="elevated">
            <CardHeader><Heading size="sm" color="white">Configure experiment</Heading></CardHeader>
            <CardBody>
              <VStack align="stretch" spacing={4}>
                <Select size="sm" value={selectedName ?? ''} onChange={(e) => setSelectedName(e.target.value)} bg="gray.900" color="white">
                  {experiments.map((e) => <option key={e.name} value={e.name}>{e.label}</option>)}
                </Select>
                <ExperimentConfigForm
                  experimentSchema={selectedSchema}
                  currentPositionM={currentPositionM}
                  onRefreshPosition={refreshPosition}
                  onConfigure={handleConfigure}
                  disabled={busy || anotherModeRunning}
                  busy={busy}
                />
              </VStack>
            </CardBody>
          </Card>
        )}

        {isConfigured && (
          <Alert status="warning" variant="solid">
            <AlertIcon />
            <Box flex="1">
              <AlertTitle>Motor not yet energized</AlertTitle>
              <AlertDescription>
                Experiment configured. Confirm to begin the torque ramp — make sure the area is clear.
              </AlertDescription>
            </Box>
            <Button colorScheme="orange" fontWeight="bold" onClick={handleConfirmStart} isDisabled={busy}>
              Confirm &amp; Energize Motor
            </Button>
          </Alert>
        )}

        {experimentRunning && !isConfigured && (
          <Card bg="gray.800" variant="elevated">
            <CardHeader><Heading size="sm" color="white">Live telemetry</Heading></CardHeader>
            <CardBody>
              <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                <Stat>
                  <StatLabel color="gray.300">Position</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{control?.extra?.position_m != null ? control.extra.position_m.toFixed(4) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">m, target {control?.extra?.target_position_m?.toFixed(4) ?? '—'}</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Commanded torque</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{control?.extra?.commanded_torque_nm != null ? control.extra.commanded_torque_nm.toFixed(3) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">Nm</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Phase current</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{control?.latest_sample?.current_iq != null ? control.latest_sample.current_iq.toFixed(3) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">A (Iq_measured)</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Bus voltage / power</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{control?.extra?.bus_voltage_v != null ? control.extra.bus_voltage_v.toFixed(1) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">V, ~{control?.extra?.estimated_power_w != null ? control.extra.estimated_power_w.toFixed(2) : '—'} W</Text>
                </Stat>
              </SimpleGrid>
            </CardBody>
          </Card>
        )}

        {isTerminal && (
          <Card bg="gray.800" variant="elevated">
            <CardHeader><Heading size="sm" color="white">Run summary</Heading></CardHeader>
            <CardBody>
              <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                <Stat>
                  <StatLabel color="gray.300">Peak torque</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{control?.extra?.peak_torque_nm != null ? control.extra.peak_torque_nm.toFixed(3) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">Nm</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Time to first movement</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{control?.extra?.time_to_first_movement_s != null ? control.extra.time_to_first_movement_s.toFixed(2) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">s</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Time to target</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{control?.extra?.time_to_target_s != null ? control.extra.time_to_target_s.toFixed(2) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">s</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Final position error</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{control?.extra?.final_position_error_m != null ? control.extra.final_position_error_m.toFixed(4) : '—'}</StatNumber>
                  <Text fontSize="xs" color="gray.400">m</Text>
                </Stat>
              </SimpleGrid>
              {(control?.extra?.abort_reason || control?.extra?.complete_reason) && (
                <Text mt={3} fontSize="sm" color="gray.400">
                  {experimentState === 'aborted' ? `Aborted: ${control.extra.abort_reason}` : `Completed: ${control.extra.complete_reason}`}
                </Text>
              )}
              {control?.log_path && <Text mt={2} fontSize="xs" color="gray.500">Log: {control.log_path}</Text>}
            </CardBody>
          </Card>
        )}

        <TelemetryTimeSeriesChart series={series} lines={CHART_LINES} bufferS={90} title="Testing telemetry" />
      </VStack>
    </Box>
  )
}

export default TestingTab
