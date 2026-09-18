import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalCloseButton,
  ModalBody,
  ModalFooter,
  Button,
  VStack,
  HStack,
  Text,
  Box,
} from '@chakra-ui/react'

/**
 * Generic confirmation dialog for the Apply action. Axis0-only (this board never
 * drives axis1).
 */
const ConfirmationModal = ({
  isOpen,
  onClose,
  onConfirm,
  isLoading,
  title = 'Apply & Save Configuration',
  description = 'This will write the commands below to the ODrive and save them to non-volatile memory. The device will reboot.',
  confirmText = 'Apply & Save',
  commandCount = 0,
  customCommandCount = 0,
}) => (
  <Modal isOpen={isOpen} onClose={onClose} isCentered>
    <ModalOverlay />
    <ModalContent bg="paper.bg">
      <ModalHeader color="accent.600">{title}</ModalHeader>
      <ModalCloseButton />
      <ModalBody>
        <VStack align="stretch" spacing={3}>
          <Text color="paper.textPrimary" fontSize="sm">{description}</Text>
          <Box bg="paper.bg" p={3} borderRadius="md">
            <HStack justify="space-between"><Text fontSize="sm" color="paper.textSecondary">Target:</Text>
              <Text fontSize="sm">Axis 0</Text></HStack>
            <HStack justify="space-between"><Text fontSize="sm" color="paper.textSecondary">Commands:</Text>
              <Text fontSize="sm">{commandCount}</Text></HStack>
            {customCommandCount > 0 && (
              <HStack justify="space-between"><Text fontSize="sm" color="paper.textSecondary">Custom commands:</Text>
                <Text fontSize="sm">{customCommandCount}</Text></HStack>
            )}
          </Box>
        </VStack>
      </ModalBody>
      <ModalFooter>
        <Button variant="ghost" mr={3} onClick={onClose}>Cancel</Button>
        <Button colorScheme="accent" onClick={onConfirm} isLoading={isLoading} loadingText="Processing…">
          {confirmText}
        </Button>
      </ModalFooter>
    </ModalContent>
  </Modal>
)

export default ConfirmationModal
