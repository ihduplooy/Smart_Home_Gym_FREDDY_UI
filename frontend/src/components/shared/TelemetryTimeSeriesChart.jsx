import { useMemo, useState } from 'react'
import { Box, HStack, VStack, Text, Checkbox, Select, Button, ButtonGroup, Badge, Card, CardHeader, CardBody, Heading } from '@chakra-ui/react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer } from 'recharts'
import AxisRangeControl from './AxisRangeControl'
import { domainFromRange, filterByRange, movingAverage } from '../../utils/chartDisplay'
import { useFreezableSeries } from '../../hooks/useFreezableSeries'

// Smoothing window options (samples in a trailing moving average) -- "Off"
// (1) leaves the raw telemetry untouched, matching chartDisplay.js's
// movingAverage() no-op at window<=1.
const SMOOTHING_OPTIONS = [1, 3, 5, 10, 20]

const DEFAULT_RANGE = { auto: true, min: '', max: '' }

// One consolidated telemetry time-series chart, shared by the Train and
// Control tabs (originally Train-only -- train_tab_build_spec.md §5/§6 --
// generalized 29 July 2026 once the same axis-scaling / pause / per-line
// controls were requested for Control and Inspector too; Inspector's own
// per-property cards get the same controls individually rather than being
// merged onto one shared multi-line chart, since its property list is
// arbitrary/user-picked rather than a small fixed set -- see
// components/tabs/inspector/LiveCharts.jsx instead).
//
// `lines`: [{ key, label, color, unit, defaultOn, side: 'left'|'right',
// axisKey?, dashed?, lineType? }]. Each line gets its own checkbox and Y
// axis by default (wildly different magnitudes/units on one shared axis
// makes the smaller ones unreadable whenever a larger one is also on) --
// set `axisKey` to another line's `key` to plot two lines on the same axis
// instead (e.g. an actual value and its commanded target), in which case
// only the "owning" line (the one whose own key equals its axisKey) renders
// axis-range/invert controls and the YAxis itself, since duplicating those
// per line sharing an axis would just be confusing. `dashed`/`lineType`
// (default 'linear') let a target/overlay line look visually distinct from
// the value it's paired with.
//
// Pause/freeze (item 5) lives inside this component via useFreezableSeries
// rather than in each caller -- one Pause/Resume button, next to the
// heading, freezes the chart on a snapshot without touching the caller's
// own polling; remount the component (a `key` prop bump, same pattern used
// elsewhere for a full state wipe) to drop an active freeze from outside,
// e.g. on a tab's own Reset action.
//
// Range options are capped at the actual buffered duration (`bufferS`)
// rather than a fixed list that could silently offer more than the buffer
// really holds -- see docs/decisions.md ("Train tab" entry) for the bug
// this was originally built to fix.
const DEFAULT_RANGE_OPTIONS_SECONDS = [10, 30, 60, 120]

