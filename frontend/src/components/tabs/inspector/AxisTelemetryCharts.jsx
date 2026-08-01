import { useEffect, useMemo, useRef, useState } from 'react'
import { Box, Checkbox, Text, VStack, Wrap, WrapItem } from '@chakra-ui/react'
import { useDispatch, useSelector } from 'react-redux'
import * as backend from '../../../api/backend'
import { addProperty, removeProperty } from '../../../store/slices/telemetrySlice'
import TelemetryTimeSeriesChart from '../../shared/TelemetryTimeSeriesChart'
import { FIXED_AXIS_TELEMETRY_PATHS } from './fixedAxisTelemetry'

// Inspector's telemetry slice buffers by SAMPLE COUNT, not age (maxSamples:
// 1000 in telemetrySlice.js) at a 10ms streaming interval -- ~10s of real
// history, matching LiveCharts.jsx's own WINDOW_MS_OPTIONS (1/2.5/5/10s +
// All). Reused here instead of TelemetryTimeSeriesChart's Train/Control-
// oriented 90s default so the range buttons never offer a window the buffer
// can't actually hold.
const BUFFER_S = 10
const RANGE_OPTIONS_SECONDS = [1, 2.5, 5, 10]

const COLOR_MEASURED = '#63B3ED'
const COLOR_SETPOINT = '#F6AD55'
const COLOR_IQ = '#68D391'
const COLOR_TORQUE = '#B794F6'
const COLOR_ID = '#FC8181'
const COLOR_IBUS = '#4FD1C7'
const COLOR_VBUS = '#FBD38D'

const FROZEN_SAMPLES = Object.freeze({})

// Each fixed graph's underlying property path(s) (what gets subscribed on
// the shared device WebSocket when the graph is toggled on -- see the
// subscribe/unsubscribe effect below) and its TelemetryTimeSeriesChart
// `lines` config. `torque` deliberately shares Iq's path (it's a client-side
// computed line, not a separate live property) so switching Iq off while
// Torque stays on doesn't drop the subscription out from under it.
function buildGraphs(torqueConstant) {
  return [
    {
      id: 'position',
      title: 'Position (turns)',
      paths: [FIXED_AXIS_TELEMETRY_PATHS.posEstimate, FIXED_AXIS_TELEMETRY_PATHS.posSetpoint],
      label: 'Position',
      lines: [
        { key: 'pos_estimate', label: 'Position estimate', unit: 'turns', color: COLOR_MEASURED, side: 'left', defaultOn: true },
        {
          key: 'pos_setpoint',
          label: 'Position setpoint',
          unit: 'turns',
          color: COLOR_SETPOINT,
          side: 'left',
          defaultOn: true,
          axisKey: 'pos_estimate',
          dashed: true,
        },
      ],
    },
    {
      id: 'velocity',
      title: 'Velocity (turns/s)',
      paths: [FIXED_AXIS_TELEMETRY_PATHS.velEstimate, FIXED_AXIS_TELEMETRY_PATHS.velSetpoint],
      label: 'Velocity',
      lines: [
        { key: 'vel_estimate', label: 'Velocity estimate', unit: 'turns/s', color: COLOR_MEASURED, side: 'left', defaultOn: true },
        {
          key: 'vel_setpoint',
          label: 'Velocity setpoint',
          unit: 'turns/s',
          color: COLOR_SETPOINT,
          side: 'left',
          defaultOn: true,
          axisKey: 'vel_estimate',
          dashed: true,
        },
      ],
    },
    {
      id: 'iq',
      title: 'Torque current -- Iq measured (A)',
      paths: [FIXED_AXIS_TELEMETRY_PATHS.iqMeasured],
      label: 'Iq (torque current)',
      lines: [{ key: 'iq_measured', label: 'Iq measured', unit: 'A', color: COLOR_IQ, side: 'left', defaultOn: true }],
    },
    {
      id: 'torque',
      title:
        typeof torqueConstant === 'number'
          ? `Computed torque -- Iq × ${torqueConstant} Nm/A (Nm)`
          : 'Computed torque (Nm)',
      paths: [FIXED_AXIS_TELEMETRY_PATHS.iqMeasured],
      label: 'Torque (computed)',
      lines: [{ key: 'torque_computed', label: 'Torque (computed)', unit: 'Nm', color: COLOR_TORQUE, side: 'left', defaultOn: true }],
    },
    {
      id: 'id',
      title: 'Field current -- Id measured (A, should sit near zero)',
      paths: [FIXED_AXIS_TELEMETRY_PATHS.idMeasured],
      label: 'Id (field current)',
      lines: [{ key: 'id_measured', label: 'Id measured', unit: 'A', color: COLOR_ID, side: 'left', defaultOn: true }],
    },
    {
      id: 'ibus',
      title: 'Bus current -- ibus (A, negative = regen/braking)',
      paths: [FIXED_AXIS_TELEMETRY_PATHS.ibus],
      label: 'Ibus (bus current)',
      lines: [{ key: 'ibus', label: 'Ibus', unit: 'A', color: COLOR_IBUS, side: 'left', defaultOn: true }],
    },
    {
      id: 'vbus',
      title: 'Bus voltage -- vbus_voltage (V)',
      paths: [FIXED_AXIS_TELEMETRY_PATHS.vbusVoltage],
      label: 'Vbus (bus voltage)',
      lines: [{ key: 'vbus_voltage', label: 'Vbus', unit: 'V', color: COLOR_VBUS, side: 'left', defaultOn: true }],
    },
  ]
}

