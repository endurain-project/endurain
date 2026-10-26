"""Request-parameter types for the profile routes."""

from typing import Annotated

from fastapi import Depends

import core.dependencies as core_dependencies
import modules.users.users_profile.export_state_store as profile_export_state_store
import modules.users.users_profile.import_state_store as profile_import_state_store


def get_profile_import_state_store(
    state: core_dependencies.PlatformState,
) -> profile_import_state_store.ProfileImportStateStore:
    """Return the import state store over the platform state provider.

    Args:
        state: The platform state provider.

    Returns:
        The import state store.
    """
    return profile_import_state_store.ProfileImportStateStore(state)


ProfileImportStateStoreDep = Annotated[
    profile_import_state_store.ProfileImportStateStore, Depends(get_profile_import_state_store)
]


def get_profile_export_state_store(
    state: core_dependencies.PlatformState,
) -> profile_export_state_store.ProfileExportStateStore:
    """Return the export state store over the platform state provider.

    Args:
        state: The platform state provider.

    Returns:
        The export state store.
    """
    return profile_export_state_store.ProfileExportStateStore(state)


ProfileExportStateStoreDep = Annotated[
    profile_export_state_store.ProfileExportStateStore, Depends(get_profile_export_state_store)
]
