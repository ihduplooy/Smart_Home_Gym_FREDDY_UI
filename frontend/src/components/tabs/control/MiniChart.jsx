import { memo } from 'react'
import { Box, HStack, Text } from '@chakra-ui/react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts'

// Same visual language as the Inspector's LiveCharts (dark card, colored
// line, seconds on X) — the declared Session 1 -> 2 chart-reuse touchpoint.
// Extracted out of ControlTab so the Profiles tab (Session 3) can reuse it
// verbatim instead of duplicating ~50 lines of recharts config.
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

export default MiniChart