// Only vbus on by default -- matches this tab's pre-existing baseline (the
// rest are opt-in). Each fixed property read here is a real per-tick round
// trip to the device on real hardware (telemetry.py's WS loop reads every
// subscribed path serially, under the same per-device lock the Emergency
// Stop button and other REST actions need) -- having all seven on
// unconditionally by default measurably slowed the whole app down, including
// Emergency Stop's response time, on real hardware (found live, 1 August
// 2026). Keeping the default light and making each graph opt-in via the
// checkboxes below is the fix, not just a nicety.
const DEFAULT_ENABLED = { position: false, velocity: false, iq: false, torque: false, id: false, ibus: false, vbus: true }

// Inspector's telemetry.samples is {path: [{t, v}, ...]}, one array per
// property, independently buffered. TelemetryTimeSeriesChart (the Train/
// Control shared chart) instead wants one row per tick with every line's
// value alongside it, so overlaying two paths (e.g. pos_estimate +
// pos_setpoint) or deriving a computed line lands on the same x position.
// Rows are keyed by the exact epoch-ms `t` telemetrySlice.pushBatch stamps
// every sample with -- every path here is always part of the same
// subscription batch (see useDeviceTelemetry.js), so same-tick samples share
// that timestamp; a path that dropped out for one tick (a stale/errored
// read, filtered by pushBatch before it reaches the store) just leaves that
// key undefined on the row rather than misaligning everything else. Paths
// that aren't currently subscribed (their graph is toggled off) simply have
// no entry in `samples`, so this stays cheap regardless of how many graphs
// are enabled.
function mergeSeries(samples, torqueConstant) {
  const rows = new Map()
  const put = (key, path) => {
    const arr = samples[path]
    if (!arr) return
    for (const s of arr) {
      let row = rows.get(s.t)
      if (!row) {
        row = { t: s.t / 1000 }
        rows.set(s.t, row)
      }
      row[key] = s.v
    }
  }
  put('pos_estimate', FIXED_AXIS_TELEMETRY_PATHS.posEstimate)
  put('pos_setpoint', FIXED_AXIS_TELEMETRY_PATHS.posSetpoint)
  put('vel_estimate', FIXED_AXIS_TELEMETRY_PATHS.velEstimate)
  put('vel_setpoint', FIXED_AXIS_TELEMETRY_PATHS.velSetpoint)
  put('iq_measured', FIXED_AXIS_TELEMETRY_PATHS.iqMeasured)
  put('id_measured', FIXED_AXIS_TELEMETRY_PATHS.idMeasured)
  put('ibus', FIXED_AXIS_TELEMETRY_PATHS.ibus)
  put('vbus_voltage', FIXED_AXIS_TELEMETRY_PATHS.vbusVoltage)

  const out = Array.from(rows.values()).sort((a, b) => a.t - b.t)
  if (typeof torqueConstant === 'number') {
    for (const row of out) {
      if (typeof row.iq_measured === 'number') row.torque_computed = row.iq_measured * torqueConstant
    }
  }
  return out
}

