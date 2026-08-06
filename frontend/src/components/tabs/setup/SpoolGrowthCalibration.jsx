import { useState } from 'react'
import {
  Box, VStack, HStack, Text, Badge, Button, Input, InputGroup, InputRightAddon,
  Alert, AlertIcon, AlertDescription, IconButton,
} from '@chakra-ui/react'
import { CloseIcon } from '@chakra-ui/icons'
import {
  startSpoolGrowthCalibration, recordGrowthPoint, removeGrowthPoint, clearGrowthPoints,
  cancelSpoolGrowthCalibration, saveGrowthCalibration, clearGrowthCalibration,
} from '../../../api/exercise'

// Experimental multi-point spool-growth calibration (train tab calibration
// overhaul item 4/5) -- determines how the effective spool radius grows as
// strap winds on, from real measurements at several positions, rather than
// an assumed per-rotation constant. Generalizes the existing single-
// measurement k flow (kept as-is, above this section) into a piecewise
// model fit through every recorded point (core/cable/geometry.py
// ::build_growth_segments) -- see SpoolModelDiagnostics for the resulting
// equations/segments once saved.
//
// Recording holds the cable under the same light calib_hold_force_n torque
// max-extension calibration already uses (keeps the webbing taut so the
// encoder reading is trustworthy while reading a tape measure) -- same
// action shape as start_max_calibration, just a different action name
// (start_spool_growth_calibration) so it can't be confused with actually
// setting the max extension.
const SpoolGrowthCalibration = ({ status }) => {
  const [lengthText, setLengthText] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const control = status?.control
  const cable = status?.cable
  const spoolModel = cable?.spool_model
  const setupSessionRunning = Boolean(control?.running && control?.mode === 'exercise')
  const anotherModeRunning = Boolean(control?.running && !setupSessionRunning)
  const action = setupSessionRunning ? control?.extra?.action ?? null : null
  const isHomed = cable?.is_homed ?? false
  const inProgress = action === 'spool_growth_calibrating'

  const pendingPoints = spoolModel?.pending_growth_points ?? []
  const savedPoints = spoolModel?.growth_points ?? []

  const run = async (fn, ...args) => {
    setError(null)
    setBusy(true)
    try {
      await fn(...args)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleRecord = async () => {
    const length = Number(lengthText)
    if (lengthText === '' || !Number.isFinite(length) || length < 0) {
      setError('Measured length must be a non-negative number')
      return
    }
    setError(null)
    setBusy(true)
    try {
      await recordGrowthPoint(length)
      setLengthText('')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const currentTurns = cable?.cable_position_turns
  const currentLength = control?.extra?.cable_length_m

  return (
    <Box borderTop="1px solid" borderColor="gray.700" pt={3}>
      <HStack justify="space-between" mb={2}>
        <Text fontSize="sm" fontWeight="semibold" color="gray.200">Spool growth calibration (experimental)</Text>
        <Badge colorScheme={savedPoints.length > 0 ? 'green' : 'gray'} variant="outline">
          {savedPoints.length > 0 ? `${savedPoints.length} point${savedPoints.length === 1 ? '' : 's'} saved` : 'not calibrated'}
        </Badge>
      </HStack>

      {error && (
        <Alert status="error" variant="left-accent" mb={2}><AlertIcon /><AlertDescription>{error}</AlertDescription></Alert>
      )}

      {!inProgress && (
        <>
          <Text fontSize="xs" color="gray.400" mb={2}>
            Measure the actual cable length at several reel-out positions and record each one here; the
            recorded points are fit into a piecewise model of how the effective spool radius grows with
            rotations, rather than assuming a single constant rate. Uses the spool radius (r0) set above as
            its starting point. Recording holds the cable under the same light force as max-extension
            calibration, so it stays put while you read the tape measure.
          </Text>
          <Button
            size="sm"
            colorScheme="odrive"
            onClick={() => run(startSpoolGrowthCalibration)}
            isDisabled={!setupSessionRunning || busy || !isHomed || anotherModeRunning || (action != null && action !== 'idle')}
            isLoading={busy}
          >
            Start spool growth calibration
          </Button>

          {savedPoints.length > 0 && (
            <Box mt={3}>
              <Text fontSize="xs" color="gray.400" mb={1}>Saved calibration points:</Text>
              <VStack align="stretch" spacing={1} mb={2}>
                {savedPoints.map((p, i) => (
                  <HStack key={i} justify="space-between" fontSize="xs" color="gray.300" fontFamily="mono">
                    <Text>{p.turns_from_home.toFixed(3)} turns</Text>
                    <Text>{p.length_m.toFixed(4)} m</Text>
                  </HStack>
                ))}
              </VStack>
              <Button size="xs" variant="outline" colorScheme="red" onClick={() => run(clearGrowthCalibration)} isLoading={busy}>
                Clear saved growth calibration
              </Button>
            </Box>
          )}
        </>
      )}

      {inProgress && (
        <VStack align="stretch" spacing={3}>
          <HStack justify="space-between" fontSize="xs" color="gray.400" fontFamily="mono">
            <Text>position: {currentTurns != null ? `${currentTurns.toFixed(3)} turns` : '—'}</Text>
            <Text>model length: {currentLength != null ? `${currentLength.toFixed(4)} m` : '—'}</Text>
          </HStack>

          <HStack spacing={3} align="flex-end">
            <Box>
              <Text fontSize="xs" color="gray.400" mb={1}>Measured length</Text>
              <InputGroup size="sm" w="130px">
                <Input type="text" inputMode="decimal" fontFamily="mono" value={lengthText} onChange={(e) => setLengthText(e.target.value)} />
                <InputRightAddon px={2} fontSize="xs">m</InputRightAddon>
              </InputGroup>
            </Box>
            <Button size="sm" onClick={handleRecord} isLoading={busy}>Record point</Button>
          </HStack>

          {pendingPoints.length > 0 && (
            <VStack align="stretch" spacing={1}>
              {pendingPoints.map((p, i) => (
                <HStack key={i} justify="space-between" fontSize="xs" color="gray.300" fontFamily="mono">
                  <Text>{p.turns_from_home.toFixed(3)} turns</Text>
                  <Text>{p.length_m.toFixed(4)} m</Text>
                  <IconButton
                    aria-label="Remove point"
                    icon={<CloseIcon boxSize={2} />}
                    size="xs"
                    variant="ghost"
                    onClick={() => run(removeGrowthPoint, i)}
                    isDisabled={busy}
                  />
                </HStack>
              ))}
            </VStack>
          )}

          <HStack spacing={3}>
            <Button size="sm" variant="outline" onClick={() => run(clearGrowthPoints)} isDisabled={busy || pendingPoints.length === 0}>
              Clear all
            </Button>
            <Button size="sm" colorScheme="red" variant="outline" onClick={() => run(cancelSpoolGrowthCalibration)} isDisabled={busy}>
              Discard
            </Button>
            <Button size="sm" colorScheme="green" onClick={() => run(saveGrowthCalibration)} isDisabled={busy || pendingPoints.length === 0}>
              Save & finish
            </Button>
          </HStack>
        </VStack>
      )}
    </Box>
  )
}

export default SpoolGrowthCalibration
