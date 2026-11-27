"""Collect ORM model contributions from the gears packages."""

import modules.gears.gear.model_registry as gear_model_registry
import modules.gears.gear_components.model_registry as gear_components_model_registry

MODEL_MODULES = (
    *gear_model_registry.MODEL_MODULES,
    *gear_components_model_registry.MODEL_MODULES,
)
