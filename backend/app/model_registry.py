"""Application composition for SQLAlchemy model registration."""

import pathlib
from importlib import import_module

import modules.activities.model_registry as activities_models
import modules.followers.model_registry as follower_models

_APP_ROOT = pathlib.Path(__file__).resolve().parent
_MODULES_ROOT = _APP_ROOT / "modules"

_CONVERTED_MODEL_MODULES = frozenset((*activities_models.MODEL_MODULES, *follower_models.MODEL_MODULES))


def _legacy_model_modules() -> tuple[str, ...]:
    """Return model modules whose bounded context has not been converted yet."""
    discovered = (
        ".".join(path.relative_to(_APP_ROOT).with_suffix("").parts) for path in _MODULES_ROOT.rglob("models.py")
    )
    return tuple(sorted(module for module in discovered if module not in _CONVERTED_MODEL_MODULES))


def import_all_models() -> None:
    """Import explicit converted contributions plus legacy module models."""
    for module in (*sorted(_CONVERTED_MODEL_MODULES), *_legacy_model_modules()):
        import_module(module)
