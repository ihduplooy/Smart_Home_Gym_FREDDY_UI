import { Box, Alert, AlertIcon } from '@chakra-ui/react'
import AxisTelemetryCharts from './AxisTelemetryCharts'
import '../../../styles/InspectorTab.css'

// Trimmed down (5 Aug 2026) to just the fixed axis0 telemetry graphs --
// the free-form property tree/custom-property picker + CSV recording it
// fed (PropertyTree.jsx, PropertyItem.jsx, LiveCharts.jsx,
// useApiPropertyTree.js, utils/apiReference.js) were removed: ~130 of its
// 209 properties were write-only config (gains/limits/calibration, already
// editable on the Configuration tab) nobody ever ticked here, and the
// handful of read-only ones actually worth watching (vbus_voltage, ibus,
// brake_resistor_current, ...) weren't worth keeping the whole browser
// around for. If ad-hoc property inspection is needed again, that's the
// feature to rebuild, not a partial patch of what's left here.
const InspectorTab = ({ isConnected, isActive = true }) => {
  return (
    <Box className="inspector-tab" h="100%" display="flex" flexDirection="column" bg="paper.bg">
      <Box flex="1" minH="0" p={4} overflow="auto">
        {!isConnected && (
          <Alert status="info" variant="left-accent" mb={3} borderRadius="md">
            <AlertIcon />
            Connect to an ODrive to read live values.
          </Alert>
        )}
        <AxisTelemetryCharts isActive={isActive} />
      </Box>
    </Box>
  )
}

export default InspectorTab
