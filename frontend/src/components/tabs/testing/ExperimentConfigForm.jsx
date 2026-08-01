import { useEffect, useState } from 'react'
import {
  VStack, HStack, FormControl, FormLabel, NumberInput, NumberInputField,
  Input, Button, SimpleGrid, Text,
} from '@chakra-ui/react'

// Schema-driven numeric fields (everything from the experiment's describe()
// except initial_position_m, which is handled separately below since it's a
// read-only live reading, never hand-typed -- Testing tab Build Spec §4.3).
//
// `value`/`onChange` deal in the raw typed STRING, not a parsed Number --
// Chakra's NumberInput is controlled by `value`, so if the parent stored a
// Number and re-rendered on every keystroke, typing "1." immediately
// collapsed back to "1" (Number("1.") === 1), making it impossible to ever
// type a decimal point. Keeping the string as-is until submit (see
// ExperimentConfigForm's handleConfigure) fixes that.
const ConfigNumberField = ({ fieldKey, schema, value, onChange }) => (
  <FormControl>
    <FormLabel color="gray.300" fontSize="xs">{schema?.label ?? fieldKey}</FormLabel>
    <NumberInput
      size="sm"
      value={value}
      min={schema?.min ?? undefined}
      max={schema?.max ?? undefined}
      onChange={(valueString) => onChange(valueString)}
    >
      <NumberInputField bg="gray.900" color="white" />
    </NumberInput>
  </FormControl>
)

const CONFIG_FIELD_ORDER = [
  'known_weight_kg',
  'target_position_m',
  'initial_torque_nm',
  'torque_ramp_rate_nm_per_s',
  'movement_threshold_m_per_s',
  'hold_deadband_m',
  'hold_gain',
  'max_torque_nm',
  'max_duration_s',
]

/**
 * `experimentSchema`: one entry from GET /api/experiments (name/label/parameters).
 * `currentPositionM`: live cable position (m, from home) for the read-only
 * initial_position_m field -- refreshed on demand, never free-typed.
 * `onConfigure(config)`: fires with the full 10-field config dict.
 */
const ExperimentConfigForm = ({ experimentSchema, currentPositionM, onRefreshPosition, onConfigure, disabled, busy }) => {
  const [values, setValues] = useState({})

  useEffect(() => {
    if (!experimentSchema) return
    const defaults = {}
    for (const key of CONFIG_FIELD_ORDER) {
      defaults[key] = String(experimentSchema.parameters?.[key]?.default ?? 0)
    }
    setValues(defaults)
  }, [experimentSchema])

  const setField = (key, val) => setValues((prev) => ({ ...prev, [key]: val }))

  const handleConfigure = () => {
    const numeric = {}
    for (const key of CONFIG_FIELD_ORDER) {
      const n = Number(values[key])
      numeric[key] = Number.isNaN(n) ? 0 : n
    }
    onConfigure({ ...numeric, initial_position_m: currentPositionM ?? 0 })
  }

  if (!experimentSchema) return null

  return (
    <VStack align="stretch" spacing={4}>
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs">Initial position (m, from home)</FormLabel>
        <HStack>
          <Input size="sm" isReadOnly value={currentPositionM != null ? currentPositionM.toFixed(4) : '—'} bg="gray.900" color="gray.400" />
          <Button size="sm" variant="outline" onClick={onRefreshPosition} isDisabled={disabled}>Refresh</Button>
        </HStack>
        <Text fontSize="xs" color="gray.500" mt={1}>Read from the live position -- never hand-typed.</Text>
      </FormControl>

      <SimpleGrid columns={{ base: 1, md: 3 }} spacing={3}>
        {CONFIG_FIELD_ORDER.map((key) => (
          <ConfigNumberField
            key={key}
            fieldKey={key}
            schema={experimentSchema.parameters?.[key]}
            value={values[key] ?? '0'}
            onChange={(v) => setField(key, v)}
          />
        ))}
      </SimpleGrid>

      <Button colorScheme="blue" onClick={handleConfigure} isDisabled={disabled || busy}>
        Configure
      </Button>
    </VStack>
  )
}

export default ExperimentConfigForm
