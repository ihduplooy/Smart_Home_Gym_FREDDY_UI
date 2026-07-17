import { memo, useEffect, useMemo, useState } from 'react'
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
} from '@chakra-ui/react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts'

import { useControlTelemetry } from '../../../hooks/useControlTelemetry'
import {
  startControlSession,
  stopControlSession,
  setControlTarget,
  setHardwareSource as apiSetHardwareSource,
} from '../../../api/control'

const UNIT_BY_MODE = { velocity: 'turns/s', torque: 'Nm' }

// Same visual language as the Inspector's LiveCharts (dark card, colored
// line, seconds on X) — the declared Session 1 -> 2 chart-reuse touchpoint.
const MiniChart = memo(({ label, unit, color, data }) => (
  <Box bg="gray.800" border="1px solid" borderColor="gray.700" borderRadius="md" p={2} h="200px" display="flex" flexDirection="column">
    <HStack justify="space-between" mb={1} flexShrink={0}>
      <HStack spacing={2}>
        <Box w={3} h={3} borderRadius="full" bg={color} flexShrink={0} />
        <Text fontSize="sm" fontWeight="semibold" color="white">{label}</Text>
      </HStack>
      <Text fontSize="xs" color="gray.500" fontFamily="mono">
        {data.length ? `${Number(data[data.length - 1].v).toFixed(3)} ${unit}` : '—'}
      </Text>
    </HStack>
    <Box flex="1" minH={0}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="t"
            type="number"
            domain={['dataMin', 'dataMax']}
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 10 }}
            tickFormatter={(v) => `${v.toFixed(1)}s`}
            minTickGap={24}
          />
          <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF', fontSize: 10 }} domain={['auto', 'auto']} width={48} />
          <RechartsTooltip
            contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '6px', color: '#F9FAFB', fontSize: '11px' }}
            labelFormatter={(v) => `t: ${Number(v).toFixed(2)}s`}
            formatter={(v) => [Number(v).toFixed(6), label]}
          />
          <Line type="linear" dataKey="v" stroke={color} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </Box>
  </Box>
))
MiniChart.displayName = 'MiniChart'

