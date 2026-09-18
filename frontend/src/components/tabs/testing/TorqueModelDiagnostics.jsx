import {
  Box, VStack, HStack, Text, Badge, Button, Collapse, useDisclosure, Divider,
} from '@chakra-ui/react'
import { ChevronDownIcon, ChevronRightIcon } from '@chakra-ui/icons'

const fmt = (v, digits = 6) => (v == null ? '—' : Number(v).toFixed(digits))

const DIRECTION_LABEL = { up: 'up (lifting / concentric)', down: 'down (lowering / eccentric)' }

const DirectionBlock = ({ direction, entry }) => {
  const pointCount = entry?.points?.length ?? 0
  return (
    <Box>
      <HStack mb={1}>
        <Text color="paper.textSecondary">{DIRECTION_LABEL[direction]}:</Text>
        <Badge colorScheme={pointCount > 0 ? 'green' : 'gray'}>
          {pointCount > 0 ? `fitted from ${pointCount} point${pointCount === 1 ? '' : 's'}` : 'identity (uncalibrated)'}
        </Badge>
      </HStack>
      <Text color="paper.textPrimary" pl={2} mb={1}>{entry?.equation}</Text>
      {pointCount > 0 && (
        <VStack align="stretch" spacing={0.5} pl={2}>
          <HStack color="paper.textSecondary" fontSize="10px">
            <Text w="80px">weight (kg)</Text>
            <Text w="100px">raw torque (Nm)</Text>
            <Text w="90px">r_eff (m)</Text>
            <Text w="100px">expected (Nm)</Text>
          </HStack>
          {entry.points.map((p, i) => (
            <HStack key={i} color="paper.textPrimary">
              <Text w="80px">{fmt(p.known_weight_kg, 3)}</Text>
              <Text w="100px">{fmt(p.raw_torque_nm, 5)}</Text>
              <Text w="90px">{fmt(p.r_eff_m, 5)}</Text>
              <Text w="100px">{fmt(p.expected_torque_nm, 5)}</Text>
            </HStack>
          ))}
        </VStack>
      )}
    </Box>
  )
}

// Developer Visibility (items 6/7) -- same collapsed-by-default "Developer
// diagnostics" convention as SpoolModelDiagnostics.jsx: this is for the
// developer/engineer building the machine, not an end user, so it shows the
// exact fitted equations (numbers substituted in) for BOTH directions, every
// recorded calibration point (tagged by direction), and a plain-text walk
// through how the software gets from a raw current reading to an equivalent
// lifted mass -- nothing about the calibration is meant to be a black box.
const TorqueModelDiagnostics = ({ cable }) => {
  const { isOpen, onToggle } = useDisclosure({ defaultIsOpen: false })
  const torqueModel = cable?.torque_model
  const directions = torqueModel?.directions
  const totalPoints = torqueModel?.points?.length ?? 0

  return (
    <Box borderTop="1px solid" borderColor="paper.border" pt={3}>
      <Button variant="ghost" size="sm" leftIcon={isOpen ? <ChevronDownIcon /> : <ChevronRightIcon />} onClick={onToggle} color="accent.600">
        {isOpen ? 'Hide' : 'Show'} Developer diagnostics (torque/force calibration)
      </Button>
      <Collapse in={isOpen} animateOpacity>
        <VStack align="stretch" spacing={3} mt={2} fontSize="xs" fontFamily="mono">
          {!torqueModel && <Text color="paper.textSecondary">No status yet.</Text>}
          {torqueModel && (
            <>
              <HStack>
                <Text color="paper.textSecondary">recorded points:</Text>
                <Badge colorScheme={totalPoints > 0 ? 'green' : 'gray'}>{totalPoints} total</Badge>
              </HStack>

              <Box>
                <Text color="paper.textSecondary" mb={1}>how this is used, end to end:</Text>
                <Text color="paper.textPrimary" pl={2}>1. hardware reads phase current (current_iq, A) -- signed, direction encodes which way the motor is turning/pushing</Text>
                <Text color="paper.textPrimary" pl={2}>2. raw_torque_nm = motor_torque_constant_nm_per_a × current_iq (fixed board estimate, signed)</Text>
                <Text color="paper.textPrimary" pl={2}>3. the cable&apos;s live velocity picks which fitted line applies -- up (lifting), down (lowering), or the static blend near zero velocity</Text>
                <Text color="paper.textPrimary" pl={2}>4. corrected_torque_nm = sign(raw_torque_nm) × (scale × |raw_torque_nm| + offset) for that line (magnitude only, sign passes through untouched)</Text>
                <Text color="paper.textPrimary" pl={2}>5. force_n = corrected_torque_nm ÷ r_eff (effective spool radius at the current position)</Text>
                <Text color="paper.textPrimary" pl={2}>6. equivalent lifted mass_kg = |force_n| ÷ 9.81</Text>
              </Box>
              <Text color="paper.textSecondary" fontStyle="italic">
                Note: friction opposes whichever way the motor is turning, so a single static hold can&apos;t
                represent both lifting and lowering -- points are recorded separately per direction from the
                steady-state (constant-velocity) portion of real reps, not a static hold. Near-zero velocity (e.g.
                an isometric hold) uses the average of both directions&apos; scale with no friction offset applied,
                since Coulomb friction&apos;s direction is indeterminate exactly at zero velocity.
              </Text>

              {directions && (
                <>
                  <Divider borderColor="paper.border" />
                  <DirectionBlock direction="up" entry={directions.up} />
                  <Divider borderColor="paper.border" />
                  <DirectionBlock direction="down" entry={directions.down} />
                </>
              )}

              <Divider borderColor="paper.border" />

              <VStack align="stretch" spacing={0.5}>
                <HStack justify="space-between">
                  <Text color="paper.textSecondary">static blend scale (near-zero velocity)</Text>
                  <Text color="paper.textPrimary">{fmt(torqueModel.static_blend?.scale)}</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text color="paper.textSecondary">deadband</Text>
                  <Text color="paper.textPrimary">{fmt(torqueModel.static_blend?.deadband_turns_s, 3)} turns/s</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text color="paper.textSecondary">motor_torque_constant (board default)</Text>
                  <Text color="paper.textPrimary">{fmt(torqueModel.motor_torque_constant_nm_per_a, 5)} Nm/A</Text>
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
