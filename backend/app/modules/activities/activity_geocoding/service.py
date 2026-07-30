"""Resolve and persist activity locations, off the ingestion path.

Owns *when* an activity's location is resolved and *where* the result is stored.
It deliberately does not own *how* resolution happens: that is the platform's
:class:`~infra.providers.GeocodingProvider`, which holds the upstream service
knowledge and the egress hardening that calling a third party requires. Before
that split this module built provider URLs, validated the configured host against
SSRF, throttled, and spoke HTTP — none of which is a fact about activities.

Parsers emit an activity with no ``city``/``town``/``country``; the
``activity.created`` subscriber calls in here to resolve and persist the
location, and the scheduled backfill re-resolves any that were missed. Being a
subscriber (not part of parsing) keeps the parse path free of network I/O and
lets the work run durably/async when durable jobs are enabled.
"""

import logging

from sqlalchemy.orm import Session

import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity.crud as activities_crud
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.crud as activity_streams_crud
from infra.providers import GeocodedPlace

logger = core_logger.get_logger(__name__)


def reverse_geocode(latitude: float | None, longitude: float | None) -> GeocodedPlace | None:
    """Reverse-geocode a ``(lat, lon)`` pair through the platform provider.

    Args:
        latitude: Latitude in decimal degrees, or None.
        longitude: Longitude in decimal degrees, or None.

    Returns:
        The resolved place (any field may be ``None``), or ``None`` when the
        coordinates are missing, geocoding is not configured, or nothing
        resolved. Never raises: the provider contract requires an upstream
        failure to surface as ``None``, so it cannot fail the import or backfill
        that triggered it.
    """
    if latitude is None or longitude is None:
        return None
    return platform_runtime.get_active_platform().geocoding.reverse(latitude, longitude)


def geocode_and_store_activity_location(activity_id: int, user_id: int, db: Session) -> bool:
    """Resolve and persist a created activity's location from its GPS stream.

    Loads the activity's first GPS waypoint, reverse-geocodes it, and writes
    ``city``/``town``/``country`` back to the row. No-ops for non-GPS activities
    (no map stream) or when nothing resolves.

    Args:
        activity_id: The activity to geocode.
        user_id: The owning user (used to load the activity's own map stream).
        db: Database session.

    Returns:
        True when a location was resolved and stored, else False.
    """
    stream = activity_streams_crud.get_activity_stream_by_type(
        activity_id,
        activity_streams_constants.STREAM_TYPE_MAP,
        user_id,
        db,
    )
    if stream is None or not stream.stream_waypoints:
        return False

    first_waypoint = stream.stream_waypoints[0]
    location = reverse_geocode(first_waypoint.get("lat"), first_waypoint.get("lon"))
    if location is None:
        return False

    activities_crud.update_activity_location(
        activity_id,
        location.city,
        location.town,
        location.country,
        db,
    )
    logger.debug(f"Stored location for activity {activity_id}: {location.city} / {location.town} / {location.country}")
    return True


def backfill_missing_activity_locations(db: Session) -> int:
    """Resolve locations for GPS activities that still have none.

    Reconciliation net for the ``activity.created`` geocoding subscriber: it lists
    activities with an all-NULL location (bounded per pass), fetches their GPS
    waypoints in one batch, and reverse-geocodes each. Activities without a GPS
    stream are skipped.

    Args:
        db: Database session.

    Returns:
        The number of activities whose location was resolved and stored.
    """
    candidates = activities_crud.get_activities_missing_location(db)
    if not candidates:
        logger.debug("Geocoding scheduler: no activities missing location")
        return 0

    candidate_ids = [ref.id for ref in candidates]
    waypoints_by_activity = activity_streams_crud.get_gps_stream_waypoints_for_activities(candidate_ids, db)

    stored = 0
    for activity_id, waypoints in waypoints_by_activity.items():
        if not waypoints:
            continue
        first_waypoint = waypoints[0]
        location = reverse_geocode(first_waypoint.get("lat"), first_waypoint.get("lon"))
        if location is None:
            continue
        activities_crud.update_activity_location(
            activity_id,
            location.city,
            location.town,
            location.country,
            db,
        )
        stored += 1

    logger.log(
        logging.INFO if stored else logging.DEBUG,
        f"Geocoding scheduler: stored location for {stored} activity(ies) "
        f"out of {len(waypoints_by_activity)} GPS candidate(s)",
    )
    return stored