const ControlTab = ({ isActive = true }) => {
  const { status, series, connected } = useControlTelemetry(isActive)

  const [mode, setMode] = useState('velocity')
  const [targetText, setTargetText] = useState('0.5')
  const [hardwareSource, setHardwareSourceState] = useState('sim')
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)

  const running = status?.running ?? false

  // Sync local UI state (mode select, source selector) from the backend's
  // authoritative status once it starts arriving over the websocket.
  useEffect(() => {
    if (!status) return
    setHardwareSourceState(status.hardware_source)
    if (status.running && status.mode) setMode(status.mode)
    // Deliberately narrow deps: `status` also carries latest_sample, which
    // changes every tick — depending on the whole object would re-run this
    // sync loop at telemetry rate for no reason.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.hardware_source, status?.running, status?.mode])

  const chartData = useMemo(() => {
    if (!series.length) return { position: [], velocity: [], torque: [] }
    const t0 = series[0].t
    const position = []
    const velocity = []
    const torque = []
    for (const s of series) {
      const t = s.t - t0
      position.push({ t, v: s.position })
      velocity.push({ t, v: s.velocity })
      torque.push({ t, v: s.torque_est })
    }
    return { position, velocity, torque }
  }, [series])

  const targetNumber = Number(targetText)
  const targetValid = targetText !== '' && Number.isFinite(targetNumber)

  const handleStart = async () => {
    if (!targetValid) {
      setActionError('Target must be a number')
      return
    }
    setActionError(null)
    setBusy(true)
    try {
      await startControlSession(mode, targetNumber)
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
      setActionError('Target must be a number')
      return
    }
    setActionError(null)
    try {
      await setControlTarget(targetNumber)
    } catch (e) {
      setActionError(e.message)
    }
  }

  const handleHardwareSourceChange = async (source) => {
    setActionError(null)
    try {
      const res = await apiSetHardwareSource(source)
      setHardwareSourceState(res.hardware_source)
    } catch (e) {
      setActionError(e.message)
    }
  }

  const latest = status?.latest_sample
  const logFilename = status?.log_path ? status.log_path.split('/').pop() : null
  const backendErrors = status?.errors ?? []

  return (
    <Box p={4} h="100%" maxW="1400px" mx="auto" overflow="auto">
      <VStack spacing={4} align="stretch">
        {/* Hardware source — unmistakable so nobody thinks the sim is a real motor */}
        <Box
          p={3}
          borderRadius="md"
          bg={hardwareSource === 'real' ? 'red.900' : 'yellow.900'}
          border="2px solid"
          borderColor={hardwareSource === 'real' ? 'red.400' : 'yellow.400'}
        >
          <HStack justify="space-between" wrap="wrap">
            <HStack spacing={3}>
              <Badge colorScheme={hardwareSource === 'real' ? 'red' : 'yellow'} fontSize="md" px={3} py={1}>
                {hardwareSource === 'real' ? 'REAL HARDWARE' : 'SIM'}
              </Badge>
              <Text fontWeight="bold" color="white">
                {hardwareSource === 'real'
                  ? 'Commands go to a real motor.'
                  : 'No real motor is moving — dynamics are simulated.'}
              </Text>
            </HStack>
            <HStack>
              <Button
                size="sm"
                colorScheme="yellow"
                variant={hardwareSource === 'sim' ? 'solid' : 'outline'}
                isDisabled={running}
                onClick={() => handleHardwareSourceChange('sim')}
              >
                Sim
              </Button>
              <Button
                size="sm"
                colorScheme="red"
                variant={hardwareSource === 'real' ? 'solid' : 'outline'}
                isDisabled={running}
                onClick={() => handleHardwareSourceChange('real')}
              >
                Real
              </Button>
            </HStack>
          </HStack>
        </Box>

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

        {/* Mode / target / run controls */}
        <Card bg="gray.800" variant="elevated">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="white">Control</Heading>
              <Badge colorScheme={connected ? 'green' : 'gray'} variant="outline">
                {connected ? 'connected' : 'disconnected'}
              </Badge>
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={4}>
              <HStack spacing={4} wrap="wrap">
                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Mode</Text>
                  <Select
                    size="sm"
                    w="140px"
                    value={mode}
                    isDisabled={running}
                    onChange={(e) => setMode(e.target.value)}
                  >
                    <option value="velocity">Velocity</option>
                    <option value="torque">Torque</option>
                  </Select>
                </Box>

                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Target</Text>
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

                <VStack align="stretch" spacing={1} justify="flex-end">
                  <Text fontSize="xs" color="transparent" userSelect="none">.</Text>
                  {running ? (
                    <Button size="sm" colorScheme="odrive" onClick={handleRetarget} isDisabled={!targetValid}>
                      Set target
                    </Button>
                  ) : (
                    <Button size="sm" colorScheme="green" onClick={handleStart} isDisabled={!targetValid || busy}>
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
                  <StatLabel color="gray.300">Position</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{(latest?.position ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="gray.400">turns</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Velocity</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{(latest?.velocity ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="gray.400">turns/s</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Torque (est.)</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{(latest?.torque_est ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="gray.400">Nm</Text>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Current (Iq)</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{(latest?.current_iq ?? 0).toFixed(3)}</StatNumber>
                  <Text fontSize="xs" color="gray.400">A</Text>
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

        {/* Live charts */}
        <SimpleGrid columns={{ base: 1, lg: 3 }} spacing={4}>
          <MiniChart label="Position" unit="turns" color="#63B3ED" data={chartData.position} />
          <MiniChart label="Velocity" unit="turns/s" color="#68D391" data={chartData.velocity} />
          <MiniChart label="Torque (est.)" unit="Nm" color="#F6AD55" data={chartData.torque} />
        </SimpleGrid>
      </VStack>
    </Box>
  )
}

export default ControlTab
