import {
  Box, VStack, HStack, Text, Badge, Button, Collapse, useDisclosure, Divider,
} from '@chakra-ui/react'
import { ChevronDownIcon, ChevronRightIcon } from '@chakra-ui/icons'

const MODEL_LABEL = {
  piecewise: 'piecewise (experimental growth model)',
  linear: 'linear (r0 + k·θ)',
  fixed_radius: 'fixed radius (k = 0)',
}

const fmt = (v, digits = 6) => (v == null ? '—' : Number(v).toFixed(digits))

// Developer Visibility (train tab calibration overhaul item 6): this
// interface is for the developer building the machine, not an end user --
// rather than hiding how the calibration works, show the exact equation
// currently in effect (numbers substituted in, not symbolic), every
// intermediate value that feeds it, and the underlying segment table when
// the experimental piecewise model is active, so another engineer can
// verify/troubleshoot it without reading source. Collapsed by default to
// stay out of the way of the primary calibration flow above.
const SpoolModelDiagnostics = ({ status }) => {
  const { isOpen, onToggle } = useDisclosure({ defaultIsOpen: false })
  const cable = status?.cable
  const spoolModel = cable?.spool_model

  return (
    <Box borderTop="1px solid" borderColor="paper.border" pt={3}>
      <Button variant="ghost" size="sm" borderRadius="full" leftIcon={isOpen ? <ChevronDownIcon /> : <ChevronRightIcon />} onClick={onToggle} color="accent.600">
        {isOpen ? 'Hide' : 'Show'} Developer diagnostics
      </Button>
      <Collapse in={isOpen} animateOpacity>
        <VStack align="stretch" spacing={3} mt={2} fontSize="xs" fontFamily="mono">
          {!spoolModel && <Text color="paper.textSecondary">No status yet.</Text>}
          {spoolModel && (
            <>
              <HStack>
                <Text color="paper.textSecondary">active model:</Text>
                <Badge colorScheme={spoolModel.type === 'piecewise' ? 'green' : 'gray'} borderRadius="full">
                  {MODEL_LABEL[spoolModel.type] ?? spoolModel.type}
                </Badge>
              </HStack>

              <Box>
                <Text color="paper.textSecondary" mb={1}>equations:</Text>
                <Text color="paper.textPrimary">{spoolModel.equations?.model}</Text>
                <Text color="paper.textPrimary">{spoolModel.equations?.length_equation}</Text>
                {spoolModel.equations?.segments?.map((line, i) => (
                  <Text key={i} color="paper.textPrimary" pl={2}>{line}</Text>
                ))}
              </Box>

              {spoolModel.type === 'piecewise' && spoolModel.segments?.length > 0 && (
                <Box>
                  <Text color="paper.textSecondary" mb={1}>segments:</Text>
                  <VStack align="stretch" spacing={0.5}>
                    <HStack color="paper.textSecondary" fontSize="10px">
                      <Text w="90px">θ start (turns)</Text>
                      <Text w="90px">θ end (turns)</Text>
                      <Text w="90px">r start (m)</Text>
                      <Text w="90px">r end (m)</Text>
                      <Text>slope (m/rad)</Text>
                    </HStack>
                    {spoolModel.segments.map((seg, i) => (
                      <HStack key={i} color="paper.textPrimary">
                        <Text w="90px">{fmt(seg.theta_start_turns, 3)}</Text>
                        <Text w="90px">{seg.theta_end_turns == null ? '∞' : fmt(seg.theta_end_turns, 3)}</Text>
                        <Text w="90px">{fmt(seg.r_start_m, 5)}</Text>
                        <Text w="90px">{seg.r_end_m == null ? '—' : fmt(seg.r_end_m, 5)}</Text>
                        <Text>{fmt(seg.slope_m_per_rad, 6)}</Text>
                      </HStack>
                    ))}
                  </VStack>
                </Box>
              )}

              <Divider borderColor="paper.border" />

              <VStack align="stretch" spacing={0.5}>
                <HStack justify="space-between"><Text color="paper.textSecondary">r0</Text><Text color="paper.textPrimary">{fmt(spoolModel.r0)} m</Text></HStack>
                <HStack justify="space-between"><Text color="paper.textSecondary">k</Text><Text color="paper.textPrimary">{fmt(spoolModel.k)} m/rad</Text></HStack>
                <HStack justify="space-between">
                  <Text color="paper.textSecondary">k bounds (fat-finger guard)</Text>
                  <Text color="paper.textPrimary">[{fmt(spoolModel.k_bounds?.[0])}, {fmt(spoolModel.k_bounds?.[1])}]</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text color="paper.textSecondary">min effective radius floor</Text>
                  <Text color="paper.textPrimary">{fmt(spoolModel.min_effective_radius_m, 4)} m</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text color="paper.textSecondary">r_eff at current position</Text>
                  <Text color="paper.textPrimary">{fmt(spoolModel.r_eff_at_current_position_m, 5)} m</Text>
                </HStack>
                <HStack justify="space-between"><Text color="paper.textSecondary">cable position</Text><Text color="paper.textPrimary">{fmt(cable?.cable_position_turns, 4)} turns</Text></HStack>
                <HStack justify="space-between"><Text color="paper.textSecondary">home_turns (raw encoder)</Text><Text color="paper.textPrimary">{fmt(cable?.home_turns, 4)}</Text></HStack>
                <HStack justify="space-between"><Text color="paper.textSecondary">max_turns (raw encoder)</Text><Text color="paper.textPrimary">{fmt(cable?.max_turns, 4)}</Text></HStack>
                <HStack justify="space-between"><Text color="paper.textSecondary">max extension length</Text><Text color="paper.textPrimary">{fmt(cable?.max_extension_length_m, 4)} m</Text></HStack>
              </VStack>
            </>
          )}
        </VStack>
      </Collapse>
    </Box>
  )
}

export default SpoolModelDiagnostics
