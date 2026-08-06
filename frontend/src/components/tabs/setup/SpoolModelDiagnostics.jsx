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
    <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
      <Button variant="ghost" size="sm" leftIcon={isOpen ? <ChevronDownIcon /> : <ChevronRightIcon />} onClick={onToggle} color="odrive.300">
        {isOpen ? 'Hide' : 'Show'} Developer diagnostics
      </Button>
      <Collapse in={isOpen} animateOpacity>
        <VStack align="stretch" spacing={3} mt={2} fontSize="xs" fontFamily="mono">
          {!spoolModel && <Text color="gray.500">No status yet.</Text>}
          {spoolModel && (
            <>
              <HStack>
                <Text color="gray.400">active model:</Text>
                <Badge colorScheme={spoolModel.type === 'piecewise' ? 'green' : 'gray'}>
                  {MODEL_LABEL[spoolModel.type] ?? spoolModel.type}
                </Badge>
              </HStack>

              <Box>
                <Text color="gray.400" mb={1}>equations:</Text>
                <Text color="gray.200">{spoolModel.equations?.model}</Text>
                <Text color="gray.200">{spoolModel.equations?.length_equation}</Text>
                {spoolModel.equations?.segments?.map((line, i) => (
                  <Text key={i} color="gray.300" pl={2}>{line}</Text>
                ))}
              </Box>

              {spoolModel.type === 'piecewise' && spoolModel.segments?.length > 0 && (
                <Box>
                  <Text color="gray.400" mb={1}>segments:</Text>
                  <VStack align="stretch" spacing={0.5}>
                    <HStack color="gray.500" fontSize="10px">
                      <Text w="90px">θ start (turns)</Text>
                      <Text w="90px">θ end (turns)</Text>
                      <Text w="90px">r start (m)</Text>
                      <Text w="90px">r end (m)</Text>
                      <Text>slope (m/rad)</Text>
                    </HStack>
                    {spoolModel.segments.map((seg, i) => (
                      <HStack key={i} color="gray.300">
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

              <Divider borderColor="gray.700" />

              <VStack align="stretch" spacing={0.5}>
                <HStack justify="space-between"><Text color="gray.400">r0</Text><Text color="gray.200">{fmt(spoolModel.r0)} m</Text></HStack>
                <HStack justify="space-between"><Text color="gray.400">k</Text><Text color="gray.200">{fmt(spoolModel.k)} m/rad</Text></HStack>
                <HStack justify="space-between">
                  <Text color="gray.400">k bounds (fat-finger guard)</Text>
                  <Text color="gray.200">[{fmt(spoolModel.k_bounds?.[0])}, {fmt(spoolModel.k_bounds?.[1])}]</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text color="gray.400">min effective radius floor</Text>
                  <Text color="gray.200">{fmt(spoolModel.min_effective_radius_m, 4)} m</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text color="gray.400">r_eff at current position</Text>
                  <Text color="gray.200">{fmt(spoolModel.r_eff_at_current_position_m, 5)} m</Text>
                </HStack>
                <HStack justify="space-between"><Text color="gray.400">cable position</Text><Text color="gray.200">{fmt(cable?.cable_position_turns, 4)} turns</Text></HStack>
                <HStack justify="space-between"><Text color="gray.400">home_turns (raw encoder)</Text><Text color="gray.200">{fmt(cable?.home_turns, 4)}</Text></HStack>
                <HStack justify="space-between"><Text color="gray.400">max_turns (raw encoder)</Text><Text color="gray.200">{fmt(cable?.max_turns, 4)}</Text></HStack>
                <HStack justify="space-between"><Text color="gray.400">max extension length</Text><Text color="gray.200">{fmt(cable?.max_extension_length_m, 4)} m</Text></HStack>
              </VStack>
            </>
          )}
        </VStack>
      </Collapse>
    </Box>
  )
}

export default SpoolModelDiagnostics
