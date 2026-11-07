"""FastAPI dependencies for the Strava routes."""

from typing import Annotated

from fastapi import Depends

import core.dependencies as core_dependencies
import modules.strava.oauth_state_store as strava_oauth_state_store
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.strava.sync_state_store as strava_sync_state_store


def get_strava_oauth_state_store(
    state: core_dependencies.PlatformState,
) -> strava_oauth_state_store.StravaOAuthStateStore:
    """Return the OAuth state store over the platform state provider.

    Args:
        state: The platform state provider.

    Returns:
        The OAuth state store.
    """
    return strava_oauth_state_store.StravaOAuthStateStore(state)


def get_strava_sync_state_store(
    state: core_dependencies.PlatformState,
) -> strava_sync_state_store.StravaSyncStateStore:
    """Return the sync state store over the platform state provider.

    Args:
        state: The platform state provider.

    Returns:
        The sync state store.
    """
    return strava_sync_state_store.StravaSyncStateStore(state)


def get_strava_rate_limit_store(
    state: core_dependencies.PlatformState,
) -> strava_rate_limit_store.StravaRateLimitStore:
    """Return the rate-limit store over the platform state provider.

    Args:
        state: The platform state provider.

    Returns:
        The rate-limit store.
    """
    return strava_rate_limit_store.StravaRateLimitStore(state)


StravaOAuthStateStoreDep = Annotated[
    strava_oauth_state_store.StravaOAuthStateStore, Depends(get_strava_oauth_state_store)
]
StravaSyncStateStoreDep = Annotated[strava_sync_state_store.StravaSyncStateStore, Depends(get_strava_sync_state_store)]
StravaRateLimitStoreDep = Annotated[strava_rate_limit_store.StravaRateLimitStore, Depends(get_strava_rate_limit_store)]
