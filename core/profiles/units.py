"""Force <-> torque conversion via cable spool radius.

The ONLY place a spool radius is consumed for this conversion (spec §4).
Resistance profiles think in cable-force Newtons at their public parameter
surface (the user-meaningful unit); this is the one boundary where that
becomes motor torque Nm.

`r0` defaults to `config.board_constants.SPOOL_RADIUS_M` -- the only radius
Session 3's Profiles tab ever has, since it runs with no cable attached and
therefore no `CableState`. Exercise/Force (Layer A/B) callers pass
`cable_state.r0` explicitly instead: spool radius became a live-adjustable,
persisted CableState setting (23 July 2026, requested after the first
live-hardware session), so the one conversion site needs to be able to use
that calibrated value rather than always falling back to the static
board_constants placeholder.
"""

from typing import Optional

from config import board_constants


def force_to_torque(force_n: float, r0: Optional[float] = None) -> float:
    return force_n * (r0 if r0 is not None else board_constants.SPOOL_RADIUS_M)


def torque_to_force(torque_nm: float, r0: Optional[float] = None) -> float:
    return torque_nm / (r0 if r0 is not None else board_constants.SPOOL_RADIUS_M)
