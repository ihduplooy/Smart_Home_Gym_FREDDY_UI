import { useState } from 'react'
import {
  Box, HStack, VStack, Text, Heading, Card, CardBody, SimpleGrid, Stat, StatLabel, StatNumber,
  CircularProgress, CircularProgressLabel, Button, Collapse, Input, InputGroup, InputLeftAddon,
} from '@chakra-ui/react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts'

// Shared across all three GYM modes (Constant/Band/Concentric-Eccentric) --
// Set Progress and Session Summary read the same underlying session state
// (rep count, tempo, work -- useGymRepTracking's repHistory/sessionSummary)
// regardless of which resistance mode produced it, so this is implemented
// once here rather than duplicated per-panel. Ghost Trace (force-vs-cable-
// position, this rep vs previous reps) sits behind a collapsed "view detail"
// toggle -- opt-in, not the default view, since it's the same shape as the
// force-vs-position chart GYM is deliberately moving away from as a default.

const formatTempo = (s) => (s > 0 ? `${s.toFixed(1)} s` : '—')

const GymFooter = ({ repHistory, currentRepPeaks, sessionSummary, targetReps, onTargetRepsChange }) => {
  const [showGhostTrace, setShowGhostTrace] = useState(false)

  const progressPct = targetReps > 0 ? Math.min(100, (sessionSummary.totalReps / targetReps) * 100) : 0

  // Ghost trace: previous reps faded, current (in-progress) rep highlighted --
  // each rep's own point trail, merged onto one x (cable position) axis via
  // recharts' per-Line `data` override rather than one shared dataset (reps
  // don't share x-sample alignment with each other).
  const previousReps = repHistory.slice(-5)

  return (
    <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4}>
      <Card bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
        <CardBody>
          <VStack spacing={3}>
            <Heading size="sm" color="paper.textPrimary" alignSelf="flex-start">Set Progress</Heading>
            <CircularProgress value={progressPct} color="accent.600" size="110px" thickness="10px">
              <CircularProgressLabel fontSize="lg" fontFamily="mono" color="paper.textPrimary">
                {sessionSummary.totalReps}/{targetReps}
              </CircularProgressLabel>
            </CircularProgress>
            <HStack>
              <Text fontSize="xs" color="paper.textSecondary">Target reps</Text>
              <InputGroup size="xs" w="90px">
                <Input
                  type="text"
                  inputMode="numeric"
                  fontFamily="mono"
                  value={targetReps}
                  onChange={(e) => onTargetRepsChange(e.target.value)}
                />
              </InputGroup>
            </HStack>
          </VStack>
        </CardBody>
      </Card>

      <Card bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
        <CardBody>
          <VStack align="stretch" spacing={3}>
            <HStack justify="space-between">
              <Heading size="sm" color="paper.textPrimary">Ghost Trace</Heading>
              <Button
                size="xs"
                variant="ghost"
                rightIcon={showGhostTrace ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                onClick={() => setShowGhostTrace((v) => !v)}
              >
                {showGhostTrace ? 'Hide detail' : 'View detail'}
              </Button>
            </HStack>
            <Collapse in={showGhostTrace}>
              <Box h="180px" bg="paper.bg" borderRadius="md" p={2}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E4E4E7" />
                    <XAxis
                      dataKey="position_m"
                      type="number"
                      stroke="#71717A"
                      tick={{ fill: '#71717A', fontSize: 10 }}
                      tickFormatter={(v) => v.toFixed(2)}
                    />
                    <YAxis stroke="#71717A" tick={{ fill: '#71717A', fontSize: 10 }} domain={[0, 'auto']} width={40} />
                    <RechartsTooltip
                      contentStyle={{ backgroundColor: '#FFFFFF', border: '1px solid #E4E4E7', borderRadius: '6px', color: '#18181B', fontSize: '11px' }}
                      formatter={(v) => [`${Number(v).toFixed(2)} N`, 'force']}
                    />
                    {previousReps.map((rep) => (
                      <Line
                        key={rep.rep}
                        data={rep.points}
                        dataKey="force_n"
                        stroke="#A1A1AA"
                        strokeWidth={1}
                        opacity={0.5}
                        dot={false}
                        isAnimationActive={false}
                        legendType="none"
                      />
                    ))}
                    <Line
                      data={currentRepPeaks.points}
                      dataKey="force_n"
                      stroke="#eda100"
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Box>
            </Collapse>
            {!showGhostTrace && (
              <Text fontSize="xs" color="paper.textSecondary">
                Force vs. cable position, this rep against the last {Math.min(5, repHistory.length)} previous reps.
              </Text>
            )}
          </VStack>
        </CardBody>
      </Card>

      <Card bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
        <CardBody>
          <VStack align="stretch" spacing={3}>
            <Heading size="sm" color="paper.textPrimary">Session Summary</Heading>
            <SimpleGrid columns={2} spacing={3}>
              <Stat>
                <StatLabel fontSize="xs" color="paper.textSecondary">Total reps</StatLabel>
                <StatNumber fontSize="lg" color="paper.textPrimary">{sessionSummary.totalReps}</StatNumber>
              </Stat>
              <Stat>
                <StatLabel fontSize="xs" color="paper.textSecondary">Total work</StatLabel>
                <StatNumber fontSize="lg" color="paper.textPrimary">{sessionSummary.totalWorkJ.toFixed(0)} J</StatNumber>
              </Stat>
              <Stat>
                <StatLabel fontSize="xs" color="paper.textSecondary">Avg tempo</StatLabel>
                <StatNumber fontSize="lg" color="paper.textPrimary">{formatTempo(sessionSummary.avgTempoS)}</StatNumber>
              </Stat>
              <Stat>
                <StatLabel fontSize="xs" color="paper.textSecondary">Peak force</StatLabel>
                <StatNumber fontSize="lg" color="paper.textPrimary">{sessionSummary.peakForceN.toFixed(0)} N</StatNumber>
              </Stat>
            </SimpleGrid>
          </VStack>
        </CardBody>
      </Card>
    </SimpleGrid>
  )
}

export default GymFooter
