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
  Select,
  Switch,
  FormControl,
  FormLabel,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  List,
  ListItem,
} from '@chakra-ui/react'

import { useControlTelemetry } from '../../../hooks/useControlTelemetry'
import { getProfiles } from '../../../api/profiles'
import {
  startProfileSession,
  stopControlSession,
  setControlTarget,
  setHardwareSource as apiSetHardwareSource,
} from '../../../api/control'
import MiniChart from '../control/MiniChart'

const PHASE_COLOR = {
  concentric: 'green',
  top_hold: 'yellow',
  eccentric: 'orange',
  bottom_hold: 'gray',
}

const PHASE_LABEL = {
  concentric: 'CONCENTRIC',
  top_hold: 'TOP HOLD',
  eccentric: 'ECCENTRIC',
  bottom_hold: 'BOTTOM HOLD',
}

function defaultParamValues(schema) {
  return Object.fromEntries(Object.entries(schema.parameters).map(([key, p]) => [key, p.value]))
}

const ProfilesTab = ({ isActive = true }) => {
  // Same ControlSession-backed status/telemetry the Control tab polls —
  // profiles run as a third mode on the one backend session, not a
  // separate one (spec §3).
  const { status, series, connected } = useControlTelemetry(isActive)

  const [profiles, setProfiles] = useState([])
  const [profilesError, setProfilesError] = useState(null)
  const [selectedName, setSelectedName] = useState('')
  const [paramValues, setParamValues] = useState({})
  const [overloadEnabled, setOverloadEnabled] = useState(false)
  const [overloadRatio, setOverloadRatio] = useState(1.35)
  const [overloadTargetPhase, setOverloadTargetPhase] = useState('eccentric')
  const [hardwareSource, setHardwareSourceState] = useState('sim')
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)

  // Registry-driven — never hardcode profile names here. "overload" is
  // excluded from the base-profile picker: it's a modifier composed over
  // whichever base profile is chosen, not a fifth selectable profile.
  const selectableProfiles = useMemo(() => profiles.filter((p) => !p.is_wrapper), [profiles])
  const selectedProfile = useMemo(
    () => profiles.find((p) => p.name === selectedName),
    [profiles, selectedName]
  )

  useEffect(() => {
    let cancelled = false
    getProfiles()
      .then((list) => {
        if (cancelled) return
        setProfiles(list)
        const first = list.find((p) => !p.is_wrapper)
        if (first) {
          setSelectedName(first.name)
          setParamValues(defaultParamValues(first))
        }
      })
      .catch((e) => setProfilesError(e.message))
    return () => {
      cancelled = true
    }
  }, [])

  // Sync local UI state from the backend's authoritative status, same
  // narrow-deps pattern as ControlTab (status also carries latest_sample,
  // which changes every tick).
  useEffect(() => {
    if (!status) return
    setHardwareSourceState(status.hardware_source)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.hardware_source])

  const running = (status?.running && status?.mode === 'profile') ?? false
  // The backend has exactly one ControlSession — Control and Profiles tabs
  // share it, so a run started from the other tab still blocks starting here.
  const anotherModeRunning = (status?.running && status?.mode !== 'profile') ?? false

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

  const handleSelectProfile = (name) => {
    setSelectedName(name)
    const p = profiles.find((pr) => pr.name === name)
    if (p) setParamValues(defaultParamValues(p))
  }

  const handleParamChange = (key, rawValue) => {
    setParamValues((prev) => ({ ...prev, [key]: rawValue }))
  }

  const paramsAreValid = useMemo(() => {
    if (!selectedProfile) return false
    return Object.keys(selectedProfile.parameters).every((key) => {
      const v = Number(paramValues[key])
      return paramValues[key] !== '' && Number.isFinite(v)
    })
  }, [selectedProfile, paramValues])

  const handleStart = async () => {
    if (!selectedProfile || !paramsAreValid) {
      setActionError('All parameters must be numbers')
      return
    }
    setActionError(null)
    setBusy(true)
    try {
      const params = Object.fromEntries(
        Object.entries(paramValues).map(([k, v]) => [k, Number(v)])
      )
      const overload = overloadEnabled
        ? { enabled: true, ratio: Number(overloadRatio), target_phase: overloadTargetPhase }
        : null
      await startProfileSession(selectedName, params, overload)
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
    if (!selectedProfile) return
    const key = selectedProfile.primary_parameter
    const value = Number(paramValues[key])
    if (!Number.isFinite(value)) {
      setActionError('Primary parameter must be a number')
      return
    }
    setActionError(null)
    try {
      await setControlTarget(value)
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
  const phase = running ? status?.phase : null
  const repCount = running ? status?.rep_count : null

  return (
    <Box p={4} h="100%" maxW="1400px" mx="auto" overflow="auto">
      <VStack spacing={4} align="stretch">
        {/* Stub-math notice — always visible so a demo never oversells this (spec §7) */}
        <Alert status="info" variant="left-accent" borderRadius="md">
          <AlertIcon />
          <AlertDescription fontSize="sm">
            Profile math is placeholder — Phase 2A+. Interface shape only.
          </AlertDescription>
        </Alert>

        {/* Hardware source — same unmissable banner as the Control tab */}
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
                isDisabled={running || anotherModeRunning}
                onClick={() => handleHardwareSourceChange('sim')}
              >
                Sim
              </Button>
              <Button
                size="sm"
                colorScheme="red"
                variant={hardwareSource === 'real' ? 'solid' : 'outline'}
                isDisabled={running || anotherModeRunning}
                onClick={() => handleHardwareSourceChange('real')}
              >
                Real
              </Button>
            </HStack>
          </HStack>
        </Box>

        {profilesError && (
          <Alert status="error" variant="left-accent">
            <AlertIcon />
            <AlertDescription>Failed to load profile registry: {profilesError}</AlertDescription>
          </Alert>
        )}

        {actionError && (
          <Alert status="error" variant="left-accent">
            <AlertIcon />
            <AlertDescription>{actionError}</AlertDescription>
          </Alert>
        )}

        {anotherModeRunning && (
          <Alert status="warning" variant="left-accent">
            <AlertIcon />
            <AlertDescription>
              A {status?.mode} session is running from the Control tab — stop it before starting a profile.
            </AlertDescription>
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

        {/* Profile picker + parameters + overload + run controls */}
        <Card bg="gray.800" variant="elevated">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="white">Resistance Profile</Heading>
              <Badge colorScheme={connected ? 'green' : 'gray'} variant="outline">
                {connected ? 'connected' : 'disconnected'}
              </Badge>
            </HStack>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={4}>
              <HStack spacing={4} wrap="wrap" align="flex-end">
                <Box>
                  <Text fontSize="xs" color="gray.400" mb={1}>Profile</Text>
                  <Select
                    size="sm"
                    w="200px"
                    value={selectedName}
                    isDisabled={running || selectableProfiles.length === 0}
                    onChange={(e) => handleSelectProfile(e.target.value)}
                  >
                    {selectableProfiles.map((p) => (
                      <option key={p.name} value={p.name}>{p.name}</option>
                    ))}
                  </Select>
                </Box>

                {selectedProfile && Object.entries(selectedProfile.parameters).map(([key, schema]) => (
                  <Box key={key}>
                    <Text fontSize="xs" color="gray.400" mb={1}>{schema.label}</Text>
                    <InputGroup size="sm" w="180px">
                      <Input
                        type="number"
                        fontFamily="mono"
                        value={paramValues[key] ?? ''}
                        min={schema.min}
                        max={schema.max}
                        isDisabled={running && key !== selectedProfile.primary_parameter}
                        onChange={(e) => handleParamChange(key, e.target.value)}
                      />
                      {key === selectedProfile.primary_parameter && (
                        <InputRightAddon px={2} fontSize="xs">live</InputRightAddon>
                      )}
                    </InputGroup>
                  </Box>
                ))}

                <VStack align="stretch" spacing={1}>
                  {running ? (
                    <Button size="sm" colorScheme="odrive" onClick={handleRetarget}>
                      Set target
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      colorScheme="green"
                      onClick={handleStart}
                      isDisabled={!paramsAreValid || busy || anotherModeRunning}
                    >
                      Start
                    </Button>
                  )}
                </VStack>

                <VStack align="stretch" spacing={1}>
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

              {/* Eccentric overload — visually a modifier on the chosen profile, not a fifth profile */}
              <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
                <HStack spacing={4} wrap="wrap" align="flex-end">
                  <FormControl display="flex" alignItems="center" w="auto">
                    <FormLabel htmlFor="overload-toggle" mb="0" fontSize="xs" color="gray.400">
                      Eccentric overload
                    </FormLabel>
                    <Switch
                      id="overload-toggle"
                      isChecked={overloadEnabled}
                      isDisabled={running}
                      onChange={(e) => setOverloadEnabled(e.target.checked)}
                    />
                  </FormControl>
                  {overloadEnabled && (
                    <>
                      <Box>
                        <Text fontSize="xs" color="gray.400" mb={1}>Ratio</Text>
                        <Input
                          size="sm"
                          w="100px"
                          type="number"
                          fontFamily="mono"
                          value={overloadRatio}
                          isDisabled={running}
                          onChange={(e) => setOverloadRatio(e.target.value)}
                        />
                      </Box>
                      <Box>
                        <Text fontSize="xs" color="gray.400" mb={1}>Target phase</Text>
                        <Select
                          size="sm"
                          w="140px"
                          value={overloadTargetPhase}
                          isDisabled={running}
                          onChange={(e) => setOverloadTargetPhase(e.target.value)}
                        >
                          <option value="eccentric">Eccentric</option>
                          <option value="concentric">Concentric</option>
                        </Select>
                      </Box>
                    </>
                  )}
                </HStack>
              </Box>

              <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                <Stat>
                  <StatLabel color="gray.300">Phase</StatLabel>
                  <Badge colorScheme={PHASE_COLOR[phase] || 'gray'} fontSize="md" px={3} py={1} mt={1}>
                    {phase ? PHASE_LABEL[phase] : '—'}
                  </Badge>
                </Stat>
                <Stat>
                  <StatLabel color="gray.300">Rep count</StatLabel>
                  <StatNumber color="odrive.300" fontSize="xl">{repCount ?? 0}</StatNumber>
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
              </SimpleGrid>

              <HStack justify="space-between">
                <Text fontSize="xs" color="gray.400">
                  CSV log: {logFilename ? <Text as="span" fontFamily="mono" color="gray.300">{logFilename}</Text> : '—'}
                </Text>
              </HStack>
            </VStack>
          </CardBody>
        </Card>

        {/* Live charts — same MiniChart component the Control tab uses */}
        <SimpleGrid columns={{ base: 1, lg: 3 }} spacing={4}>
          <MiniChart label="Position" unit="turns" color="#63B3ED" data={chartData.position} />
          <MiniChart label="Velocity" unit="turns/s" color="#68D391" data={chartData.velocity} />
          <MiniChart label="Torque (est.)" unit="Nm" color="#F6AD55" data={chartData.torque} />
        </SimpleGrid>
      </VStack>
    </Box>
  )
}

export default ProfilesTab
