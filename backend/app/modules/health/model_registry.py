"""Collect ORM model contributions from installed health packages."""

import modules.health.health_targets.model_registry as health_targets_model_registry
import modules.health.health_weight.model_registry as health_weight_model_registry

MODEL_MODULES = (
    *health_targets_model_registry.MODEL_MODULES,
    *health_weight_model_registry.MODEL_MODULES,
)
