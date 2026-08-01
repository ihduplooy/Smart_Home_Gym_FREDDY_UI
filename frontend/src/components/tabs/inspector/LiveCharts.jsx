import { memo, useMemo, useState } from 'react'
import {
  Box,
  VStack,
  HStack,
  Text,
  Badge,
  Button,
  ButtonGroup,
  Checkbox,
  Select,
  IconButton,
  Tooltip,
  SimpleGrid,
  useColorModeValue,
} from '@chakra-ui/react'
import { DeleteIcon, DownloadIcon, CloseIcon } from '@chakra-ui/icons'
import { useSelector, useDispatch } from 'react-redux'
import { removeProperty, clearAll } from '../../../store/slices/telemetrySlice'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts'
import { movingAverage, filterByAgeMs, domainFromRange } from '../../../utils/chartDisplay'
import { useFreezableSeries } from '../../../hooks/useFreezableSeries'
import AxisRangeControl from '../../shared/AxisRangeControl'
import { FIXED_AXIS_TELEMETRY_PATH_LIST } from './fixedAxisTelemetry'

// Smoothing window options -- same set/convention as the Train/Control
// charts' (components/shared/TelemetryTimeSeriesChart.jsx): "Off" (1)
// leaves the raw telemetry untouched. Previously a fixed, non-configurable
// SMOOTHING_WINDOW=5 here; made per-property and user-controlled (29 July
// 2026, "same graphs everywhere" pass) for consistency with the other two
// tabs' charts, defaulting to Off like theirs do.
const SMOOTHING_OPTIONS = [1, 3, 5, 10, 20]

const DEFAULT_RANGE = { auto: true, min: '', max: '' }

// Shared duration control for every property card at once (rather than per
// card -- a "how much history am I looking at" view setting is naturally
// one shared choice, same as Train/Control's one range-button-group for
// their whole chart). In ms since Inspector's raw samples carry epoch-ms
// timestamps (filterByAgeMs, not the relative-seconds filterByRange Train/
// Control use). `null` ("All") is the default, matching
// TelemetryTimeSeriesChart's own default of showing everything up to
// whatever the buffer holds.
const WINDOW_MS_OPTIONS = [
  { key: '1s', ms: 1000 },
  { key: '2.5s', ms: 2500 },
  { key: '5s', ms: 5000 },
  { key: '10s', ms: 10000 },
]

// Stable frozen telemetry view used when the Inspector tab is hidden so the
// chart doesn't re-render at the raw WebSocket rate while off-screen.
const FROZEN_TELEMETRY = Object.freeze({ selectedProperties: [], samples: {}, status: 'disconnected' })

const COLORS = [
  '#63B3ED', '#68D391', '#F6AD55', '#FC8181',
  '#B794F6', '#4FD1C7', '#FBB6CE', '#9AE6B4',
  '#90CDF4', '#F687B3', '#76E4F7', '#FBD38D',
]

const leafName = (path) => path.split('.').pop()

