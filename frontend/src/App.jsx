import {
  Box,
  Flex,
  VStack,
  HStack,
  Heading,
  Badge,
  Text,
  Divider,
} from '@chakra-ui/react'
import { useSelector } from 'react-redux'

import DeviceList from './components/DeviceList'
import MainTabs from './components/MainTabs'
import { useDeviceTelemetry } from './hooks/useDeviceTelemetry'
import './App.css'

// Mounts the single device telemetry WebSocket (status + charts) for the
// connected device. Safe to keep mounted; it no-ops when nothing is connected.
function TelemetryManager() {
  const serial = useSelector((s) => s.device.connectedDevice?.serial_number)
  useDeviceTelemetry(serial)
  return null
}

// Sidebar footer: static device identity (status / serial / firmware).
function DeviceFooter() {
  const { isConnected, connectedDevice } = useSelector((s) => s.device)
  if (!isConnected || !connectedDevice) return null
  return (
    <Box p={3} bg="gray.700" borderRadius="md">
      <VStack spacing={2} align="stretch">
        <HStack justify="space-between">
          <Text fontSize="sm" color="gray.300">Status:</Text>
          <Badge colorScheme="green" variant="solid">Connected</Badge>
        </HStack>
        <HStack justify="space-between">
          <Text fontSize="sm" color="gray.300">Device:</Text>
          <Text fontSize="sm" color="white">ODrive</Text>
        </HStack>
        <HStack justify="space-between">
          <Text fontSize="sm" color="gray.300">Serial:</Text>
          <Text fontSize="sm" color="white" fontFamily="mono">{connectedDevice.serial_number}</Text>
        </HStack>
        <HStack justify="space-between">
          <Text fontSize="sm" color="gray.300">Firmware:</Text>
          <Text fontSize="sm" color="odrive.300">{connectedDevice.fw_version}</Text>
        </HStack>
      </VStack>
    </Box>
  )
}

function App() {
  return (
    <Box bg="gray.900" minH="100vh" color="white">
      <TelemetryManager />
      <Flex h="100vh">
        {/* Left Sidebar */}
        <Box w="320px" bg="gray.800" borderRight="1px solid" borderColor="gray.600">
          <VStack spacing={3} align="stretch" h="100%" p={4}>
            <Heading size="md" color="odrive.300">ODrive GUI</Heading>
            <Box flex="1" minH={0} overflowY="auto">
              <DeviceList />
            </Box>
            <Divider />
            <DeviceFooter />
          </VStack>
        </Box>

        {/* Main Content Area */}
        <MainTabs />
      </Flex>
    </Box>
  )
}

export default App