"""The Strava operations exposed only to data migrations."""

import jasil.providers as platform_providers
from stravalib.client import Client

import modules.strava.activity_service as strava_activity_service
import modules.strava.client_service as strava_client_service
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.users.users_integrations.schema as user_integrations_schema

fetch_user_integrations_and_validate_token = strava_client_service.fetch_user_integrations_and_validate_token
create_strava_client = strava_client_service.create_strava_client


def fetch_activity_laps(
    strava_client: Client,
    strava_activity_id: int,
    user_id: int,
    stream_data: list[strava_activity_service.StravaStreamEntry],
    user_integrations: user_integrations_schema.UserIntegrationsRead,
    state: platform_providers.StateProvider,
) -> list[strava_activity_service.StravaLap] | None:
    """Fetch and convert the laps Strava holds for an activity.

    Args:
        strava_client: A client authenticated as the user.
        strava_activity_id: The activity's Strava id.
        user_id: The activity's owner.
        stream_data: ``(is_set, stream_type, waypoints)`` tuples used to derive lap metrics.
        user_integrations: The owner's integration settings.
        state: The platform state provider holding the shared rate-limit state.

    Returns:
        The converted laps, or ``None`` when Strava has none for the activity.
    """
    return strava_activity_service.fetch_and_process_activity_laps(
        strava_client,
        strava_activity_id,
        user_id,
        stream_data,
        user_integrations,
        strava_rate_limit_store.StravaRateLimitStore(state),
    )