// One chart for a single property. Memoized on its own data/range/inverted/
// smoothingWindow so a new sample for property A doesn't re-render property
// B's chart. Gained the same per-property axis-range/invert/smoothing
// controls the Train/Control charts already have (29 July 2026, "same
// graphs everywhere" pass) -- kept as one card per property rather than
// merged onto a single multi-line chart like Train/Control's, since
// Inspector's property list is arbitrary and user-picked (could be 1 or
// 10, wildly different units) rather than a small fixed known set.
const PropertyChart = memo(({ path, color, data, range, inverted, smoothingWindow, onRangeChange, onToggleInvert, onSmoothingChange }) => {
  const smoothed = useMemo(
    () => (smoothingWindow > 1 ? movingAverage(data, 'v', smoothingWindow) : data),
    [data, smoothingWindow]
  )
  return (
  <Box bg="gray.800" border="1px solid" borderColor="gray.700" borderRadius="md" p={2} h="320px" display="flex" flexDirection="column">
    <HStack justify="space-between" mb={1} flexShrink={0}>
      <HStack spacing={2} minW={0}>
        <Box w={3} h={3} borderRadius="full" bg={color} flexShrink={0} />
        <Text fontSize="sm" fontWeight="semibold" color="white" isTruncated>{leafName(path)}</Text>
      </HStack>
      <Text fontSize="xs" color="gray.500" fontFamily="mono" flexShrink={0} pr={6}>
        {data.length ? Number(data[data.length - 1].v).toFixed(3) : '—'}
      </Text>
    </HStack>
    <HStack spacing={3} wrap="wrap" mb={1} flexShrink={0}>
      <AxisRangeControl label="Y range" color={color} range={range} onChange={onRangeChange} />
      <Checkbox size="sm" isChecked={inverted} onChange={onToggleInvert} colorScheme="odrive">
        <Text fontSize="xs" color="gray.400">Invert Y</Text>
      </Checkbox>
      <HStack spacing={1}>
        <Text fontSize="xs" color="gray.400">Smooth</Text>
        <Select size="xs" w="60px" value={smoothingWindow} onChange={(e) => onSmoothingChange(Number(e.target.value))}>
          {SMOOTHING_OPTIONS.map((w) => (
            <option key={w} value={w}>{w === 1 ? 'Off' : w}</option>
          ))}
        </Select>
      </HStack>
    </HStack>
    <Box flex="1" minH={0}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={smoothed} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
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
          <YAxis
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 10 }}
            domain={domainFromRange(range)}
            reversed={inverted}
            width={48}
          />
          <RechartsTooltip
            contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '6px', color: '#F9FAFB', fontSize: '11px' }}
            labelFormatter={(v) => `t: ${Number(v).toFixed(2)}s`}
            formatter={(v) => [typeof v === 'number' ? v.toFixed(6) : v, leafName(path)]}
          />
          <Line
            type="linear"
            dataKey="v"
            stroke={color}
            strokeWidth={2}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </Box>
  </Box>
  )
})
PropertyChart.displayName = 'PropertyChart'

