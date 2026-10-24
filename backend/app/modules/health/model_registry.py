"""Collect ORM model contributions from installed health packages."""

import modules.health.health_fasting.model_registry as health_fasting_model_registry
import modules.health.health_poop.model_registry as health_poop_model_registry
import modules.health.health_sleep.model_registry as health_sleep_model_registry
import modules.health.health_steps.model_registry as health_steps_model_registry
import modules.health.health_targets.model_registry as health_targets_model_registry
import modules.health.health_water.model_registry as health_water_model_registry
import modules.health.health_weight.model_registry as health_weight_model_registry

MODEL_MODULES = (
    *health_fasting_model_registry.MODEL_MODULES,
    *health_poop_model_registry.MODEL_MODULES,
    *health_sleep_model_registry.MODEL_MODULES,
    *health_steps_model_registry.MODEL_MODULES,
    *health_targets_model_registry.MODEL_MODULES,
    *health_water_model_registry.MODEL_MODULES,
    *health_weight_model_registry.MODEL_MODULES,
)
