import { useMemo } from 'react'
import { Box, HStack, VStack, Text, Badge, SimpleGrid, Stat, StatLabel, StatNumber, Icon } from '@chakra-ui/react'
import { ArrowUp, ArrowDown } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ReferenceLine, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts'
import { massKgFromForceN } from '../../../../utils/cableGeometry'

// Concentric/Eccentric panel: force alternates by movement direction, so
// "peak force per rep" splits into two mirrored halves (concentric up from
// a center line, eccentric down) rather than one bar -- same color coding
// as the phase indicator so the two stay visually tied together.

// Threshold below which a rep's mirrored bars count as "good symmetry" --
// this display convention (not a physical quantity, no config value the way
// the tolerances above have one) mirrors ConstantPanel's own
// IN_RANGE_MAJORITY_FRACTION: "which reps count", not something worth a
// settings row.
const SYMMETRY_RATIO_TOLERANCE = 0.25

const ConcentricEccentricPanel = ({ liveExtra, speedMS, repHistory }) => {
  const phase = liveExtra?.phase
  const isConcentric = phase === 'concentric'

  const goodSymmetryReps = repHistory.filter((r) => {
    if (!r.avgConcentricForceN || !r.avgEccentricForceN) return false
    const ratio = r.avgConcentricForceN / r.avgEccentricForceN
    return Math.abs(ratio - 1) <= SYMMETRY_RATIO_TOLERANCE
  }).length

  const avgConcentricForceN = repHistory.length ? repHistory.reduce((s, r) => s + r.avgConcentricForceN, 0) / repHistory.length : 0
  const avgEccentricForceN = repHistory.length ? repHistory.reduce((s, r) => s + r.avgEccentricForceN, 0) / repHistory.length : 0
  const conEccRatio = avgEccentricForceN > 0 ? avgConcentricForceN / avgEccentricForceN : 0

  const barData = useMemo(
    () => repHistory.map((r) => ({ rep: r.rep, concentric: r.peakConcentricForceN, eccentric: -r.peakEccentricForceN })),
    [repHistory]
  )

  return (
    <VStack align="stretch" spacing={5}>
      <HStack spacing={8} justify="center" wrap="wrap">
        <VStack spacing={1}>
          <Text fontSize="xs" color="paper.textSecondary">Current phase</Text>
          <HStack>
            <Icon as={isConcentric ? ArrowUp : ArrowDown} boxSize={6} color={isConcentric ? 'blue.500' : 'purple.500'} />
            <Badge colorScheme={isConcentric ? 'blue' : 'purple'} variant="solid" fontSize="sm">
              {phase ? phase.toUpperCase() : '—'}
            </Badge>
          </HStack>
          <Text fontSize="xs" color="paper.textSecondary">
            {isConcentric ? 'Pulling (lifting)' : phase === 'eccentric' ? 'Lowering' : 'Waiting for movement'}
          </Text>
        </VStack>
        <VStack spacing={1}>
          <Text fontSize="xs" color="paper.textSecondary">Rep speed</Text>
          <Text fontSize="2xl" fontFamily="mono" fontWeight="semibold" color="paper.textPrimary">
            {speedMS.toFixed(2)} <Text as="span" fontSize="xs" color="paper.textSecondary">m/s</Text>
          </Text>
          <Text fontSize="0.65rem" color="paper.textSecondary">
            Commanded: {liveExtra?.target_force_n != null ? massKgFromForceN(liveExtra.target_force_n).toFixed(1) : '—'} kg
          </Text>
        </VStack>
      </HStack>

      <Box>
        <Text fontSize="xs" color="paper.textSecondary" mb={1}>Peak force per rep (concentric / eccentric)</Text>
        <Box h="160px" bg="paper.bg" borderRadius="md" p={2}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E4E4E7" />
              <XAxis dataKey="rep" stroke="#71717A" tick={{ fill: '#71717A', fontSize: 10 }} />
              <YAxis stroke="#71717A" tick={{ fill: '#71717A', fontSize: 10 }} width={40} tickFormatter={(v) => Math.abs(v)} />
              <ReferenceLine y={0} stroke="#71717A" />
              <RechartsTooltip
                contentStyle={{ backgroundColor: '#FFFFFF', border: '1px solid #E4E4E7', borderRadius: '6px', color: '#18181B', fontSize: '11px' }}
                formatter={(v, name) => [`${Math.abs(Number(v)).toFixed(1)} N`, name]}
              />
              <Bar dataKey="concentric" name="concentric" fill="#2563eb" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="eccentric" name="eccentric" fill="#7c3aed" radius={[0, 0, 3, 3]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </Box>
      </Box>

      <SimpleGrid columns={4} spacing={4}>
        <Stat>
          <StatLabel fontSize="xs" color="paper.textSecondary">Good symmetry</StatLabel>
          <StatNumber fontSize="lg" color="paper.textPrimary">{goodSymmetryReps}/{repHistory.length}</StatNumber>
        </Stat>
        <Stat>
          <StatLabel fontSize="xs" color="paper.textSecondary">Con:Ecc ratio</StatLabel>
          <StatNumber fontSize="lg" color="paper.textPrimary">{conEccRatio > 0 ? conEccRatio.toFixed(2) : '—'}</StatNumber>
        </Stat>
        <Stat>
          <StatLabel fontSize="xs" color="paper.textSecondary">Avg concentric</StatLabel>
          <StatNumber fontSize="lg" color="paper.textPrimary">{avgConcentricForceN.toFixed(0)} N</StatNumber>
        </Stat>
        <Stat>
          <StatLabel fontSize="xs" color="paper.textSecondary">Avg eccentric</StatLabel>
          <StatNumber fontSize="lg" color="paper.textPrimary">{avgEccentricForceN.toFixed(0)} N</StatNumber>
        </Stat>
      </SimpleGrid>
    </VStack>
  )
}

export default ConcentricEccentricPanel