const LiveCharts = ({ isActive = true }) => {
  const dispatch = useDispatch()
  const { selectedProperties: allSelectedProperties, samples, status } = useSelector(
    (state) => (isActive ? state.telemetry : FROZEN_TELEMETRY)
  )
  // AxisTelemetryCharts.jsx owns a fixed set of axis0 graphs (position/
  // velocity vs. setpoint, currents, computed torque, bus voltage) rendered
  // above this section -- excluded here so each doesn't also get a second,
  // redundant generic card in this free-form/user-picked list. They stay
  // selected (and therefore charted up there) even though they're filtered
  // out of this component's own list.
  const selectedProperties = useMemo(
    () => allSelectedProperties.filter((p) => !FIXED_AXIS_TELEMETRY_PATH_LIST.includes(p)),
    [allSelectedProperties]
  )

  // Pause/freeze (same control the Train/Control charts have, built into
  // components/shared/TelemetryTimeSeriesChart.jsx -- Inspector's per-
  // property card layout doesn't reuse that component directly, so the
  // same useFreezableSeries hook is wired in here instead). One shared
  // freeze across every card at once: `samples` is the whole {path: [...]}
  // map, snapshotted as a unit on pause -- the underlying WebSocket/Redux
  // stream keeps updating unaffected.
  const { displaySeries: displaySamples, paused, togglePause } = useFreezableSeries(samples)

  const [windowMs, setWindowMs] = useState(null) // null = "All", matching TelemetryTimeSeriesChart's own default
  const [axisRanges, setAxisRanges] = useState({}) // path -> {auto,min,max}
  const [invertedProps, setInvertedProps] = useState({}) // path -> bool
  const [smoothingWindows, setSmoothingWindows] = useState({}) // path -> number

  const setAxisRange = (path, range) => setAxisRanges((prev) => ({ ...prev, [path]: range }))
  const toggleInvert = (path) => setInvertedProps((prev) => ({ ...prev, [path]: !prev[path] }))
  const setSmoothing = (path, window) => setSmoothingWindows((prev) => ({ ...prev, [path]: window }))

  const bgColor = useColorModeValue('gray.50', 'gray.900')
  const borderColor = useColorModeValue('gray.200', 'gray.600')

  // Build a per-property data array (relative seconds + value), windowed.
  const chartSeries = useMemo(() => {
    return selectedProperties.map((path, index) => {
      const raw = displaySamples[path] || []
      const slice = filterByAgeMs(raw, windowMs)
      const t0 = slice.length ? slice[0].t : 0
      const data = slice.map((s) => ({
        t: (s.t - t0) / 1000,
        v: typeof s.v === 'boolean' ? (s.v ? 1 : 0) : s.v,
      }))
      return { path, color: COLORS[index % COLORS.length], data }
    })
  }, [selectedProperties, displaySamples, windowMs])

  // Stack vertically; switch to two columns once more than two are selected.
  const columns = selectedProperties.length > 2 ? 2 : 1

  return (
    <Box h="100%" bg={bgColor} display="flex" flexDirection="column">
      {/* Header */}
      <VStack align="stretch" spacing={2} p={4} borderBottom="1px solid" borderColor={borderColor} flexShrink={0}>
        <HStack justify="space-between" align="center">
          <VStack spacing={1} align="start">
            <HStack spacing={2}>
              <Text fontSize="lg" fontWeight="medium" color="white">Custom Properties</Text>
              {paused && <Badge colorScheme="yellow" variant="solid">Frozen</Badge>}
            </HStack>
            <HStack spacing={2}>
              <Badge colorScheme={status === 'connected' ? 'green' : 'gray'} variant="outline">{status}</Badge>
              <Text fontSize="xs" color="gray.400">
                {selectedProperties.length} {selectedProperties.length === 1 ? 'property' : 'properties'} • realtime
              </Text>
            </HStack>
          </VStack>

          <HStack spacing={2}>
            <Button size="sm" variant="outline" onClick={togglePause} isDisabled={selectedProperties.length === 0}>
              {paused ? 'Resume' : 'Pause'}
            </Button>
            <Tooltip label="Clear chart data">
              <IconButton size="sm" icon={<DeleteIcon />} onClick={() => dispatch(clearAll())} aria-label="Clear data" />
            </Tooltip>
            <Tooltip label="Export data (JSON)">
              <IconButton
                size="sm"
                icon={<DownloadIcon />}
                onClick={() => {
                  const dataStr = JSON.stringify(samples, null, 2)
                  const blob = new Blob([dataStr], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `odrive-telemetry-${Date.now()}.json`
                  a.click()
                  URL.revokeObjectURL(url)
                }}
                aria-label="Export data"
              />
            </Tooltip>
          </HStack>
        </HStack>

        <ButtonGroup size="xs" isAttached variant="outline">
          {WINDOW_MS_OPTIONS.map((opt) => (
            <Button
              key={opt.key}
              onClick={() => setWindowMs(opt.ms)}
              colorScheme={windowMs === opt.ms ? 'odrive' : 'gray'}
              variant={windowMs === opt.ms ? 'solid' : 'outline'}
            >
              {opt.key}
            </Button>
          ))}
          <Button
            onClick={() => setWindowMs(null)}
            colorScheme={windowMs === null ? 'odrive' : 'gray'}
            variant={windowMs === null ? 'solid' : 'outline'}
          >
            All
          </Button>
        </ButtonGroup>
      </VStack>

      {/* Charts */}
      <Box flex="1" minH={0} overflowY="auto" p={4}>
        {selectedProperties.length === 0 ? (
          <VStack spacing={4} justify="center" align="center" h="100%" color="gray.400">
            <Text fontSize="lg">No properties selected</Text>
            <Text fontSize="sm" textAlign="center">
              Tick the checkbox next to a property in the tree to chart it.
            </Text>
          </VStack>
        ) : (
          <SimpleGrid columns={columns} spacing={4}>
            {chartSeries.map(({ path, color, data }) => (
              <Box key={path} position="relative">
                <Tooltip label="Remove chart">
                  <IconButton
                    size="xs"
                    icon={<CloseIcon />}
                    aria-label={`Remove ${path}`}
                    position="absolute"
                    top={2}
                    right={2}
                    zIndex={1}
                    variant="ghost"
                    colorScheme="red"
                    onClick={() => dispatch(removeProperty(path))}
                  />
                </Tooltip>
                <PropertyChart
                  path={path}
                  color={color}
                  data={data}
                  range={axisRanges[path] ?? DEFAULT_RANGE}
                  inverted={Boolean(invertedProps[path])}
                  smoothingWindow={smoothingWindows[path] ?? 1}
                  onRangeChange={(range) => setAxisRange(path, range)}
                  onToggleInvert={() => toggleInvert(path)}
                  onSmoothingChange={(window) => setSmoothing(path, window)}
                />
              </Box>
            ))}
          </SimpleGrid>
        )}
      </Box>
    </Box>
  )
}

export default LiveCharts
