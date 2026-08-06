import {
  Box, VStack, HStack, Text, Badge, Button, Collapse, useDisclosure, Divider,
} from '@chakra-ui/react'
import { ChevronDownIcon, ChevronRightIcon } from '@chakra-ui/icons'

const fmt = (v, digits = 6) => (v == null ? '—' : Number(v).toFixed(digits))

// Developer Visibility (items 6/7) -- same collapsed-by-default "Developer
// diagnostics" convention as SpoolModelDiagnostics.jsx: this is for the
// developer/engineer building the machine, not an end user, so it shows the
// exact fitted equation (numbers substituted in), every recorded
// calibration point, and a plain-text walk through how the software gets
// from a raw current reading to an equivalent lifted mass -- nothing about
// the calibration is meant to be a black box.
const TorqueModelDiagnostics = ({ cable }) => {
  const { isOpen, onToggle } = useDisclosure({ defaultIsOpen: false })
  const torqueModel = cable?.torque_model
  const isCalibrated = (torqueModel?.points?.length ?? 0) > 0

  return (
    <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
      <Button variant="ghost" size="sm" leftIcon={isOpen ? <ChevronDownIcon /> : <ChevronRightIcon />} onClick={onToggle} color="odrive.300">
        {isOpen ? 'Hide' : 'Show'} Developer diagnostics (torque/force calibration)
      </Button>
      <Collapse in={isOpen} animateOpacity>
        <VStack align="stretch" spacing={3} mt={2} fontSize="xs" fontFamily="mono">
          {!torqueModel && <Text color="gray.500">No status yet.</Text>}
          {torqueModel && (
            <>
              <HStack>
                <Text color="gray.400">active model:</Text>
                <Badge colorScheme={isCalibrated ? 'green' : 'gray'}>
                  {isCalibrated ? `fitted from ${torqueModel.points.length} point${torqueModel.points.length === 1 ? '' : 's'}` : 'identity (uncalibrated)'}
                </Badge>
              </HStack>

              <Box>
                <Text color="gray.400" mb={1}>equation:</Text>
                <Text color="gray.200">{torqueModel.equation}</Text>
              </Box>

              <Box>
                <Text color="gray.400" mb={1}>how this is used, end to end:</Text>
                <Text color="gray.300" pl={2}>1. hardware reads phase current (current_iq, A) -- signed, direction encodes which way the motor is turning/pushing</Text>
                <Text color="gray.300" pl={2}>2. raw_torque_nm = motor_torque_constant_nm_per_a × current_iq (fixed board estimate, signed)</Text>
                <Text color="gray.300" pl={2}>3. corrected_torque_nm = sign(raw_torque_nm) × (scale × |raw_torque_nm| + offset) (this calibration corrects magnitude only, sign passes through untouched)</Text>
                <Text color="gray.300" pl={2}>4. force_n = corrected_torque_nm ÷ r_eff (effective spool radius at the current position)</Text>
                <Text color="gray.300" pl={2}>5. equivalent lifted mass_kg = |force_n| ÷ 9.81</Text>
              </Box>
              <Text color="gray.500" fontStyle="italic">
                Note: scale/offset are fit against |raw_torque_nm| (magnitude), not the signed value -- a known
                weight is never negative, but the raw current reading's sign is meaningful (direction) and would
                otherwise get baked into the fit itself. Sign is reapplied unchanged after correction, so it stays
                available wherever it matters for control/debugging.
              </Text>

              {torqueModel.points?.length > 0 && (
                <Box>
                  <Text color="gray.400" mb={1}>recorded calibration points:</Text>
                  <VStack align="stretch" spacing={0.5}>
                    <HStack color="gray.500" fontSize="10px">
                      <Text w="80px">weight (kg)</Text>
                      <Text w="100px">raw torque (Nm)</Text>
                      <Text w="90px">r_eff (m)</Text>
                      <Text w="100px">expected (Nm)</Text>
                    </HStack>
                    {torqueModel.points.map((p, i) => (
                      <HStack key={i} color="gray.300">
                        <Text w="80px">{fmt(p.known_weight_kg, 3)}</Text>
                        <Text w="100px">{fmt(p.raw_torque_nm, 5)}</Text>
                        <Text w="90px">{fmt(p.r_eff_m, 5)}</Text>
                        <Text w="100px">{fmt(p.expected_torque_nm, 5)}</Text>
                      </HStack>
                    ))}
                  </VStack>
                </Box>
              )}

              <Divider borderColor="gray.700" />

              <VStack align="stretch" spacing={0.5}>
                <HStack justify="space-between"><Text color="gray.400">scale</Text><Text color="gray.200">{fmt(torqueModel.scale)}</Text></HStack>
                <HStack justify="space-between"><Text color="gray.400">offset</Text><Text color="gray.200">{fmt(torqueModel.offset)} Nm</Text></HStack>
                <HStack justify="space-between">
                  <Text color="gray.400">motor_torque_constant (board default)</Text>
                  <Text color="gray.200">{fmt(torqueModel.motor_torque_constant_nm_per_a, 5)} Nm/A</Text>
                </HStack>
              </VStack>
            </>
          )}
        </VStack>
      </Collapse>
    </Box>
  )
}

export default TorqueModelDiagnostics
