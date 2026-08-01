# smart-gym-control — Directory Index

Regenerated 2026-07-28 (previous version generated 2026-07-21, since gone
stale — Train tab added, Exercise/Dashboard/Presets/Profiles tabs removed).
Excludes `.git`, `.venv`, `node_modules`, `__pycache__`, `.pytest_cache`,
`.DS_Store`, and the gitignored `logs/`/`frontend/dist/` build/runtime
output (see the note at the bottom).

```
smart-gym-control/
├── README.md
├── INDEX.md
├── requirements-dev.txt
├── Start Freddy.command
├── Stop Freddy.command
│
├── backend/
│   ├── requirements.txt
│   ├── start_backend.py
│   └── app/
│       ├── app.py
│       ├── api_reference.py
│       ├── constants.py
│       ├── control_routes.py
│       ├── exercise_routes.py
│       ├── force_routes.py
│       ├── train_routes.py
│       ├── device_manager.py
│       ├── mock_odrive.py
│       ├── telemetry.py
│       ├── routes/
│       │   └── __init__.py
│       └── utils/
│           └── __init__.py
│
├── config/
│   ├── board_constants.py
│   ├── odrive_config.py
│   ├── diagnose_encoder_spi.py
│   ├── odrive_diag_common.py
│   └── spool_calibration.json
│
├── core/
│   ├── README.md
│   ├── __init__.py
│   ├── cable/
│   │   ├── __init__.py
│   │   ├── state.py            # CableState — the persisted settings singleton
│   │   ├── exercise_mode.py    # ExerciseMode (Layer A positioning/safety +
│   │   │                       # Layer B force feedback, merged)
│   │   ├── train_mode.py       # TrainMode
│   │   ├── train_profiles.py   # TrainSegment/TrainProfile (constant/linear/bell)
│   │   ├── geometry.py
│   │   ├── homing.py
│   │   ├── letgo.py
│   │   ├── limits.py
│   │   ├── governor.py
│   │   ├── power_limiter.py
│   │   └── ramps.py
│   ├── control/
│   │   ├── __init__.py
│   │   ├── modes.py             # MODES_BY_NAME: velocity/torque/position/profile
│   │   └── session.py           # ControlSession orchestrator
│   ├── hardware/
│   │   ├── __init__.py
│   │   ├── _macos_usb.py
│   │   ├── interface.py
│   │   ├── odrive_hw.py
│   │   └── sim_hw.py
│   ├── profiles/                # Session 3 resistance-profile system —
│   │   │                        # still implemented/tested, currently has
│   │   │                        # no frontend tab (see README/decisions.md)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── bell_curve.py
│   │   ├── constant.py
│   │   ├── detectors.py
│   │   ├── overload.py
│   │   ├── units.py
│   │   └── vbt.py
│   ├── telemetry/
│   │   ├── __init__.py
│   │   └── csv_logger.py
│   └── tests/                   # 26 test files — pytest core/tests
│       ├── conftest.py
│       ├── test_cable_state.py
│       ├── test_control_session.py
│       ├── test_csv_logger.py
│       ├── test_detectors.py
│       ├── test_exercise_mode.py
│       ├── test_geometry.py
│       ├── test_governor.py
│       ├── test_homing.py
│       ├── test_interface_contract.py
│       ├── test_letgo.py
│       ├── test_limits.py
│       ├── test_modes.py
│       ├── test_power_limiter.py
│       ├── test_profile_mode.py
│       ├── test_profiles.py
│       ├── test_ramps.py
│       ├── test_sim_hw.py
│       ├── test_train_mode.py
│       └── test_train_profiles.py
│
├── docs/
│   ├── decisions.md    # what/why, append-only, newest at the bottom
│   ├── progress.md     # build-session checklist, append-only
│   ├── user_manual.md  # end-user "how do I use it" guide
│   └── manual.html     # styled HTML mirror of user_manual.md
│
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── eslint.config.js
│   ├── jsconfig.json
│   ├── vite.config.js
│   ├── index.html
│   ├── public/
│   │   └── servo.ico
│   └── src/
│       ├── App.jsx              # top bar: connection status, Restart Freddy
│       ├── App.css
│       ├── index.css
│       ├── main.jsx
│       ├── api/
│       │   ├── backend.js
│       │   ├── control.js
│       │   ├── deviceSocket.js
│       │   ├── exercise.js      # still used (status polling + homing/
│       │   │                    # calibration, called from Train's Settings
│       │   │                    # section and the sidebar's Go Home button)
│       │   ├── force.js         # orphaned — no component imports this
│       │   │                    # anymore; force-feedback backend has no UI
│       │   └── train.js
│       ├── assets/
│       │   └── react.svg
│       ├── components/
│       │   ├── CommandList.jsx
│       │   ├── DeviceList.jsx   # persistent sidebar: connect/scan/reset,
│       │   │                    # EMERGENCY STOP, Go Home
│       │   ├── MainTabs.jsx     # 4 tabs: Configuration/Control/Train/Inspector
│       │   ├── MotorControls.jsx
│       │   ├── MotorControlsCard.jsx
│       │   ├── config-parameter-fields/
│       │   │   ├── AdvancedSettingsSection.jsx
│       │   │   ├── ParameterField.jsx
│       │   │   ├── ParameterFormGrid.jsx
│       │   │   ├── ParameterInput.jsx
│       │   │   ├── ParameterSelect.jsx
│       │   │   └── ParameterSwitch.jsx
│       │   ├── config-steps/
│       │   │   ├── ApplyConfigStep.jsx
│       │   │   ├── ConfigStep.jsx
│       │   │   ├── ControlConfigStep.jsx
│       │   │   └── MotorConfigStep.jsx
│       │   ├── modals/
│       │   │   ├── CalibrationModal.jsx
│       │   │   ├── ConfirmationModal.jsx
│       │   │   ├── EraseConfigModal.jsx
│       │   │   └── ErrorTroubleshootingModal.jsx
│       │   └── tabs/
│       │       ├── command console/
│       │       │   └── CommandConsoleTab.jsx
│       │       ├── config wizard/
│       │       │   └── ConfigurationTab.jsx
│       │       ├── control/
│       │       │   ├── ControlTab.jsx    # velocity/torque/position, turns/m toggle
│       │       │   └── MiniChart.jsx
│       │       ├── inspector/
│       │       │   ├── InspectorTab.jsx
│       │       │   ├── LiveCharts.jsx
│       │       │   └── property-tree/
│       │       │       ├── PropertyItem.jsx
│       │       │       └── PropertyTree.jsx
│       │       └── train/
│       │           ├── TrainTab.jsx
│       │           ├── TrainSettingsSection.jsx   # homing/max-ext/spool calib
│       │           ├── TrainProfileEditor.jsx     # segments + save/load
│       │           ├── TrainTimeSeriesChart.jsx
│       │           ├── TrainPositionChart.jsx
│       │           └── AxisRangeControl.jsx
│       ├── hooks/
│       │   ├── useApiPropertyTree.js
│       │   ├── useCalibration.js
│       │   ├── useConfigWizard.js
│       │   ├── useControlTelemetry.js
│       │   ├── useDeviceTelemetry.js
│       │   ├── useMotorControl.js
│       │   └── useTrainTelemetry.js
│       ├── store/
│       │   ├── index.js
│       │   └── slices/
│       │       ├── deviceSlice.js
│       │       ├── liveSlice.js
│       │       ├── telemetrySlice.js
│       │       └── uiSlice.js
│       ├── styles/
│       │   ├── ConfigurationTab.css
│       │   ├── DeviceList.css
│       │   └── InspectorTab.css
│       └── utils/
│           ├── apiReference.js
│           ├── boardDefaults.js
│           ├── cableGeometry.js   # shared by Train + Control (turns<->metres)
│           ├── chartDisplay.js    # axis range/domain helpers (Train graphs)
│           ├── commandLibrary.js
│           ├── configDiff.js
│           ├── configEnums.js
│           ├── configSchema.js
│           ├── configValidation.js
│           ├── consoleCommand.js
│           ├── odriveApiReference05x.json
│           ├── odriveApiReference06x.json
│           ├── odriveErrors.js
│           ├── odriveRegistry.js
│           ├── trainProfilesManager.js   # localStorage save/load of named
│           │                            # Train profiles
│           ├── troubleshooting.js
│           ├── helpers/
│           │   ├── unitConversions.js
│           │   └── valueHelpers.js
│           ├── presets/                  # kept for the Configuration wizard's
│           │   │                        # factory preset only — no Presets tab
│           │   ├── factoryPresets.js
│           │   ├── presetsManager.js
│           │   └── presetsOperations.js
│           ├── property-tree/
│           │   └── propertyTreeFavourites.js
│           └── __tests__/
│               ├── apiReference.test.js
│               ├── configDiff.test.js
│               ├── configValidation.test.js
│               ├── consoleCommand.test.js
│               ├── helpers.test.js
│               ├── integration.live.test.js
│               ├── odriveRegistry.test.js
│               ├── presetsManager.test.js
│               └── trainProfilesManager.test.js
│
├── logs/                  # gitignored — 970 CSV telemetry logs as of this
│                          # writing (sim + real runs, 2026-07-17 – 2026-07-27),
│                          # plus backend/frontend .log files from the Freddy
│                          # launcher scripts
└── frontend/dist/         # gitignored — `vite build` output, present locally
                            # from a past build; not part of the source tree
```

