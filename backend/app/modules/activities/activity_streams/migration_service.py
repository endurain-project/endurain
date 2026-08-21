"""Version-pinned stream operations exposed only to data migrations."""

import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.hr_zones as activity_streams_hr_zones

get_activity_streams = activity_streams_crud.get_activity_streams
get_activity_stream_by_type = activity_streams_crud.get_activity_stream_by_type
get_hr_streams_without_zone_percentages = activity_streams_crud.get_hr_streams_without_zone_percentages
backfill_zone_percentages_for_missing_hr_streams = (
    activity_streams_crud.backfill_zone_percentages_for_missing_hr_streams
)
compute_hr_zone_breakdown_sync = activity_streams_hr_zones.compute_hr_zone_breakdown_sync


def resolve_max_heart_rate(user) -> int | None:
    """Resolve an athlete's max heart rate from the user row a migration holds.

    Pinned to the era's signature: migration 7 walks user rows, so it passes the
    row itself. The computation now takes the three fields it actually reads, so
    the unpacking lives here rather than making the streams package depend on the
    users wire type.

    Args:
        user: A user row or DTO exposing ``max_heart_rate``, ``birthdate`` and
            ``timezone``.

    Returns:
        The resolved max heart rate, or None when it cannot be derived.
    """
    return activity_streams_hr_zones.resolve_max_heart_rate(user.max_heart_rate, user.birthdate, user.timezone)
