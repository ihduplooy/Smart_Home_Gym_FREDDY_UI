import { useMemo } from 'react'
import {
  Box,
  HStack,
  VStack,
  Text,
  Badge,
  Tooltip,
  Icon,
} from '@chakra-ui/react'
import { InfoOutlineIcon } from '@chakra-ui/icons'
import ParameterInput from './ParameterInput'
import ParameterSelect from './ParameterSelect'
import ParameterSwitch from './ParameterSwitch'
import { getParamMeta } from '../../utils/odriveRegistry'
import { enumSelectOptions } from '../../utils/configEnums'
import { resolvePath } from '../../utils/configSchema'

/**
 * Render one schema field: label + tooltip + the appropriate control, plus
 * "edited" / "unknown" badges. Determines the control kind from the field
 * (explicit `kind`) or the data-driven registry metadata.
 */
const ParameterField = ({ field, fwLine, value, known, edited, onChange, onRefresh, isLoading }) => {
  const path = resolvePath(field.path, fwLine)
  const meta = useMemo(() => getParamMeta(fwLine, path), [fwLine, path])
  const kind = field.kind || meta?.kind || 'float'

  const options = useMemo(() => {
    if (kind !== 'enum') return []
    return enumSelectOptions(fwLine, field.enumName, meta)
  }, [kind, fwLine, field.enumName, meta])

  // For enum fields, the tooltip lists what each option actually does — "how
  // input commands are shaped" doesn't tell you which of nine modes to pick.
  const tooltipContent =
    kind === 'enum' && options.some((o) => o.description) ? (
      <VStack align="start" spacing={1} py={1}>
        {field.tooltip && <Text>{field.tooltip}</Text>}
        {options.map((o) => (
          <Text key={o.value}>
            <Text as="span" fontWeight="bold">{o.label}:</Text> {o.description || '—'}
          </Text>
        ))}
      </VStack>
    ) : (
      field.tooltip
    )

  let control
  if (kind === 'boolean') {
    control = (
      <ParameterSwitch value={value} onChange={onChange} onRefresh={onRefresh} isLoading={isLoading} />
    )
  } else if (kind === 'enum') {
    control = (
      <ParameterSelect value={value} onChange={onChange} onRefresh={onRefresh} isLoading={isLoading} options={options} />
    )
  } else {
    control = (
      <ParameterInput
        value={value}
        onChange={onChange}
        onRefresh={onRefresh}
        isLoading={isLoading}
        unit={field.unit}
        step={field.step}
        decimals={kind === 'integer' ? 0 : field.decimals}
        min={field.min}
        max={field.max}
        isInteger={kind === 'integer'}
        allowInfinity={field.allowInfinity}
      />
    )
  }

  return (
    <HStack justify="space-between" align="center" spacing={3} py={1}>
      <VStack align="start" spacing={0} flex="1" minW={0}>
        <HStack spacing={1}>
          <Text fontSize="sm" noOfLines={1}>{field.label}</Text>
          {field.tooltip && (
            <Tooltip label={tooltipContent} hasArrow placement="top" bg="gray.700" color="white" maxW="360px">
              <Icon as={InfoOutlineIcon} color="gray.500" boxSize={3} />
            </Tooltip>
          )}
          {edited && <Badge colorScheme="teal" fontSize="0.55rem">edited</Badge>}
          {!known && !edited && <Badge colorScheme="yellow" fontSize="0.55rem">unknown</Badge>}
        </HStack>
        <Text fontSize="0.65rem" color="gray.500" fontFamily="mono" noOfLines={1}>{path}</Text>
      </VStack>
      <Box>{control}</Box>
    </HStack>
  )
}

export default ParameterField
