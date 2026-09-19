import { useMemo } from 'react'
import { Box, HStack, VStack, Text, SimpleGrid, Stat, StatLabel, StatNumber } from '@chakra-ui/react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ReferenceArea, ResponsiveContainer } from 'recharts'

// Band panel: stretch (cable position relative to the configured Length) is
// what matters here, not speed. "Reached target stretch" is a floor test --
// stretch >= targetStretchM - toleranceM -- not a ceiling, since past Length
// the band holds steady rather than dropping (GymProfileEditor's own Band
// doc comment), so there's no natural "too far".

const BandPanel = ({ currentRepPeaks, repHistory, lengthM, targetStretchPct, bandStretchTolerancePct }) => {
  const targetStretchM = lengthM * (targetStretchPct / 100)
  const toleranceM = lengthM * (bandStretchTolerancePct / 100)

  const livePositionM = currentRepPeaks.peakCableLengthM
  const liveStretchPct = lengthM > 0 ? Math.min(100, (livePositionM / lengthM) * 100) : 0
  const liveForceN = currentRepPeaks.peakForceN

  const repsReachedTarget = repHistory.filter((r) => r.peakCableLengthM >= targetStretchM - toleranceM).length
  const avgPeakStretchPct = repHistory.length
    ? (repHistory.reduce((s, r) => s + (lengthM > 0 ? r.peakCableLengthM / lengthM : 0), 0) / repHistory.length) * 100
    : 0
  const avgPeakForceN = repHistory.length ? repHistory.reduce((s, r) => s + r.peakForceN, 0) / repHistory.length : 0

  const barData = useMemo(
    () => repHistory.map((r) => ({ rep: r.rep, stretchPct: lengthM > 0 ? Math.min(100, (r.peakCableLengthM / lengthM) * 100) : 0 })),
    [repHistory, lengthM]
  )

  return (
    <VStack align="stretch" spacing={5}>
      <HStack spacing={8} justify="center" wrap="wrap">
        <VStack spacing={1} minW="220px">
          <Text fontSize="xs" color="paper.textSecondary">Cable position</Text>
          <Text fontSize="2xl" fontFamily="mono" fontWeight="semibold" color="paper.textPrimary">
            {liveStretchPct.toFixed(0)}%
          </Text>
          <Box w="100%" h="10px" borderRadius="full" bgGradient="linear(to-r, gray.200, accent.500)" position="relative">
            <Box
              position="absolute"
              top="-3px"
              left={`calc(${Math.min(100, liveStretchPct)}% - 4px)`}
              w="16px"
              h="16px"
              borderRadius="full"
              bg="paper.textPrimary"
              border="2px solid white"
            />
          </Box>
          <HStack justify="space-between" w="100%">
            <Text fontSize="0.65rem" color="paper.textSecondary">0%</Text>
            <Text fontSize="0.65rem" color="paper.textSecondary">100%</Text>
          </HStack>
        </VStack>
        <VStack spacing={1}>
          <Text fontSize="xs" color="paper.textSecondary">Current force</Text>
          <Text fontSize="2xl" fontFamily="mono" fontWeight="semibold" color="paper.textPrimary">
            {liveForceN.toFixed(0)} <Text as="span" fontSize="xs" color="paper.textSecondary">N</Text>
          </Text>
        </VStack>
      </HStack>

      <Box>
        <Text fontSize="xs" color="paper.textSecondary" mb={1}>Peak stretch per rep</Text>
        <Box h="160px" bg="paper.bg" borderRadius="md" p={2}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E4E4E7" />
              <XAxis dataKey="rep" stroke="#71717A" tick={{ fill: '#71717A', fontSize: 10 }} />
              <YAxis stroke="#71717A" tick={{ fill: '#71717A', fontSize: 10 }} domain={[0, 100]} width={40} />
              <RechartsTooltip
                contentStyle={{ backgroundColor: '#FFFFFF', border: '1px solid #E4E4E7', borderRadius: '6px', color: '#18181B', fontSize: '11px' }}
                formatter={(v) => [`${Number(v).toFixed(0)}%`, 'peak stretch']}
              />
              {lengthM > 0 && (
                <ReferenceArea
                  y1={Math.max(0, targetStretchPct - bandStretchTolerancePct)}
                  y2={Math.min(100, targetStretchPct + bandStretchTolerancePct)}
                  fill="#38a169"
                  fillOpacity={0.15}
                />
              )}
              <Bar dataKey="stretchPct" fill="#2563eb" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </Box>
      </Box>

      <SimpleGrid columns={3} spacing={4}>
        <Stat>
          <StatLabel fontSize="xs" color="paper.textSecondary">Reached target</StatLabel>
          <StatNumber fontSize="lg" color="paper.textPrimary">{repsReachedTarget}/{repHistory.length}</StatNumber>
        </Stat>
        <Stat>
          <StatLabel fontSize="xs" color="paper.textSecondary">Avg peak stretch</StatLabel>
          <StatNumber fontSize="lg" color="paper.textPrimary">{avgPeakStretchPct.toFixed(0)}%</StatNumber>
        </Stat>
        <Stat>
          <StatLabel fontSize="xs" color="paper.textSecondary">Avg peak force</StatLabel>
          <StatNumber fontSize="lg" color="paper.textPrimary">{avgPeakForceN.toFixed(0)} N</StatNumber>
        </Stat>
      </SimpleGrid>
    </VStack>
  )
}

export default BandPanel
