import { useEffect, useState } from 'react'
import {
  Box, VStack, HStack, Text, Heading, Button, Card, CardHeader, CardBody,
  Input, InputGroup, InputRightAddon, Alert, AlertIcon, AlertDescription,
} from '@chakra-ui/react'
import { getTrainStatus, updateInertiaSettings, updatePhaseSettings, updateGymDashboardSettings } from '../../../api/train'

// GYM's Settings sub-tab -- every "assumed"/placeholder tunable constant
// this feature set shipped with (constant+inertia's cap/filter, resistance-
// modes sub-phase 3; the concentric/eccentric phase detector's five
// constants, sub-phase 4; the dashboard's tolerances/rep-speed zones,
// sub-phase 5), made live-adjustable rather than requiring a code change +
// backend restart to retune. Backed by CableState (core/cable/state.py's
// set_inertia_settings()/set_phase_settings()/set_gym_dashboard_settings(),
// persisted the same sidecar-file way every other live setting in this app
// already is) -- these are genuinely shared TrainMode settings (Train tab's
// own Constant+Inertia segments obey the same inertia_kg_max too), just
// surfaced for editing here since that's where this session's user asked
// for them.
//
// One field group at a time is fetched/saved as its own request (matches
// the granularity of set_inertia_settings/set_phase_settings themselves) --
// loads current values once on mount rather than polling, since these
// change rarely and don't need live-telemetry-grade freshness.

const FIELD_GROUPS = [
  {
    key: 'inertia',
    title: 'Inertia',
    fields: [
      { key: 'inertia_kg_max', label: 'Inertia max', unit: 'kg', step: 0.5 },
      { key: 'inertia_velocity_filter_alpha', label: 'Velocity filter alpha', unit: '', step: 0.05 },
    ],
    save: (values) =>
      updateInertiaSettings({
        inertiaKgMax: Number(values.inertia_kg_max),
        inertiaVelocityFilterAlpha: Number(values.inertia_velocity_filter_alpha),
      }),
  },
  {
    key: 'phase',
    title: 'Concentric/Eccentric',
    fields: [
      { key: 'phase_force_delta_max_n', label: 'Max force delta', unit: 'N', step: 5 },
      { key: 'phase_velocity_deadband_m_s', label: 'Velocity deadband', unit: 'm/s', step: 0.01 },
      { key: 'phase_min_sustained_velocity_m_s', label: 'Min sustained velocity', unit: 'm/s', step: 0.01 },
      { key: 'phase_sustain_window_s', label: 'Sustain window', unit: 's', step: 0.01 },
      { key: 'phase_reversal_distance_m', label: 'Reversal distance', unit: 'm', step: 0.01 },
      { key: 'phase_ramp_duration_s', label: 'Ramp duration', unit: 's', step: 0.01 },
    ],
    save: (values) =>
      updatePhaseSettings({
        phaseForceDeltaMaxN: Number(values.phase_force_delta_max_n),
        velocityDeadbandMS: Number(values.phase_velocity_deadband_m_s),
        minSustainedVelocityMS: Number(values.phase_min_sustained_velocity_m_s),
        sustainWindowS: Number(values.phase_sustain_window_s),
        reversalDistanceM: Number(values.phase_reversal_distance_m),
        rampDurationS: Number(values.phase_ramp_duration_s),
      }),
  },
  {
    key: 'dashboard',
    title: 'Dashboard',
    fields: [
      { key: 'constant_force_tolerance_fraction', label: 'Constant "in range" tolerance', unit: 'fraction of target', step: 0.01 },
      { key: 'band_stretch_tolerance_pct', label: 'Band "reached target" tolerance', unit: '%', step: 1 },
      { key: 'rep_speed_low_m_s', label: 'Rep speed low (too slow below)', unit: 'm/s', step: 0.05 },
      { key: 'rep_speed_high_m_s', label: 'Rep speed high (too fast above)', unit: 'm/s', step: 0.05 },
      { key: 'rep_speed_max_m_s', label: 'Rep speed gauge max', unit: 'm/s', step: 0.05 },
    ],
    save: (values) =>
      updateGymDashboardSettings({
        constantForceToleranceFraction: Number(values.constant_force_tolerance_fraction),
        bandStretchTolerancePct: Number(values.band_stretch_tolerance_pct),
        repSpeedLowMS: Number(values.rep_speed_low_m_s),
        repSpeedHighMS: Number(values.rep_speed_high_m_s),
        repSpeedMaxMS: Number(values.rep_speed_max_m_s),
      }),
  },
]

const GymSettingsPanel = () => {
  const [values, setValues] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const [saveMessage, setSaveMessage] = useState(null)
  const [savingGroup, setSavingGroup] = useState(null)

  const loadValues = async () => {
    try {
      const status = await getTrainStatus()
      const cable = status.cable ?? {}
      const next = {}
      for (const group of FIELD_GROUPS) {
        for (const field of group.fields) next[field.key] = String(cable[field.key] ?? '')
      }
      setValues(next)
      setLoadError(null)
    } catch (e) {
      setLoadError(e.message)
    }
  }

  useEffect(() => {
    loadValues()
  }, [])

  const setField = (key, v) => setValues((prev) => ({ ...prev, [key]: v }))

  const handleSave = async (group) => {
    setSaveError(null)
    setSaveMessage(null)
    setSavingGroup(group.key)
    try {
      await group.save(values)
      await loadValues() // re-read back the persisted/clamped values
      setSaveMessage(`Saved ${group.title}`)
    } catch (e) {
      setSaveError(e.message)
    } finally {
      setSavingGroup(null)
    }
  }

  if (loadError) {
    return (
      <Alert status="error" variant="left-accent">
        <AlertIcon />
        <AlertDescription>{loadError}</AlertDescription>
      </Alert>
    )
  }

  if (!values) {
    return <Text fontSize="sm" color="paper.textSecondary">Loading settings…</Text>
  }

  return (
    <VStack align="stretch" spacing={4}>
      {saveError && (
        <Alert status="error" variant="left-accent">
          <AlertIcon />
          <AlertDescription>{saveError}</AlertDescription>
        </Alert>
      )}
      {saveMessage && (
        <Alert status="success" variant="left-accent">
          <AlertIcon />
          <AlertDescription>{saveMessage}</AlertDescription>
        </Alert>
      )}

      {FIELD_GROUPS.map((group) => (
        <Card key={group.key} bg="paper.bg" variant="outline" borderColor="paper.border" borderRadius="lg">
          <CardHeader pb={0}>
            <Heading size="sm" color="paper.textPrimary">{group.title}</Heading>
          </CardHeader>
          <CardBody>
            <VStack align="stretch" spacing={3}>
              <HStack spacing={3} wrap="wrap">
                {group.fields.map((field) => (
                  <Box key={field.key}>
                    <Text fontSize="xs" color="paper.textSecondary" mb={1}>{field.label}</Text>
                    <InputGroup size="sm" w="140px">
                      <Input
                        type="text"
                        inputMode="decimal"
                        fontFamily="mono"
                        value={values[field.key]}
                        onChange={(e) => setField(field.key, e.target.value)}
                      />
                      {field.unit && <InputRightAddon px={2} fontSize="xs">{field.unit}</InputRightAddon>}
                    </InputGroup>
                  </Box>
                ))}
              </HStack>
              <Button
                size="sm"
                colorScheme="accent"
                alignSelf="flex-start"
                onClick={() => handleSave(group)}
                isLoading={savingGroup === group.key}
              >
                Save
              </Button>
            </VStack>
          </CardBody>
        </Card>
      ))}
    </VStack>
  )
}

export default GymSettingsPanel
