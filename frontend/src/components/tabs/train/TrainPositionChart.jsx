import { useMemo, useState } from 'react'
import { Box, VStack, HStack, Card, CardHeader, CardBody, Heading, Text, Checkbox, Input, InputGroup, InputLeftAddon } from '@chakra-ui/react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer } from 'recharts'
import AxisRangeControl from '../../shared/AxisRangeControl'
import { domainFromRange } from '../../../utils/chartDisplay'

const DEFAULT_RANGE = { auto: true, min: '', max: '' }

// A per-curve scale multiplier (default 1 = unchanged) -- lets an
// uncalibrated Actual (or Planned) curve be nudged onto the same scale as
// the other for visual comparison, without touching the underlying values
// anywhere else (this component's own display copy only).
const scalePoints = (points, factor) =>
  factor === 1 ? points : points.map((p) => ({ ...p, force_n: p.force_n * factor }))

// Graph B (spec §5): planned/target force-vs-position curve (the static
// profile shape, from the SAME core.cable.train_profiles evaluator the
// profile editor's own preview graph uses -- one source of truth, spec §4)
// overlaid with the live actual force-vs-position while a session runs.
//
// Planned and Actual each get their OWN Y axis (25 July 2026, requested):
// the live actual force can swing far wider than the planned curve
// (calibration/scaling is a known open item, see docs/decisions.md), which
// squashed the planned curve flat on a shared axis. Independent axes plus
// the same Auto/manual-range control as the time-series chart let both
// curves stay readable regardless of how far apart their scales are.
//
// `plannedPoints`/`actualPoints` are independently-sampled series sharing
// only the X (position_m) axis -- recharts supports a Line supplying its
// own `data` distinct from the chart's, which is exactly what's needed here
// rather than trying to merge two differently-spaced series into one array.
const TrainPositionChart = ({ plannedPoints, actualPoints, positionRangeM }) => {
  const domain = useMemo(() => positionRangeM ?? [0, 1], [positionRangeM])
  const [plannedRange, setPlannedRange] = useState(DEFAULT_RANGE)
  const [actualRange, setActualRange] = useState(DEFAULT_RANGE)
  const [plannedInverted, setPlannedInverted] = useState(false)
  const [actualInverted, setActualInverted] = useState(false)
  const [plannedFactorText, setPlannedFactorText] = useState('1')
  const [actualFactorText, setActualFactorText] = useState('1')

  const plannedFactor = Number(plannedFactorText)
  const actualFactor = Number(actualFactorText)
  const scaledPlannedPoints = useMemo(
    () => scalePoints(plannedPoints, Number.isFinite(plannedFactor) ? plannedFactor : 1),
    [plannedPoints, plannedFactor]
  )
  const scaledActualPoints = useMemo(
    () => scalePoints(actualPoints, Number.isFinite(actualFactor) ? actualFactor : 1),
    [actualPoints, actualFactor]
  )

  return (
    <Card bg="gray.800" variant="elevated">
      <CardHeader pb={2}>
        <VStack align="stretch" spacing={2}>
          <Box>
            <Heading size="sm" color="white">Force vs. cable position</Heading>
            <Text fontSize="xs" color="gray.400">Planned profile curve vs. what's actually being commanded live</Text>
          </Box>
          <HStack spacing={6} wrap="wrap">
            <AxisRangeControl label="Planned (N)" color="#F6E05E" range={plannedRange} onChange={setPlannedRange} />
            <Checkbox size="sm" colorScheme="odrive" isChecked={plannedInverted} onChange={() => setPlannedInverted((v) => !v)}>
              <Text fontSize="xs" color="gray.400">Invert Y</Text>
            </Checkbox>
            <InputGroup size="xs" w="90px">
              <InputLeftAddon px={2} fontSize="xs">×</InputLeftAddon>
              <Input fontFamily="mono" value={plannedFactorText} onChange={(e) => setPlannedFactorText(e.target.value)} />
            </InputGroup>
          </HStack>
          <HStack spacing={6} wrap="wrap">
            <AxisRangeControl label="Actual (N)" color="#68D391" range={actualRange} onChange={setActualRange} />
            <Checkbox size="sm" colorScheme="odrive" isChecked={actualInverted} onChange={() => setActualInverted((v) => !v)}>
              <Text fontSize="xs" color="gray.400">Invert Y</Text>
            </Checkbox>
            <InputGroup size="xs" w="90px">
              <InputLeftAddon px={2} fontSize="xs">×</InputLeftAddon>
              <Input fontFamily="mono" value={actualFactorText} onChange={(e) => setActualFactorText(e.target.value)} />
            </InputGroup>
          </HStack>
        </VStack>
      </CardHeader>
      <CardBody pt={0}>
        <Box h="380px">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart margin={{ top: 4, right: 16, left: 0, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="position_m"
                type="number"
                domain={domain}
                stroke="#9CA3AF"
                tick={{ fill: '#9CA3AF', fontSize: 10 }}
                tickFormatter={(v) => `${v.toFixed(2)}m`}
                allowDuplicatedCategory={false}
                label={{ value: 'Cable position (m)', position: 'insideBottom', offset: -8, fill: '#9CA3AF', fontSize: 11 }}
              />
              <YAxis
                yAxisId="planned"
                type="number"
                orientation="left"
                reversed={plannedInverted}
                domain={domainFromRange(plannedRange)}
                stroke="#F6E05E"
                tick={{ fill: '#F6E05E', fontSize: 10 }}
                width={56}
                label={{ value: 'Planned force (N)', angle: -90, position: 'insideLeft', fill: '#F6E05E', fontSize: 11 }}
              />
              <YAxis
                yAxisId="actual"
                type="number"
                orientation="right"
                reversed={actualInverted}
                domain={domainFromRange(actualRange)}
                stroke="#68D391"
                tick={{ fill: '#68D391', fontSize: 10 }}
                width={56}
                label={{ value: 'Actual force (N)', angle: -90, position: 'insideRight', fill: '#68D391', fontSize: 11 }}
              />
              <RechartsTooltip
                contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '6px', color: '#F9FAFB', fontSize: '11px' }}
                labelFormatter={(v) => `pos: ${Number(v).toFixed(3)}m`}
                formatter={(v, name) => [v == null ? '—' : `${Number(v).toFixed(2)} N`, name]}
              />
              <Legend wrapperStyle={{ fontSize: '11px' }} />
              <Line
                yAxisId="planned"
                data={scaledPlannedPoints}
                type="linear"
                dataKey="force_n"
                name="Planned"
                stroke="#F6E05E"
                strokeWidth={2}
                strokeDasharray="5 3"
                dot={false}
                isAnimationActive={false}
              />
              <Line
                yAxisId="actual"
                data={scaledActualPoints}
                type="linear"
                dataKey="force_n"
                name="Actual (live)"
                stroke="#68D391"
                strokeWidth={1.5}
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </Box>
      </CardBody>
    </Card>
  )
}

export default TrainPositionChart
