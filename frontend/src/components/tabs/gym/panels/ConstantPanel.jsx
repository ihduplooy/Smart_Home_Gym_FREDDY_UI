import { useMemo } from 'react'
import { Box, HStack, VStack, Text, SimpleGrid, Stat, StatLabel, StatNumber, CircularProgress, CircularProgressLabel } from '@chakra-ui/react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ReferenceArea, ResponsiveContainer } from 'recharts'
import SemiGauge from '../../../shared/SemiGauge'
import { massKgFromForceN } from '../../../../utils/cableGeometry'

// Constant panel: a target force held steady, rep speed and "stayed within
// tolerance of target" are what matter here -- the rep-speed gauge's zone
// boundaries and the force tolerance both come from config (repSpeedZones
// prop, forceToleranceFraction from GYM's Settings sub-tab), not hardcoded
// pixels/fractions.
//
// "In range" majority threshold (a rep counts toward "reps in range" once
// >=50% of its duration was within tolerance) is this panel's own display
// convention, not a backend concept -- unlike the force tolerance itself
// (bench-unvalidated, hence configurable), this 50% cutoff is just "which
// half of a repeated rep counts", not a physical quantity worth a settings
// row.
const IN_RANGE_MAJORITY_FRACTION = 0.5

const ConstantPanel = ({ speedMS, currentRepPeaks, repHistory, targetForceN, forceToleranceFraction, repSpeedZones }) => {
  const liveTimeInRangeFraction = currentRepPeaks.totalTicks ? currentRepPeaks.inRangeTicks / currentRepPeaks.totalTicks : 0

  const repsInRange = repHistory.filter((r) => r.timeInRangeFraction >= IN_RANGE_MAJORITY_FRACTION).length
  const avgPeakForceN = repHistory.length ? repHistory.reduce((s, r) => s + r.peakForceN, 0) / repHistory.length : 0
  const avgTempoS = repHistory.length ? repHistory.reduce((s, r) => s + r.durationS, 0) / repHistory.length : 0

  const toleranceN = targetForceN * (forceToleranceFraction ?? 0.1)
  const barData = useMemo(() => repHistory.map((r) => ({ rep: r.rep, peakForceN: r.peakForceN })), [repHistory])

  return (
    <VStack align="stretch" spacing={5}>
      <HStack spacing={8} justify="center" wrap="wrap">
        <SemiGauge
          value={speedMS}
          min={0}
          max={repSpeedZones.max}
          zones={[
            { from: 0, to: repSpeedZones.low, color: '#e53e3e' },
            { from: repSpeedZones.low, to: repSpeedZones.high, color: '#38a169' },
            { from: repSpeedZones.high, to: repSpeedZones.max, color: '#e53e3e' },
          ]}
          unit="m/s"
          label="Rep speed"
        />
        <VStack spacing={1}>
          <CircularProgress value={liveTimeInRangeFraction * 100} color="accent.600" size="120px" thickness="10px">
            <CircularProgressLabel fontSize="xl" fontFamily="mono" color="paper.textPrimary">
              {(liveTimeInRangeFraction * 100).toFixed(0)}%
            </CircularProgressLabel>
          </CircularProgress>
          <Text fontSize="xs" color="paper.textSecondary">In target (this rep)</Text>
        </VStack>
      </HStack>

      <Box>
        <Text fontSize="xs" color="paper.textSecondary" mb={1}>Peak force per rep</Text>
        <Box h="160px" bg="paper.bg" borderRadius="md" p={2}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E4E4E7" />
              <XAxis dataKey="rep" stroke="#71717A" tick={{ fill: '#71717A', fontSize: 10 }} />
              <YAxis stroke="#71717A" tick={{ fill: '#71717A', fontSize: 10 }} width={40} />
              <RechartsTooltip
                contentStyle={{ backgroundColor: '#FFFFFF', border: '1px solid #E4E4E7', borderRadius: '6px', color: '#18181B', fontSize: '11px' }}
                formatter={(v) => [`${Number(v).toFixed(1)} N`, 'peak force']}
              />
              {targetForceN > 0 && (
                <ReferenceArea y1={targetForceN - toleranceN} y2={targetForceN + toleranceN} fill="#38a169" fillOpacity={0.15} />
              )}
              <Bar dataKey="peakForceN" fill="#eda100" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </Box>
      </Box>

      <SimpleGrid columns={3} spacing={4}>
        <Stat>
          <StatLabel fontSize="xs" color="paper.textSecondary">Reps in range</StatLabel>
          <StatNumber fontSize="lg" color="paper.textPrimary">{repsInRange}/{repHistory.length}</StatNumber>
        </Stat>
        <Stat>
          <StatLabel fontSize="xs" color="paper.textSecondary">Avg peak force</StatLabel>
          <StatNumber fontSize="lg" color="paper.textPrimary">
            {avgPeakForceN.toFixed(0)} N <Text as="span" fontSize="xs" color="paper.textSecondary">({massKgFromForceN(avgPeakForceN).toFixed(1)} kg)</Text>
          </StatNumber>
        </Stat>
        <Stat>
          <StatLabel fontSize="xs" color="paper.textSecondary">Avg tempo</StatLabel>
          <StatNumber fontSize="lg" color="paper.textPrimary">{avgTempoS > 0 ? `${avgTempoS.toFixed(1)} s` : '—'}</StatNumber>
        </Stat>
      </SimpleGrid>
    </VStack>
  )
}

export default ConstantPanel
