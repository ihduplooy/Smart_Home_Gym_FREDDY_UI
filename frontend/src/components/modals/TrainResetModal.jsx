import { useState } from 'react'
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalCloseButton, ModalBody, ModalFooter,
  Button, VStack, Text, List, ListItem, Alert, AlertIcon, Box,
} from '@chakra-ui/react'
import { resetExercisePosition } from '../../api/exercise'

// Train tab's "Reset" control (train_tab_build_spec.md "calibration
// overhaul" item 1) -- a full state wipe distinct from re-homing: clears the
// homing reference (and marked max, in lockstep -- see CableState.reset()'s
// own docstring) plus any not-yet-saved spool-growth calibration points, and
// returns the tab to its pre-homed state. Deliberately does NOT touch
// anything persisted/calibrated (r0, k, saved growth points, homing/force
// settings, the guard-enforcement toggles, the telemetry buffer duration, or
// saved named profiles in localStorage) -- those are bench/session-durable
// properties, not this session's artifacts, same split CableState.reset()
// itself already draws.
//
// Same self-contained confirm-dialog shape as
// frontend/src/components/modals/EraseConfigModal.jsx (own busy state, own
// API call, calls back out only on success) rather than threading the
// network call through the parent.
const TrainResetModal = ({ isOpen, onClose, onReset }) => {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const handleReset = async () => {
    setError(null)
    setBusy(true)
    try {
      await resetExercisePosition()
      onReset()
      onClose()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} isCentered>
      <ModalOverlay />
      <ModalContent bg="gray.800" borderTop="3px solid" borderColor="orange.500">
        <ModalHeader color="orange.300">Reset Train tab</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack align="stretch" spacing={3}>
            {error && (
              <Alert status="error" variant="left-accent"><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>
            )}
            <Alert status="warning" bg="orange.900" borderRadius="md">
              <AlertIcon />
              <Box>
                <Text fontWeight="bold">This clears the current homing reference.</Text>
                <Text fontSize="sm">The cable will need to be re-homed before Train can start again.</Text>
              </Box>
            </Alert>
            <Box>
              <Text fontSize="sm" color="gray.300" mb={1}>This will clear:</Text>
              <List fontSize="sm" color="gray.400" spacing={0.5} pl={2}>
                <ListItem>• Homing reference and marked max-extension</ListItem>
                <ListItem>• Any unsaved spool-growth calibration points</ListItem>
                <ListItem>• The draft resistance profile and any planned/actual chart data</ListItem>
              </List>
            </Box>
            <Box>
              <Text fontSize="sm" color="gray.300" mb={1}>This will NOT touch:</Text>
              <List fontSize="sm" color="gray.400" spacing={0.5} pl={2}>
                <ListItem>• Spool radius (r0), wrap-growth (k), or saved growth calibration</ListItem>
                <ListItem>• Homing/force settings or the guard-enforcement toggles</ListItem>
                <ListItem>• Saved named resistance profiles</ListItem>
              </List>
            </Box>
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose} isDisabled={busy}>Cancel</Button>
          <Button colorScheme="orange" onClick={handleReset} isLoading={busy} loadingText="Resetting…">
            Reset
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  )
}

export default TrainResetModal
