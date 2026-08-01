import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSelector } from 'react-redux'
import * as backend from '../api/backend'
import { buildDeviceSnapshot, diffConfig, toCommandStrings } from '../utils/configDiff'
import { expandAxisPath } from '../utils/odriveRegistry'
import { parseConsoleCommand } from '../utils/consoleCommand'
import { STEPS, resolvePath, stepFields } from '../utils/configSchema'
import { validateConfig } from '../utils/configValidation'
import { expandValues } from '../utils/presets/presetsManager'
import { boardConstantsToTemplateValues } from '../utils/boardDefaults'

/**
 * Engine for the configuration wizard.
 *
 * Holds a clean device snapshot (only successfully-read scalars), the desired
 * form values, and the set of user-edited paths. Change detection runs through
 * configDiff so the Apply list only ever contains real, intended changes — the
 * fix for the phantom-command bug. Values are keyed by concrete (axis-expanded)
 * path.
 *
 * On pull, `desired` is seeded with this project's board constants
 * (config/board_constants.py, via GET /api/board-constants) for any field the
 * device doesn't already report a value for — real device values always win.
 * This is what makes the wizard "open pre-loaded" instead of blank: it's a
 * verification/tweak tool against known project defaults, not a from-scratch
 * setup flow.
 */
export function useConfigWizard() {
  const { connectedDevice, fw_line, isConnected } = useSelector((s) => s.device)
  const selectedAxis = useSelector((s) => s.ui.selectedAxis)
  const serial = connectedDevice?.serial_number
  const fwLine = fw_line || 5

  const [snapshot, setSnapshot] = useState({})
  const [desired, setDesired] = useState({})
  const [editedPaths, setEditedPaths] = useState(() => new Set())
  const [unreadable, setUnreadable] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadingPaths, setLoadingPaths] = useState(() => new Set())
  const [boardDefaults, setBoardDefaults] = useState({})
  // Axes we've already seeded with board-constant defaults this connection.
  // Board defaults should only pre-fill a field the *first* time you view an
  // axis (so the wizard "opens pre-loaded") — not on every pull, which used
  // to silently overwrite live edits (or the device's actual current value)
  // back to the project's fixed target every time, including the automatic
  // re-pull right after every Apply. Reset on disconnect so a fresh connect
  // gets the pre-loaded treatment again.
  const seededAxesRef = useRef(new Set())

  // Fetch this project's board constants once; independent of device connection.
  useEffect(() => {
    let cancelled = false
    backend.getBoardConstants()
      .then((bc) => { if (!cancelled) setBoardDefaults(boardConstantsToTemplateValues(bc)) })
      .catch(() => {}) // no defaults available -> wizard just falls back to device values
    return () => { cancelled = true }
  }, [])

  // Resolve a schema field to its concrete device path for the current axis/line.
  const concretePath = useCallback(
    (field) => {
      const resolved = resolvePath(field.path, fwLine)
      // Axis-scoped paths carry the `{n}` placeholder; everything else is global.
      return resolved.includes('{n}') ? expandAxisPath(resolved, selectedAxis) : resolved
    },
    [fwLine, selectedAxis]
  )

  const allPaths = useMemo(() => {
    const paths = new Set()
    for (const step of STEPS) {
      if (step.id === 'apply') continue
      for (const field of stepFields(step.id)) paths.add(concretePath(field))
    }
    return [...paths]
  }, [concretePath])

  const pullConfig = useCallback(async () => {
    if (!serial) return
    setLoading(true)
    try {
      const results = await backend.readProperties(serial, allPaths)
      const { snapshot: snap, unreadable: bad } = buildDeviceSnapshot(results)
      setSnapshot(snap) // untouched device readback; diffConfig compares desired against this
      setUnreadable(bad)
      // This project's board-constant defaults pre-fill the small, curated set
      // of fields we have an opinion on (config/board_constants.py) — but only
      // the first time this axis is viewed this connection. After that,
      // `desired` just tracks the live device snapshot (still overridable by
      // the user's own edits via setValue/setValueByPath), so an Apply doesn't
      // keep re-suggesting the project's fixed target as a "pending change"
      // every time you deviate from it on purpose (e.g. testing a different
      // mode from the Control tab).
      if (!seededAxesRef.current.has(selectedAxis)) {
        seededAxesRef.current.add(selectedAxis)
        setDesired({ ...snap, ...expandValues(boardDefaults, selectedAxis) })
      } else {
        setDesired(snap)
      }
      setEditedPaths(new Set())
    } finally {
      setLoading(false)
    }
  }, [serial, allPaths, boardDefaults, selectedAxis])

  // Auto-pull on connect / axis change / once board defaults arrive.
  useEffect(() => {
    if (!serial) {
      seededAxesRef.current = new Set() // next connect starts pre-loaded again
      return
    }
    pullConfig()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serial, selectedAxis, fwLine, boardDefaults])

  const setValue = useCallback(
    (field, value) => {
      const path = concretePath(field)
      setDesired((prev) => ({ ...prev, [path]: value }))
      setEditedPaths((prev) => new Set(prev).add(path))
    },
    [concretePath]
  )

  // Directly set a value by concrete path (used by "Use Calculated", unit toggles).
  const setValueByPath = useCallback((path, value) => {
    setDesired((prev) => ({ ...prev, [path]: value }))
    setEditedPaths((prev) => new Set(prev).add(path))
  }, [])

  const refreshField = useCallback(
    async (field) => {
      if (!serial) return
      const path = concretePath(field)
      setLoadingPaths((prev) => new Set(prev).add(path))
      try {
        const results = await backend.readProperties(serial, [path])
        const { snapshot: snap } = buildDeviceSnapshot(results)
        if (Object.prototype.hasOwnProperty.call(snap, path)) {
          setSnapshot((prev) => ({ ...prev, [path]: snap[path] }))
          setDesired((prev) => ({ ...prev, [path]: snap[path] }))
          setEditedPaths((prev) => {
            const next = new Set(prev)
            next.delete(path) // refreshed to real value -> no longer a pending edit
            return next
          })
          setUnreadable((prev) => prev.filter((p) => p !== path))
        }
      } finally {
        setLoadingPaths((prev) => {
          const next = new Set(prev)
          next.delete(path)
          return next
        })
      }
    },
    [serial, concretePath]
  )

  const fieldState = useCallback(
    (field) => {
      const path = concretePath(field)
      return {
        path,
        value: desired[path],
        known: Object.prototype.hasOwnProperty.call(snapshot, path),
        edited: editedPaths.has(path),
        isLoading: loadingPaths.has(path),
      }
    },
    [concretePath, desired, snapshot, editedPaths, loadingPaths]
  )

  const valueOf = useCallback((path) => desired[path], [desired])

  const validation = useMemo(
    () => validateConfig({ valueOf, axis: selectedAxis, fwLine }),
    [valueOf, selectedAxis, fwLine]
  )

  const changes = useMemo(
    () => diffConfig({ snapshot, desired, editedPaths }),
    [snapshot, desired, editedPaths]
  )

  // Write the pending changes, save to NVM, then re-pull the clean snapshot.
  const applyChanges = useCallback(async () => {
    if (!serial || changes.length === 0) return { written: 0, failed: [] }
    const writes = changes.map(({ path, value }) => ({ path, value }))
    const results = await backend.writeProperties(serial, writes)
    const failed = (results || []).filter((r) => r.status !== 'ok')
    await backend.invokeCommand(serial, 'save_configuration', [])
    await pullConfig()
    return { written: writes.length - failed.length, failed }
  }, [serial, changes, pullConfig])

  // Build odrivetool-style command strings for the Apply tab.
  // onlyChanged: only diff vs device (default); otherwise every field's current
  // desired value. Axis0-only (this board never drives axis1).
  const buildCommandStrings = useCallback(
    ({ onlyChanged = true } = {}) => {
      let items
      if (onlyChanged) {
        items = changes.map((c) => ({ path: c.path, value: c.value }))
      } else {
        items = []
        for (const step of STEPS) {
          if (step.id === 'apply') continue
          for (const field of stepFields(step.id)) {
            const path = concretePath(field)
            const value = desired[path]
            if (value !== undefined && value !== null) items.push({ path, value })
          }
        }
      }
      return toCommandStrings(items)
    },
    [changes, desired, concretePath]
  )

  // Parse and execute a list of command strings (incl. user-edited/custom ones),
  // then save and re-pull.
  const applyCommandStrings = useCallback(
    async (commandStrings) => {
      if (!serial) return { written: 0, failed: [] }
      const writes = []
      const calls = []
      for (const line of commandStrings) {
        const trimmed = String(line).trim()
        if (!trimmed || trimmed.startsWith('#')) continue
        const parsed = parseConsoleCommand(trimmed)
        if (parsed.error) continue
        if (parsed.type === 'write') writes.push({ path: parsed.path, value: parsed.value })
        else if (parsed.type === 'command') calls.push(parsed)
      }
      const failed = []
      if (writes.length) {
        const results = await backend.writeProperties(serial, writes)
        failed.push(...(results || []).filter((r) => r.status !== 'ok'))
      }
      for (const c of calls) {
        try {
          await backend.invokeCommand(serial, c.path, c.args)
        } catch (err) {
          failed.push({ path: c.path, error: String(err.message || err) })
        }
      }
      await backend.invokeCommand(serial, 'save_configuration', [])
      await pullConfig()
      return { written: writes.length + calls.length - failed.length, failed }
    },
    [serial, pullConfig]
  )

  return {
    serial,
    fwLine,
    selectedAxis,
    isConnected,
    loading,
    unreadable,
    changes,
    validation,
    pullConfig,
    applyChanges,
    buildCommandStrings,
    applyCommandStrings,
    setValue,
    setValueByPath,
    refreshField,
    fieldState,
    valueOf,
    concretePath,
  }
}
