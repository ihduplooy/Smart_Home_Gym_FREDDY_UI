import { useEffect, useState } from 'react'
import { Box, VStack } from '@chakra-ui/react'
import { getExerciseStatus } from '../../../api/exercise'
import TrainSettingsSection from './TrainSettingsSection'

// Item 5: the Settings/Startup block (Homing, Max-extension calibration,
// Spool calibration, guard toggles) used to live inside the Train tab; it's
// general cable setup, not training-specific, so it now gets its own
// top-level tab (between Configuration and Control). Purely a move -- see
// TrainSettingsSection.jsx's own header comment.
//
// Polls /api/exercise/status directly at a modest interval: this page has
// no chart and no need for Control/Train/Testing's ~150ms telemetry rate,
// just enough to keep Homing/calibration state and "is another mode
// running" fresh while the tab is open.
const POLL_INTERVAL_MS = 500

const SetupTab = ({ isActive = true }) => {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    if (!isActive) return undefined
    let cancelled = false
    let timer = null

    async function poll() {
      if (cancelled) return
      try {
        const next = await getExerciseStatus()
        if (!cancelled) setStatus(next)
      } catch {
        // Transient poll failure -- keep the last known status rather than
        // flickering the section's controls in and out.
      } finally {
        if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }
    poll()

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [isActive])

  return (
    <Box p={4} h="100%" maxW="1400px" mx="auto" overflow="auto" bg="paper.bg">
      <VStack spacing={4} align="stretch">
        <TrainSettingsSection status={status} />
      </VStack>
    </Box>
  )
}

export default SetupTab
