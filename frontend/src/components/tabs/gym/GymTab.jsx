import { Box, Tabs, TabList, TabPanels, Tab, TabPanel } from '@chakra-ui/react'
import TrainSessionShell from '../train/TrainSessionShell'
import GymProfileEditor from './GymProfileEditor'
import GymSettingsPanel from './GymSettingsPanel'

// GYM's own Session/Settings split -- the session view (status, the
// Constant/Band/Concentric-Eccentric builder, telemetry) is everything GYM
// had before; Settings (GymSettingsPanel.jsx) is the sub-tab the user asked
// for so the "assumed" placeholder tuning constants throughout GYM (inertia
// range, phase-detector deadzone/timing) can be configured without editing
// code. Session stays mounted (isLazy/keepMounted-free here -- Chakra Tabs
// unmounts inactive panels by default, which is fine: TrainSessionShell's
// own telemetry hook is gated by `isActive` at the MainTabs level already,
// not by whether this inner Settings tab happens to be open).
const GymTab = (props) => (
  <Box h="100%" overflow="auto">
    <Tabs variant="enclosed" colorScheme="accent" isLazy>
      <TabList px={4} pt={2}>
        <Tab>Session</Tab>
        <Tab>Settings</Tab>
      </TabList>
      <TabPanels>
        <TabPanel p={0}>
          <TrainSessionShell {...props} title="GYM" EditorComponent={GymProfileEditor} showStats={false} showReset={false} />
        </TabPanel>
        <TabPanel p={4}>
          <GymSettingsPanel />
        </TabPanel>
      </TabPanels>
    </Tabs>
  </Box>
)

export default GymTab
