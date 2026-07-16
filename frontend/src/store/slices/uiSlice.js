import { createSlice } from '@reduxjs/toolkit'

// selectedAxis is always 0: this board only ever drives axis0 (axis1 is a ghost
// node from Phase 2B). No UI sets it; it's kept as a constant so the many hooks
// that thread an "axis" value through (useMotorControl, useConfigWizard, etc.)
// don't need a separate code path for the single-axis case.
const initialState = {
  selectedAxis: 0,
  activeTab: 0,
}

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    setActiveTab(state, action) {
      state.activeTab = action.payload
    },
  },
})

export const { setActiveTab } = uiSlice.actions

export default uiSlice.reducer