## Top-level summary

| Path | Purpose |
|---|---|
| `backend/` | Flask app — device control, telemetry, ODrive interface routes (control/exercise/force/train) |
| `config/` | ODrive board configuration, board constants, and encoder diagnostic scripts |
| `core/` | Control logic — modes, hardware abstraction, cable/exercise/train modes, resistance profiles, telemetry logging, test suite |
| `docs/` | Decisions log, progress notes, user manual (markdown + HTML) |
| `frontend/` | React + Vite UI — Configuration, Control, Train, Inspector tabs |
| `logs/` | CSV telemetry + launcher logs (gitignored, not part of source) |
| `README.md` | Project overview |
| `INDEX.md` | This file |
| `requirements-dev.txt` | Dev-only Python dependencies |
| `Start Freddy.command` / `Stop Freddy.command` | One-click launcher/stopper for real-hardware mode (double-click in Finder) |

## Current tab structure (frontend)

As of 28 July 2026 the app has **four** tabs (`MainTabs.jsx`), down from the
eight described in older docs:

1. **Configuration** — config wizard, writes board settings to a connected device.
2. **Control** — raw velocity/torque/position control, no cable awareness required.
3. **Train** — the primary day-to-day tab: homing, max-extension and spool
   calibration (Settings/Startup section), position-based resistance
   profiles (segments: constant/linear/bell, with save/load), and the two
   live graphs.
4. **Inspector** — raw ODrive property tree.

`ExerciseTab.jsx`, `DashboardTab.jsx`, `PresetsTab.jsx`, and `ProfilesTab.jsx`
have been deleted. The backend routes/logic they used
(`exercise_routes.py`, `force_routes.py`, `core/cable/exercise_mode.py`'s
force-feedback state machine, `core/profiles/`) are all still present and
tested but currently have **no frontend surface** — see
`docs/decisions.md` ("Frontend consolidation to four tabs") for the open
question this raises.