const TelemetryTimeSeriesChart = ({
  series,
  lines,
  bufferS = 90,
  rangeOptionsSeconds = DEFAULT_RANGE_OPTIONS_SECONDS,
  title = 'Telemetry over time',
  height = '380px',
}) => {
  const { displaySeries, paused, togglePause } = useFreezableSeries(series)

  const [enabledLines, setEnabledLines] = useState(() =>
    Object.fromEntries(lines.map((l) => [l.key, l.defaultOn]))
  )
  const [rangeSeconds, setRangeSeconds] = useState(null)
  const [axisRanges, setAxisRanges] = useState(() =>
    Object.fromEntries(lines.map((l) => [l.key, DEFAULT_RANGE]))
  )
  const [invertedLines, setInvertedLines] = useState(() =>
    Object.fromEntries(lines.map((l) => [l.key, false]))
  )
  const [smoothingWindows, setSmoothingWindows] = useState(() =>
    Object.fromEntries(lines.map((l) => [l.key, 1]))
  )

  const rangeOptions = useMemo(
    () => [
      ...rangeOptionsSeconds.filter((s) => s <= bufferS).map((s) => ({ key: `${s}s`, seconds: s })),
      { key: 'All', seconds: null },
    ],
    [rangeOptionsSeconds, bufferS]
  )

  const chartData = useMemo(() => {
    if (!displaySeries || !displaySeries.length) return []
    const t0 = displaySeries[0].t
    return displaySeries.map((s) => ({ ...s, t: s.t - t0 }))
  }, [displaySeries])

  const displayData = useMemo(() => filterByRange(chartData, rangeSeconds), [chartData, rangeSeconds])

  // Smoothing is applied per enabled line, in sequence -- movingAverage()
  // only touches the one key it's given, so chaining across lines is safe
  // (each pass leaves every other line's values untouched).
  const smoothedData = useMemo(() => {
    let result = displayData
    for (const l of lines) {
      if (!enabledLines[l.key]) continue
      const window = smoothingWindows[l.key] ?? 1
      if (window > 1) result = movingAverage(result, l.key, window)
    }
    return result
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayData, enabledLines, smoothingWindows])

  const toggleLine = (key) => setEnabledLines((prev) => ({ ...prev, [key]: !prev[key] }))
  const setAxisRange = (key, range) => setAxisRanges((prev) => ({ ...prev, [key]: range }))
  const toggleInvert = (key) => setInvertedLines((prev) => ({ ...prev, [key]: !prev[key] }))
  const setSmoothing = (key, window) => setSmoothingWindows((prev) => ({ ...prev, [key]: window }))

  const activeLines = lines.filter((l) => enabledLines[l.key])
  // Lines sharing another line's axisKey don't get their own YAxis -- only
  // the "owner" (axisKey === key) does, so a target/overlay line doesn't
  // duplicate axis-range controls or render a second redundant axis.
  const axisOwnerKeys = new Set(activeLines.map((l) => l.axisKey ?? l.key))
  const activeAxes = lines.filter((l) => (l.axisKey ?? l.key) === l.key && axisOwnerKeys.has(l.key))
  // Multiple axes on the same side stack outward automatically in recharts,
  // but the chart's own right margin has to grow to make room or the
  // outermost axis's ticks/label get clipped at the container edge.
  const rightAxisCount = activeAxes.filter((l) => l.side === 'right').length
  const marginRight = 16 + Math.max(0, rightAxisCount - 1) * 64
  const rightCount = { current: 0 }

  return (
    <Card bg="gray.800" variant="elevated">
      <CardHeader pb={2}>
        <VStack align="stretch" spacing={2}>
          <HStack justify="space-between">
            <HStack spacing={2}>
              <Heading size="sm" color="white">{title}</Heading>
              {paused && <Badge colorScheme="yellow" variant="solid">Frozen</Badge>}
            </HStack>
            <Button size="xs" variant="outline" onClick={togglePause} isDisabled={!series || series.length === 0}>
              {paused ? 'Resume' : 'Pause'}
            </Button>
          </HStack>
          <VStack align="stretch" spacing={1}>
            {lines.map((l) => {
              const isAxisOwner = (l.axisKey ?? l.key) === l.key
              return (
                <HStack key={l.key} spacing={4} wrap="wrap">
                  <Checkbox
                    isChecked={enabledLines[l.key]}
                    onChange={() => toggleLine(l.key)}
                    colorScheme="odrive"
                    size="sm"
                    minW="180px"
                  >
                    <Text fontSize="xs" color="gray.300">{l.label} <Text as="span" color="gray.500">({l.unit})</Text></Text>
                  </Checkbox>
                  {enabledLines[l.key] && isAxisOwner && (
                    <>
                      <AxisRangeControl
                        label="Y range"
                        color={l.color}
                        range={axisRanges[l.key]}
                        onChange={(range) => setAxisRange(l.key, range)}
                      />
                      <Checkbox
                        size="sm"
                        isChecked={invertedLines[l.key]}
                        onChange={() => toggleInvert(l.key)}
                        colorScheme="odrive"
                      >
                        <Text fontSize="xs" color="gray.400">Invert Y</Text>
                      </Checkbox>
                    </>
                  )}
                  {enabledLines[l.key] && (
                    <HStack spacing={1}>
                      <Text fontSize="xs" color="gray.400">Smooth</Text>
                      <Select
                        size="xs"
                        w="60px"
                        value={smoothingWindows[l.key]}
                        onChange={(e) => setSmoothing(l.key, Number(e.target.value))}
                      >
                        {SMOOTHING_OPTIONS.map((w) => (
                          <option key={w} value={w}>{w === 1 ? 'Off' : w}</option>
                        ))}
                      </Select>
                    </HStack>
                  )}
                </HStack>
              )
            })}
          </VStack>
          <ButtonGroup size="xs" isAttached variant="outline">
            {rangeOptions.map((opt) => (
              <Button
                key={opt.key}
                onClick={() => setRangeSeconds(opt.seconds)}
                colorScheme={rangeSeconds === opt.seconds ? 'odrive' : 'gray'}
                variant={rangeSeconds === opt.seconds ? 'solid' : 'outline'}
              >
                {opt.key}
              </Button>
            ))}
          </ButtonGroup>
        </VStack>
      </CardHeader>
      <CardBody pt={0}>
        <Box h={height}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={smoothedData} margin={{ top: 4, right: marginRight, left: 0, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="t"
                type="number"
                domain={['dataMin', 'dataMax']}
                stroke="#9CA3AF"
                tick={{ fill: '#9CA3AF', fontSize: 10 }}
                tickFormatter={(v) => `${v.toFixed(1)}s`}
                minTickGap={24}
                label={{ value: 'Time (s)', position: 'insideBottom', offset: -8, fill: '#9CA3AF', fontSize: 11 }}
              />
              {activeAxes.map((l) => {
                const offset = l.side === 'right' ? rightCount.current++ * 56 : 0
                return (
                  <YAxis
                    key={l.key}
                    yAxisId={l.key}
                    orientation={l.side}
                    reversed={invertedLines[l.key]}
                    domain={domainFromRange(axisRanges[l.key])}
                    stroke={l.color}
                    tick={{ fill: l.color, fontSize: 10 }}
                    width={56}
                    {...(l.side === 'right' ? { dx: offset } : {})}
                    label={{ value: `${l.label.split(' ')[0]} (${l.unit})`, angle: -90, position: l.side === 'right' ? 'insideRight' : 'insideLeft', fill: l.color, fontSize: 11 }}
                  />
                )
              })}
              <RechartsTooltip
                contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '6px', color: '#F9FAFB', fontSize: '11px' }}
                labelFormatter={(v) => `t: ${Number(v).toFixed(2)}s`}
                formatter={(v, name) => [v == null ? '—' : Number(v).toFixed(4), name]}
              />
              <Legend wrapperStyle={{ fontSize: '11px' }} />
              {activeLines.map((l) => (
                <Line
                  key={l.key}
                  yAxisId={l.axisKey ?? l.key}
                  type={l.lineType ?? 'linear'}
                  dataKey={l.key}
                  name={l.label}
                  stroke={l.color}
                  strokeWidth={l.dashed ? 1.5 : 2}
                  strokeDasharray={l.dashed ? '5 3' : undefined}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </Box>
      </CardBody>
    </Card>
  )
}

export default TelemetryTimeSeriesChart
