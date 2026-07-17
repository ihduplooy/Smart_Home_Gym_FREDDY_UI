"""Force <-> torque conversion via cable spool radius.

The ONLY place `config.board_constants.SPOOL_RADIUS_M` is consumed (spec §4).
Resistance profiles think in cable-force Newtons at their public parameter
surface (the user-meaningful unit); this is the one boundary where that
becomes motor torque Nm.
"""

from config import board_constants


def force_to_torque(force_n: float) -> float:
    return force_n * board_constants.SPOOL_RADIUS_M


def torque_to_force(torque_nm: float) -> float:
    return torque_nm / board_constants.SPOOL_RADIUS_M