// Fixed, toggleable set of axis0 graphs (position/velocity vs. their
// setpoints, torque current, computed torque, field current, bus current,
// bus voltage) -- distinct from LiveCharts.jsx's free-form, user-picked
// property charts below it. Graphs only, no error/status fields, per spec.
const AxisTelemetryCharts = ({ isActive = true }) => {
  const dispatch = useDispatch()
  const liveSamples = useSelector((s) => s.telemetry.samples)
  const samples = isActive ? liveSamples : FROZEN_SAMPLES
  const [torqueConstant, setTorqueConstant] = useState(null)
  const [enabled, setEnabled] = useState(DEFAULT_ENABLED)

  const graphs = useMemo(() => buildGraphs(torqueConstant), [torqueConstant])

  // Subscribe only what's actually needed for the currently-enabled graphs,
  // and drop subscriptions a toggle-off no longer needs -- each subscribed
  // path is a real per-tick device read on real hardware, so this is the
  // actual fix for the whole-app slowdown a permanently-on subscription set
  // caused (see DEFAULT_ENABLED's comment). `subscribedRef` tracks only the
  // paths THIS component added, so toggling a graph off never rips out a
  // path the free-form "Custom Properties" list below might separately have
  // selected on its own.
  const subscribedRef = useRef(new Set())
  useEffect(() => {
    const needed = new Set()
    graphs.forEach((g) => {
      if (enabled[g.id]) g.paths.forEach((p) => needed.add(p))
    })
    for (const p of needed) {
      if (!subscribedRef.current.has(p)) dispatch(addProperty(p))
    }
    for (const p of subscribedRef.current) {
      if (!needed.has(p)) dispatch(removeProperty(p))
    }
    subscribedRef.current = needed
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, dispatch])

  useEffect(() => {
    return () => {
      subscribedRef.current.forEach((p) => dispatch(removeProperty(p)))
      subscribedRef.current = new Set()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch])

  // MOTOR_TORQUE_CONSTANT lives in config/board_constants.py -- the single
  // source of truth (see boardDefaults.js) -- fetched, never duplicated here.
  useEffect(() => {
    let cancelled = false
    backend
      .getBoardConstants()
      .then((bc) => {
        if (!cancelled) setTorqueConstant(typeof bc?.motor?.torque_constant === 'number' ? bc.motor.torque_constant : null)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const series = useMemo(() => mergeSeries(samples, torqueConstant), [samples, torqueConstant])

  const toggleGraph = (id) => setEnabled((prev) => ({ ...prev, [id]: !prev[id] }))

  return (
    <VStack align="stretch" spacing={4}>
      <Box bg="gray.800" border="1px solid" borderColor="gray.700" borderRadius="md" p={3}>
        <Text fontSize="xs" color="gray.400" mb={2}>
          Axis0 telemetry -- toggle graphs on/off. Each one adds a live property read on the device, so leave off whatever you aren't looking at right now.
        </Text>
        <Wrap spacing={4}>
          {graphs.map((g) => (
            <WrapItem key={g.id}>
              <Checkbox size="sm" colorScheme="odrive" isChecked={Boolean(enabled[g.id])} onChange={() => toggleGraph(g.id)}>
                <Text fontSize="sm" color="gray.200">{g.label}</Text>
              </Checkbox>
            </WrapItem>
          ))}
        </Wrap>
      </Box>

      {graphs
        .filter((g) => enabled[g.id])
        .map((g) => (
          <TelemetryTimeSeriesChart
            key={g.id}
            title={g.title}
            series={series}
            bufferS={BUFFER_S}
            rangeOptionsSeconds={RANGE_OPTIONS_SECONDS}
            lines={g.lines}
          />
        ))}
    </VStack>
  )
}

export default AxisTelemetryCharts
