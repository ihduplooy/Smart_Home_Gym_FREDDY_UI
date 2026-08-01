"""Name -> Experiment class, mirrors core/profiles/__init__.py::PROFILE_REGISTRY's
role for /api/profiles. Each entry takes `cable_state` as its sole constructor
arg (same contract every future experiment follows) -- unlike PROFILE_REGISTRY's
zero-arg factories, since every experiment needs the shared calibration state
(is_homed/has_max/spool_geometry) to validate its own config."""

from .static_hold import StaticWeightHoldExperiment

EXPERIMENT_REGISTRY = {
    "static_hold": StaticWeightHoldExperiment,
}

__all__ = ["EXPERIMENT_REGISTRY"]
