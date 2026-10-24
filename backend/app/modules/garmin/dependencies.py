"""FastAPI dependencies for the Garmin Connect routes."""

from typing import Annotated

from fastapi import Depends

import core.dependencies as core_dependencies
import modules.garmin.link_state_store as garmin_link_state_store
import modules.garmin.mfa_code_store as garmin_mfa_code_store
import modules.garmin.sync_state_store as garmin_sync_state_store


def get_garmin_mfa_code_store(
    state: core_dependencies.PlatformState,
) -> garmin_mfa_code_store.GarminMFACodeStore:
    """Return the MFA code store over the platform state provider.

    Args:
        state: The platform state provider.

    Returns:
        The MFA code store.
    """
    return garmin_mfa_code_store.GarminMFACodeStore(state)


def get_garmin_link_state_store(
    state: core_dependencies.PlatformState,
) -> garmin_link_state_store.GarminLinkStateStore:
    """Return the link state store over the platform state provider.

    Args:
        state: The platform state provider.

    Returns:
        The link state store.
    """
    return garmin_link_state_store.GarminLinkStateStore(state)


def get_garmin_sync_state_store(
    state: core_dependencies.PlatformState,
) -> garmin_sync_state_store.GarminSyncStateStore:
    """Return the sync state store over the platform state provider.

    Args:
        state: The platform state provider.

    Returns:
        The sync state store.
    """
    return garmin_sync_state_store.GarminSyncStateStore(state)


GarminMFACodeStoreDep = Annotated[garmin_mfa_code_store.GarminMFACodeStore, Depends(get_garmin_mfa_code_store)]
GarminLinkStateStoreDep = Annotated[garmin_link_state_store.GarminLinkStateStore, Depends(get_garmin_link_state_store)]
GarminSyncStateStoreDep = Annotated[garmin_sync_state_store.GarminSyncStateStore, Depends(get_garmin_sync_state_store)]
