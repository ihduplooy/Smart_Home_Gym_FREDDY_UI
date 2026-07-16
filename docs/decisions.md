# Decisions log — what was stripped/changed from upstream and why

Per spec §8: 0.5.1-incompatibilities found during the trim are logged here rather than
deeply investigated without hardware. This file is append-only during Session 1;
newest entries at the bottom.

## Path discrepancy (pre-work note)

- Spec §"Working directory" refers to the 1B script as `Developer/odrive_config_1B.py`.
  The actual file on disk is `Phase 1/odrive_config_1B.py` — there is no `Developer/`
  subfolder anywhere in the project. Treated as the same file (only one 1B script
  exists, contents match spec's description exactly: hoverboard motor, 15 pole pairs,
  AS5047P SPI CS pin 7). No action needed beyond noting it here.
