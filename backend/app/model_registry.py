"""Application composition for SQLAlchemy model registration."""

from importlib import import_module

import modules.activities.model_registry as activities_model_registry
import modules.auth.model_registry as auth_model_registry
import modules.followers.model_registry as follower_models
import modules.gears.model_registry as gears_model_registry
import modules.health.model_registry as health_model_registry
import modules.notifications.model_registry as notifications_model_registry
import modules.server_settings.model_registry as server_settings_model_registry
import modules.users.model_registry as users_model_registry

_CONVERTED_MODEL_MODULES = frozenset(
    (
        *activities_model_registry.MODEL_MODULES,
        *auth_model_registry.MODEL_MODULES,
        *follower_models.MODEL_MODULES,
        *gears_model_registry.MODEL_MODULES,
        *health_model_registry.MODEL_MODULES,
        *notifications_model_registry.MODEL_MODULES,
        *server_settings_model_registry.MODEL_MODULES,
        *users_model_registry.MODEL_MODULES,
    )
)


def import_all_models() -> None:
    """Import the explicit ORM model contributions from installed modules."""
    for module in sorted(_CONVERTED_MODEL_MODULES):
        import_module(module)
