"""Collect ORM model contributions from the users packages."""

import modules.users.users.model_registry as users_model_registry
import modules.users.users_default_gear.model_registry as users_default_gear_model_registry
import modules.users.users_goals.model_registry as users_goals_model_registry
import modules.users.users_integrations.model_registry as users_integrations_model_registry
import modules.users.users_privacy_settings.model_registry as users_privacy_settings_model_registry

MODEL_MODULES = (
    *users_model_registry.MODEL_MODULES,
    *users_default_gear_model_registry.MODEL_MODULES,
    *users_goals_model_registry.MODEL_MODULES,
    *users_integrations_model_registry.MODEL_MODULES,
    *users_privacy_settings_model_registry.MODEL_MODULES,
)
