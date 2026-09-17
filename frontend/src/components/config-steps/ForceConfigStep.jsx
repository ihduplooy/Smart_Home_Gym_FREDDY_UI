import { Alert, AlertIcon, AlertDescription } from '@chakra-ui/react'
import ConfigStep from './ConfigStep'
import SoftwarePowerLimitsCard from './SoftwarePowerLimitsCard'

// Static explainer: the fields on this step are ordered to match the actual
// order these constraints are checked in the pipeline (PSU/bus-side first,
// then motor phase current, then the derived torque/force ceilings) -- see
// the comment above SCHEMA.force in configSchema.js for the full chain.
const chainDescription = (
  <Alert status="info" variant="left-accent" bg="gray.800" borderColor="odrive.400" mb={4} alignItems="start">
    <AlertIcon mt={0.5} />
    <AlertDescription fontSize="sm" color="gray.300">
      These limits form a chain, listed top to bottom in the order they&apos;re actually checked: the DC bus
      current limit (PSU capacity) bounds the motor phase current limit, which bounds the torque limit, which
      the app&apos;s own Software Power Limits then re-clamp in force/power terms. Whichever value is smallest —
      after converting to the same units — is the one that actually governs delivered force, regardless of what
      the others are set to.
    </AlertDescription>
  </Alert>
)

const ForceConfigStep = ({ wizard }) => (
  <ConfigStep
    stepId="force"
    wizard={wizard}
    extraTop={chainDescription}
    extraBottom={<SoftwarePowerLimitsCard />}
  />
)

export default ForceConfigStep
