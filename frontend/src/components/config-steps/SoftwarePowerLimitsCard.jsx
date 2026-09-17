import { useEffect, useState } from 'react'
import {
  Box,
  Card,
  CardBody,
  Heading,
  HStack,
  VStack,
  Text,
  Tooltip,
  Icon,
  IconButton,
  Alert,
  AlertIcon,
  AlertDescription,
} from '@chakra-ui/react'
import { InfoOutlineIcon, CheckIcon } from '@chakra-ui/icons'
import ParameterInput from '../config-parameter-fields/ParameterInput'
import { getExerciseStatus, updatePowerLimits } from '../../api/exercise'

// Row layout deliberately mirrors ParameterField.jsx (label + tooltip left,
// ParameterInput right) so these two fields read as part of the same
// Configuration tab even though they're wired to a completely different
// backend: FORCE_MAX_N/REGEN_POWER_BUDGET_W aren't ODrive device registers
// (nothing here goes through wizard.setValue/backend.readProperties), they're
// this project's own app-level safety ceilings (config/board_constants.py,
// live-adjustable via CableState.set_power_limits() since 18 Aug 2026 -- see
// core/cable/state.py's module docstring for why these two constants get
// live-editing when MOTOR_CURRENT_LIM/DC-bus regen limits deliberately don't).
// Saved independently of the wizard's Apply & Save -- there's no pending-
// change diff to review, a Save here takes effect immediately.
const Row = ({ label, path, tooltip, unit, value, onChange }) => (
  <HStack justify="space-between" align="center" spacing={3} py={1}>
    <VStack align="start" spacing={0} flex="1" minW={0}>
      <HStack spacing={1}>
        <Text fontSize="sm" noOfLines={1}>{label}</Text>
        {tooltip && (
          <Tooltip label={tooltip} hasArrow placement="top" bg="gray.700" color="white" maxW="360px">
            <Icon as={InfoOutlineIcon} color="gray.500" boxSize={3} />
          </Tooltip>
        )}
      </HStack>
      <Text fontSize="0.65rem" color="gray.500" fontFamily="mono" noOfLines={1}>{path}</Text>
    </VStack>
    <Box>
      <ParameterInput value={value} onChange={onChange} unit={unit} step={1} decimals={1} min={0} />
    </Box>
  </HStack>
)

const SoftwarePowerLimitsCard = () => {
  const [forceMaxN, setForceMaxN] = useState(undefined)
  const [regenBudgetW, setRegenBudgetW] = useState(undefined)
  const [savedForceMaxN, setSavedForceMaxN] = useState(undefined)
  const [savedRegenBudgetW, setSavedRegenBudgetW] = useState(undefined)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const refresh = async () => {
    try {
      const status = await getExerciseStatus()
      const cable = status?.cable
      if (cable?.force_max_n != null) {
        setForceMaxN(cable.force_max_n)
        setSavedForceMaxN(cable.force_max_n)
      }
      if (cable?.regen_power_budget_w != null) {
        setRegenBudgetW(cable.regen_power_budget_w)
        setSavedRegenBudgetW(cable.regen_power_budget_w)
      }
    } catch {
      // Exercise backend not reachable yet -- fields just show "unknown"
      // (ParameterInput's placeholder) until the next successful refresh.
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const dirty = forceMaxN !== savedForceMaxN || regenBudgetW !== savedRegenBudgetW

  const handleSave = async () => {
    setError(null)
    setBusy(true)
    try {
      await updatePowerLimits({ forceMaxN, regenPowerBudgetW: regenBudgetW })
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card bg="gray.800" variant="outline" borderColor="gray.700" mt={4}>
      <CardBody>
        <HStack justify="space-between" align="start" mb={3}>
          <VStack align="start" spacing={0}>
            <Heading size="sm" color="odrive.300">Software Power Limits</Heading>
            <Text fontSize="xs" color="gray.500">
              App-level safety ceilings, not ODrive device registers -- saves immediately, independent of
              Apply &amp; Save above.
            </Text>
          </VStack>
          <Tooltip label="Save changes">
            <IconButton
              aria-label="Save power limits"
              size="sm"
              icon={<CheckIcon />}
              onClick={handleSave}
              isLoading={busy}
              isDisabled={!dirty}
              colorScheme="odrive"
            />
          </Tooltip>
        </HStack>

        {error && (
          <Alert status="error" variant="left-accent" mb={3}>
            <AlertIcon /><AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <VStack align="stretch" spacing={1}>
          <Row
            label="Max Cable Force"
            path="force_max_n"
            unit="N"
            value={forceMaxN}
            onChange={setForceMaxN}
            tooltip="Hard ceiling on commanded cable force (Exercise Force Feedback and Train resistance profiles both clamp to this). Bounded above by this board's structural force ceiling: MOTOR_CURRENT_LIM * MOTOR_TORQUE_CONSTANT / SPOOL_RADIUS_M."
          />
          <Row
            label="Regen Power Budget"
            path="regen_power_budget_w"
            unit="W"
            value={regenBudgetW}
            onChange={setRegenBudgetW}
            tooltip="Estimated regen power (post-copper-loss) allowed to reach the brake resistor/bus before the software power limiter engages during Force Feedback resistance states. No computed hardware ceiling -- set conservatively relative to the brake resistor's rated dissipation."
          />
        </VStack>
      </CardBody>
    </Card>
  )
}

export default SoftwarePowerLimitsCard
