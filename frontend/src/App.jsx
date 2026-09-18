import { useRef, useState } from 'react'
import {
  Box,
  Flex,
  VStack,
  HStack,
  Heading,
  Button,
  AlertDialog,
  AlertDialogOverlay,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogBody,
  AlertDialogFooter,
  useDisclosure,
  useToast,
} from '@chakra-ui/react'
import { useSelector } from 'react-redux'

import DeviceList from './components/DeviceList'
import MainTabs from './components/MainTabs'
import { useDeviceTelemetry } from './hooks/useDeviceTelemetry'
import * as backend from './api/backend'
import './App.css'

// Mounts the single device telemetry WebSocket (status + charts) for the
// connected device. Safe to keep mounted; it no-ops when nothing is connected.
function TelemetryManager() {
  const serial = useSelector((s) => s.device.connectedDevice?.serial_number)
  useDeviceTelemetry(serial)
  return null
}

// Always-visible recovery control — not gated by connection state, since a
// wedged backend is exactly the situation where the connection state can't
// be trusted. Stops the motor, drops the device cache, and clears home/max
// calibration immediately, then respawns the backend process — the in-UI
// equivalent of killing and re-running Start Freddy.command, without needing
// a terminal or restarting the frontend dev server too. Polls
// /api/backend/version after triggering it so the button reflects when the
// fresh process is actually back up.
function RestartFreddyButton() {
  const { isOpen, onOpen, onClose } = useDisclosure()
  const [restarting, setRestarting] = useState(false)
  const cancelRef = useRef(null)
  const toast = useToast()

  const confirmRestart = async () => {
    onClose()
    setRestarting(true)
    try {
      await backend.restartBackend()
    } catch {
      // The process may go down before this request's own response makes it
      // back — that's the expected/successful path, not a failure.
    }
    // Give the reloader a moment to actually kill the old process before we
    // start polling, so an early poll doesn't hit it on its way down.
    await new Promise((r) => setTimeout(r, 800))
    for (let i = 0; i < 30; i++) {
      try {
        await backend.getBackendVersion()
        setRestarting(false)
        toast({ title: 'Freddy restarted', status: 'success', duration: 3000 })
        return
      } catch {
        await new Promise((r) => setTimeout(r, 1000))
      }
    }
    setRestarting(false)
    toast({ title: 'Freddy did not come back up', description: 'Check the terminal / logs.', status: 'error', duration: 6000 })
  }

  return (
    <>
      <Button size="sm" variant="outline" colorScheme="orange" onClick={onOpen} isLoading={restarting} loadingText="Restarting">
        Restart Freddy
      </Button>
      <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose} isCentered>
        <AlertDialogOverlay>
          <AlertDialogContent bg="paper.bg">
            <AlertDialogHeader color="orange.300">Restart Freddy?</AlertDialogHeader>
            <AlertDialogBody>
              Stops the motor, forgets the device connection, clears home/max
              calibration, and relaunches the backend process (the frontend
              keeps running). Use this any time the app stops responding or
              behaves oddly — it's the same recovery as re-running Start
              Freddy.command, just faster and without leaving the browser.
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} variant="ghost" onClick={onClose}>Cancel</Button>
              <Button colorScheme="orange" onClick={confirmRestart} ml={3}>Restart</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  )
}

// Actually shuts Freddy down -- unlike RestartFreddyButton above, nothing
// comes back up on its own afterward (see /api/quit's docstring: it kills
// both the debug reloader's watcher and the worker, plus whatever's on the
// frontend's port). Kept visually distinct (red, bottom of the sidebar,
// full-width) and behind its own confirmation dialog so it can't be mistaken
// for Restart -- Restart is the "things are acting up, get me back to a
// working state" button; this one ends the session outright.
function QuitFreddyButton() {
  const { isOpen, onOpen, onClose } = useDisclosure()
  const [quitting, setQuitting] = useState(false)
  const cancelRef = useRef(null)
  const toast = useToast()

  const confirmQuit = async () => {
    onClose()
    setQuitting(true)
    try {
      await backend.quitBackend()
    } catch {
      // The process goes down before this request's own response can make
      // it back in most cases -- that's the expected/successful path here,
      // not a failure (see /api/quit's docstring).
    }
    toast({
      title: 'Freddy stopped',
      description: 'The backend and frontend dev servers are shutting down. You can close this browser tab now.',
      status: 'info',
      duration: null,
      isClosable: true,
    })
    // Best-effort only: browsers block window.close() on a tab/window the
    // page itself didn't open (this one was opened by Start Freddy.command
    // via `open -a Safari`, not by a window.open() call from this page), so
    // this usually won't actually close anything -- the toast above is what
    // actually tells the user what to do next. Left in because it's free
    // and occasionally does work depending on browser/security settings.
    window.close()
  }

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        colorScheme="red"
        onClick={onOpen}
        isLoading={quitting}
        loadingText="Quitting"
        width="100%"
      >
        Quit Freddy
      </Button>
      <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose} isCentered>
        <AlertDialogOverlay>
          <AlertDialogContent bg="paper.bg">
            <AlertDialogHeader color="red.300">Quit Freddy?</AlertDialogHeader>
            <AlertDialogBody>
              Idles the motor, then stops the backend AND the frontend dev
              server completely -- unlike Restart, nothing comes back up on
              its own afterward. You'll need to re-run Start Freddy.command
              to use the app again (this tab's Restart button won't work
              anymore either, once the backend is down).
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} variant="ghost" onClick={onClose}>Cancel</Button>
              <Button colorScheme="red" onClick={confirmQuit} ml={3}>Quit</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  )
}

function App() {
  return (
    <Box bg="paper.bg" minH="100vh" color="paper.textPrimary">
      <TelemetryManager />
      <Flex h="100vh">
        {/* Left Sidebar */}
        <Box w="320px" bg="paper.bg" borderRight="1px solid" borderColor="paper.border">
          <VStack spacing={3} align="stretch" h="100%" p={4}>
            <HStack justify="space-between" align="center">
              <Heading size="md" color="accent.600">Smart Gym Control</Heading>
              <RestartFreddyButton />
            </HStack>
            <Box flex="1" minH={0} overflowY="auto">
              <DeviceList />
            </Box>
            <Box flexShrink={0}>
              <QuitFreddyButton />
            </Box>
          </VStack>
        </Box>

        {/* Main Content Area */}
        <MainTabs />
      </Flex>
    </Box>
  )
}

export default App