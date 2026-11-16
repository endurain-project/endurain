"""Resolve and persist activity locations, off the ingestion path.

Owns *when* an activity's location is resolved and *where* the result is stored.
It deliberately does not own *how* resolution happens: that is the platform's
:class:`~jasil.providers.GeocodingProvider`, which holds the upstream service
knowledge and the egress hardening that calling a third party requires, so this
module builds no provider URL, validates no host, throttles nothing and speaks no
HTTP.

Parsers emit an activity with no ``city``/``town``/``country``; the
``activity.created`` subscriber calls in here to resolve and persist the
location, and the scheduled backfill re-resolves any that were missed. Being a
subscriber (not part of parsing) keeps the parse path free of network I/O and
lets the work run durably/async when durable jobs are enabled.
"""

import uuid
from datetime import datetime, timedelta

from jasil.providers import ClockProvider, GeocodingOutcome, GeocodingProvider
from sqlalchemy.orm import Session

import core.logger as core_logger
import core.pagination as core_pagination
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.integration_service as activity_streams_integration

logger = core_logger.get_logger(__name__)

#: How long an activity whose location did not resolve waits before the backfill
#: looks it up again.
LOOKUP_RETRY_DELAY = timedelta(days=1)

#: The longest a lookup waits for its turn under the geocoding rate limit, which every
#: process sharing the platform state shares. A longer wait sends nothing: the durable
#: handler defers until the provider's retry time and the backfill ends its pass, so a
#: worker is not held queueing behind the limit.
LOOKUP_MAX_WAIT_SECONDS = 5.0


def reverse_geocode(
    geocoding: GeocodingProvider,
    latitude: float | None,
    longitude: float | None,
) -> GeocodingOutcome:
    """Reverse-geocode a ``(lat, lon)`` pair through the platform provider.

    Args:
        geocoding: The platform geocoding provider.
        latitude: Latitude in decimal degrees, or None.
        longitude: Longitude in decimal degrees, or None.

    Returns:
        The provider's outcome: the resolved place (any field may be ``None``);
        a final "nothing here", also when the coordinates are missing or
        geocoding is not configured; or, with ``retry_at`` set, a lookup the rate
        limit or an upstream failure held back. Never raises for an upstream
        failure, so it cannot fail the import or backfill that triggered it.
    """
    if latitude is None or longitude is None:
        return GeocodingOutcome()
    return geocoding.lookup(latitude, longitude, max_wait_seconds=LOOKUP_MAX_WAIT_SECONDS)


def geocode_and_store_activity_location(
    activity_id: uuid.UUID, geocoding: GeocodingProvider, db: Session
) -> datetime | None:
    """Resolve and persist a created activity's location from its GPS stream.

    Loads the activity's first GPS waypoint, reverse-geocodes it, and writes
    ``city``/``town``/``country`` back to the row. No-ops for non-GPS activities
    (no map stream), when nothing resolves, or when the lookup was held back.

    Args:
        activity_id: The activity to geocode.
        geocoding: The platform geocoding provider.
        db: Database session.

    Returns:
        When to look the location up again if the rate limit or an upstream
        failure held the lookup back, else None (stored, nothing resolved, or no
        GPS stream).
    """
    stream = activity_streams_integration.get_stream_for_derivation(
        activity_id,
        activity_streams_constants.STREAM_TYPE_MAP,
        db,
    )
    if stream is None or not stream.stream_waypoints:
        return None

    first_waypoint = stream.stream_waypoints[0]
    # End the read transaction before the network call so no connection is held
    # while the geocoder answers.
    db.commit()
    outcome = reverse_geocode(geocoding, first_waypoint.get("lat"), first_waypoint.get("lon"))
    location = outcome.place
    if location is None:
        return outcome.retry_at

    if activity_integration.set_activity_location(
        activity_id,
        location.locality,
        location.sublocality,
        location.country,
        db,
    ):
        db.commit()
        logger.debug("Stored the resolved activity location", extra=core_logger.context(activity_id=str(activity_id)))
    return None


def backfill_missing_activity_locations(
    geocoding: GeocodingProvider,
    clock: ClockProvider,
    db: Session,
    *,
    max_lookups: int = core_pagination.DEFAULT_EXTERNAL_IO_BATCH_SIZE,
) -> int:
    """Resolve locations for GPS activities that still have none.

    Reconciliation net for the ``activity.created`` geocoding subscriber. It pages
    through the activities with an all-NULL location that are due a lookup and
    fetches each page's GPS waypoints in one batch. Only an activity with a GPS
    stream costs a (rate-limited) geocoding request, so ``max_lookups`` bounds a
    pass's external I/O.

    An activity with no GPS stream, or whose lookup resolves nothing, is deferred
    by :data:`LOOKUP_RETRY_DELAY` rather than retried every pass, so it neither
    occupies the budget nor is given up on. Geocoding that is not configured
    answers "nothing here" too, so the delay is bounded rather than permanent:
    once geocoding works, every deferred activity is reached within one delay.

    A lookup the rate limit or an upstream failure held back ends the pass and
    leaves its activity due, so the pass neither queues behind the limit nor keeps
    calling a failing upstream; the next scheduled run carries on.

    Args:
        geocoding: The platform geocoding provider.
        clock: The platform clock, for the due time and the retry time.
        db: Database session.
        max_lookups: Maximum reverse-geocoding requests this pass may make; the
            remainder is picked up on the next scheduled run.

    Returns:
        The number of activities whose location was resolved and stored.
    """
    now = clock.now()
    retry_at = now + LOOKUP_RETRY_DELAY
    stored = 0
    lookups = 0
    deferred = 0
    held_back = False
    after_id: uuid.UUID | None = None
    while lookups < max_lookups and not held_back:
        candidates = activity_integration.list_activities_missing_location(db, due_at=now, after_id=after_id)
        if not candidates:
            break
        after_id = candidates[-1].id

        waypoints_by_activity = activity_streams_integration.get_gps_waypoints_for_activities(
            [ref.id for ref in candidates], db
        )
        unresolved = [ref.id for ref in candidates if not waypoints_by_activity.get(ref.id)]
        # The lookups below are network calls; do not hold the read transaction.
        db.commit()
        for ref in candidates:
            waypoints = waypoints_by_activity.get(ref.id)
            if not waypoints:
                continue
            if lookups >= max_lookups:
                # Not looked up, so not deferred: still due on the next pass.
                break
            lookups += 1
            first_waypoint = waypoints[0]
            outcome = reverse_geocode(geocoding, first_waypoint.get("lat"), first_waypoint.get("lon"))
            if outcome.retry_at is not None:
                # No final answer, so not deferred: still due on the next pass.
                held_back = True
                break
            location = outcome.place
            if location is None or not (location.locality or location.sublocality or location.country):
                unresolved.append(ref.id)
                continue
            if activity_integration.set_activity_location(
                ref.id,
                location.locality,
                location.sublocality,
                location.country,
                db,
            ):
                db.commit()
                stored += 1

        if unresolved:
            activity_integration.defer_location_lookups(unresolved, retry_at, db)
            db.commit()
            deferred += len(unresolved)

    extra = core_logger.context(stored=stored, lookups=lookups, deferred=deferred, held_back=held_back)
    if stored:
        logger.info("Geocoding scheduler pass complete", extra=extra)
    else:
        logger.debug("Geocoding scheduler pass complete", extra=extra)
    return stored
