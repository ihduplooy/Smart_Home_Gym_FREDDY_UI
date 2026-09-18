import { Box, HStack, Text, Input, Checkbox } from '@chakra-ui/react'

// Small reusable per-axis "Auto | min–max" control. Originally built for the
// Train tab's telemetry/position charts (25 July 2026, requested so
// independently-scaled quantities sharing a chart -- e.g. position in
// metres next to torque in Nm -- can each get a visible range that actually
// fits the data, not just whatever recharts' auto-domain picks across every
// enabled line at once); moved to components/shared/ (29 July 2026, "same
// graphs everywhere" pass) once TelemetryTimeSeriesChart itself became a
// cross-tab component rather than Train-only.
//
// `range` is `{auto, min, max}` (min/max are text, same string-state-plus-
// validity convention as every numeric input elsewhere in this app); `min`/
// `max` are only consulted while `auto` is false. The domain-resolution
// helper itself lives in utils/chartDisplay.js (not here) so this file only
// exports a component -- keeps React Fast Refresh happy.

const AxisRangeControl = ({ label, color, range, onChange }) => {
  return (
    <HStack spacing={2}>
      <HStack spacing={1.5} minW="70px">
        <Box w="8px" h="8px" borderRadius="full" bg={color} flexShrink={0} />
        <Text fontSize="xs" color="paper.textSecondary">{label}</Text>
      </HStack>
      <Checkbox
        size="sm"
        isChecked={range.auto}
        onChange={() => onChange({ ...range, auto: !range.auto })}
        colorScheme="accent"
      >
        <Text fontSize="xs" color="paper.textSecondary">Auto</Text>
      </Checkbox>
      {!range.auto && (
        <>
          <Input
            size="xs"
            w="64px"
            fontFamily="mono"
            placeholder="min"
            value={range.min}
            onChange={(e) => onChange({ ...range, min: e.target.value })}
          />
          <Text fontSize="xs" color="paper.textSecondary">–</Text>
          <Input
            size="xs"
            w="64px"
            fontFamily="mono"
            placeholder="max"
            value={range.max}
            onChange={(e) => onChange({ ...range, max: e.target.value })}
          />
        </>
      )}
    </HStack>
  )
}

export default AxisRangeControl
