"""The activities surface consumed by other modules (Strava, Garmin, gears, account deletion).

A curated set of lookups, re-gearing, aggregation, bulk-delete and derived-artifact
maintenance operations; every function returns schemas or DTOs, never an ORM row.
Writes that publish events (bulk deletes, bulk re-gearing, ingestion) delegate to
``activity.service``, which owns their transaction.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

import core.pagination as core_pagination
import modules.activities.activity.child_access_service as activity_child_access_service
import modules.activities.activity.child_collection_service as activity_child_collection_service
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.ingestion_service as activity_ingestion_service
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service

ChildCollection = activity_child_collection_service.ChildCollection


def get_activity_by_strava_id(
    strava_activity_id: int,
    user_id: int,
    db: Session,
) -> activity_schema.ActivityRead | None:
    """Return the user's activity imported from the given Strava activity id.

    Args:
        strava_activity_id: The Strava provider activity id.
        user_id: The owning user id.
        db: Database session.

    Returns:
        The matching activity, or ``None`` when the user has no such import.
    """
    return activity_crud.get_activity_by_strava_id_from_user_id(strava_activity_id, user_id, db)


def get_activity_by_garminconnect_id(
    garminconnect_activity_id: int,
    user_id: int,
    db: Session,
) -> activity_schema.ActivityRead | None:
    """Return the user's activity imported from the given Garmin Connect activity id.

    Args:
        garminconnect_activity_id: The Garmin Connect provider activity id.
        user_id: The owning user id.
        db: Database session.

    Returns:
        The matching activity, or ``None`` when the user has no such import.
    """
    return activity_crud.get_activity_by_garminconnect_id_from_user_id(garminconnect_activity_id, user_id, db)


def list_user_activities(user_id: int, db: Session) -> list[activity_schema.ActivityRead]:
    """Return all of a user's activities (used by provider gear reconciliation).

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The user's activities (empty when they have none).
    """
    return activity_crud.get_user_activities(user_id, db, user_is_owner=True)


def list_user_activities_with_garminconnect_gear(
    user_id: int,
    db: Session,
) -> list[activity_schema.ActivityRead]:
    """Return a user's activities that carry a Garmin Connect gear id.

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The matching activities, or ``None`` when there are none.
    """
    return activity_crud.get_user_activities_by_user_id_and_garminconnect_gear_set(user_id, db)


def bulk_set_activities_gear(
    user_id: int,
    gear_assignments: dict[int, int | None],
    db: Session,
) -> int:
    """Assign gear to many of a user's activities at once.

    Stages the change and its events; the caller commits.

    Args:
        user_id: The owning user id (ownership is enforced by the update).
        gear_assignments: Map of activity id -> gear id (or ``None`` to clear).
        db: Database session.

    Returns:
        The number of activities updated.
    """
    return activity_service.bulk_set_activities_gear(
        user_id,
        gear_assignments,
        db,
        source="api:bulk_set_activities_gear",
    )


def get_gear_usage_totals(gear_id: int, user_id: int, db: Session) -> activity_contracts.ActivityUsageTotals:
    """Return the total distance and moving time a user recorded against a gear.

    Args:
        gear_id: The gear to accumulate usage for.
        user_id: The gear's owner; only their activities count.
        db: Database session.

    Returns:
        The gear's totals; zeroes when it has no activities.
    """
    return activity_crud.sum_gear_usage(gear_id, user_id, db)


def get_gear_usage_totals_by_window(
    gear_id: int,
    user_id: int,
    windows: Sequence[activity_contracts.GearUsageWindow],
    db: Session,
) -> dict[int, activity_contracts.ActivityUsageTotals]:
    """Return per-window usage totals for one gear, in a single query.

    Used to attribute a gear's activities to whichever component was fitted at
    the time. Window bounds are calendar dates evaluated in each activity's own
    timezone, which is why this lives in the activities module rather than being
    joined from the gears side.

    Args:
        gear_id: The gear whose activities to accumulate.
        user_id: The gear's owner; only their activities count.
        windows: The date windows to accumulate over, keyed by the caller.
        db: Database session.

    Returns:
        Totals per window key; every requested key is present, zeroed when the
        window matched nothing.
    """
    return activity_crud.sum_gear_usage_by_window(gear_id, user_id, windows, db)


def list_user_activities_page(
    user_id: int,
    db: Session,
    *,
    page_number: int,
    num_records: int,
) -> list[activity_schema.ActivityRead]:
    """Return one page of a user's own activities, newest first.

    The profile export walks a user's whole library in batches; it is always the
    owner reading their own data, so no visibility mask applies.

    Args:
        user_id: The owning user id.
        page_number: 1-based page number.
        num_records: Page size.
        db: Database session.

    Returns:
        The page of activities, empty when the page is past the end.
    """
    return activity_crud.get_user_activities_with_pagination(
        user_id=user_id,
        db=db,
        page_number=page_number,
        num_records=num_records,
        # Newest first, so an export produced in batches stays in a stable order.
        sort_by="start_time",
        sort_order="desc",
        user_is_owner=True,
    )


def list_user_activities_in_timeframe_by_types(
    user_id: int,
    activity_types: list[int],
    start: datetime,
    end: datetime,
    db: Session,
    *,
    exclude_hidden: bool = True,
) -> list[activity_schema.ActivityRead]:
    """Return a user's own activities of the given types within a window.

    Used by goal progress. Hidden activities are excluded by default so a
    duplicate import from a second source cannot count twice towards a goal.

    Args:
        user_id: The owning user id.
        activity_types: Sport type codes to include.
        start: Inclusive start of the window.
        end: Inclusive end of the window.
        db: Database session.
        exclude_hidden: Whether to skip activities marked hidden.

    Returns:
        The matching activities, empty when there are none.
    """
    return activity_crud.get_user_activities_per_timeframe_and_activity_types(
        user_id,
        activity_types,
        start,
        end,
        db,
        user_is_owner=True,
        exclude_hidden=exclude_hidden,
    )


def restore_activity(
    activity: activity_contracts.ActivityCore,
    db: Session,
) -> activity_schema.ActivityRead:
    """Persist an activity from a profile restore **without** publishing events.

    Deliberately not the ``store_parsed_activity`` ingestion seam: a bulk restore
    must not publish ``activity.created`` per row. Doing so would spam the user
    with one "new activity" notification each and, on the in-process bus, render
    every map thumbnail, score HR zones, and reverse-geocode inline inside the
    import loop. The derived artifacts are re-created afterwards by the scheduled
    thumbnail, HR-zone, and geocoding backfills — the reconciliation nets that
    exist for exactly this case.

    The row is staged and flushed, not committed: the importer restores the
    activity's components against the returned id and commits the whole activity
    as one unit.

    Args:
        activity: The activity to persist.
        db: Database session.

    Returns:
        The staged activity, with its generated id.
    """
    return activity_crud.create_activity(activity, db)


def store_parsed_activity(
    parsed: activity_contracts.ParsedActivity,
    db: Session,
) -> activity_schema.ActivityRead:
    """Stage a canonical parsed activity through the ingestion seam.

    The activity, its components and the ``activity.created`` event are staged
    together; the caller commits.

    Args:
        parsed: Parsed root and child data to store.
        db: Database session.

    Returns:
        The stored activity.
    """
    return activity_ingestion_service.store_parsed_activity(parsed, db)


def resolve_readable_parent(
    activity_id: int,
    requester_user_id: int,
    db: Session,
) -> activity_schema.ActivityRead | None:
    """Return the parent activity when an authenticated caller may read it.

    Args:
        activity_id: ID of the activity.
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The parent activity when an authenticated caller may read it.
    """
    return activity_child_access_service.resolve_readable_parent(activity_id, requester_user_id, db)


def resolve_public_parent(activity_id: int, db: Session) -> activity_schema.ActivityRead | None:
    """Return the parent activity when it is publicly shareable.

    Args:
        activity_id: ID of the activity.
        db: Database session.

    Returns:
        The parent activity when it is publicly shareable.
    """
    return activity_child_access_service.resolve_public_parent(activity_id, db)


def owns_activity(activity_id: int, user_id: int, db: Session) -> bool:
    """Return whether a user owns an activity.

    Args:
        activity_id: ID of the activity.
        user_id: ID of the user.
        db: Database session.

    Returns:
        Whether a user owns an activity.
    """
    return activity_service.owns_activity(activity_id, user_id, db)


# Derived-artifact maintenance. The thumbnail and geocoding subsystems reach the
# activity row through these. They are system-level operations with no requester
# to authorize, no event and no invariant beyond the payload, so they go straight
# to CRUD. The writes **stage only**: the caller owns the unit of work and decides
# when it is durable, so one call can never end another module's transaction.


def set_thumbnail_key(activity_id: int, key: str | None, db: Session, *, expected_key: str | None = None) -> bool:
    """Stage recording or clearing an activity's stored thumbnail key.

    The caller commits.

    Args:
        activity_id: ID of the activity.
        key: The new storage key, or None to clear it.
        db: Database session.
        expected_key: When given, write only if the activity still holds this key.

    Returns:
        True when the activity exists (and holds ``expected_key`` when given) and was
        updated, False otherwise.
    """
    return activity_crud.set_activity_thumbnail_key(activity_id, key, db, expected_key=expected_key)


def clear_all_thumbnail_keys(db: Session) -> None:
    """Stage clearing every stored activity thumbnail key.

    The caller commits.

    Args:
        db: Database session.
    """
    activity_crud.clear_all_activity_thumbnail_keys(db)


def list_activities_with_thumbnail(
    db: Session,
    *,
    after_id: int = 0,
    limit: int = core_pagination.DEFAULT_MAINTENANCE_BATCH_SIZE,
) -> list[activity_contracts.ActivityThumbnailRef]:
    """Return one bounded page of activity references carrying a stored thumbnail key.

    Args:
        db: Database session.
        after_id: Return only rows with an ID greater than this.
        limit: Maximum number of rows to return.

    Returns:
        One bounded page of activity references carrying a stored thumbnail key.
    """
    return activity_crud.get_activities_with_thumbnail(db, after_id=after_id, limit=limit)


def list_activities_without_thumbnail(
    db: Session,
    *,
    due_at: datetime,
    after_id: int = 0,
    limit: int = core_pagination.DEFAULT_MAINTENANCE_BATCH_SIZE,
) -> list[activity_contracts.ActivityThumbnailRef]:
    """Return one bounded page of activities with no stored thumbnail key that are due an attempt.

    Args:
        db: Database session.
        due_at: Only activities not deferred past this instant are returned.
        after_id: Return only rows with an ID greater than this.
        limit: Maximum number of rows to return.

    Returns:
        One bounded page of activity references that have no stored thumbnail key.
    """
    return activity_crud.get_activities_without_thumbnail(db, due_at=due_at, after_id=after_id, limit=limit)


def defer_thumbnail_attempts(activity_ids: Sequence[int], retry_at: datetime, db: Session) -> None:
    """Stage when activities that did not get a thumbnail may be tried again.

    The caller commits.

    Args:
        activity_ids: Activities to defer.
        retry_at: Earliest time the backfill may try them again.
        db: Database session.
    """
    activity_crud.defer_thumbnail_attempts(activity_ids, retry_at, db)


def list_activities_missing_location(
    db: Session,
    *,
    due_at: datetime,
    after_id: int = 0,
    limit: int = core_pagination.DEFAULT_EXTERNAL_IO_BATCH_SIZE,
) -> list[activity_contracts.ActivityLocationRef]:
    """Return one id-ordered page of activities whose location is unresolved and due a lookup.

    Args:
        db: Database session.
        due_at: Only activities due at or before this instant are returned.
        after_id: Return only activities with an id greater than this.
        limit: Maximum number of rows to return.

    Returns:
        One page of activity references whose location is unresolved.
    """
    return activity_crud.get_activities_missing_location(db, due_at=due_at, after_id=after_id, limit=limit)


def defer_location_lookups(activity_ids: Sequence[int], retry_at: datetime, db: Session) -> None:
    """Stage when activities whose location did not resolve may be looked up again.

    The caller commits.

    Args:
        activity_ids: Activities to defer.
        retry_at: Earliest time the backfill may look them up again.
        db: Database session.
    """
    activity_crud.defer_location_lookups(activity_ids, retry_at, db)


def set_activity_location(
    activity_id: int,
    city: str | None,
    town: str | None,
    country: str | None,
    db: Session,
) -> bool:
    """Stage a reverse-geocoded activity location.

    The caller commits.

    Args:
        activity_id: ID of the activity.
        city: Resolved city, or None.
        town: Resolved town, or None.
        country: Resolved country, or None.
        db: Database session.

    Returns:
        True when the activity existed and was updated.
    """
    return activity_crud.update_activity_location(activity_id, city, town, country, db)


def delete_all_strava_activities(user_id: int, db: Session) -> int:
    """Delete all of a user's Strava-sourced activities.

    Emits one ``activity.deleted`` per removed activity so the thumbnail and
    source-file cleanup subscribers reclaim the blobs each one owned. The caller
    commits.

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The number of activities deleted.
    """
    return activity_service.delete_all_strava_activities(user_id, db, source="api:delete_all_strava_activities")


def delete_all_activities_for_user(user_id: int, db: Session) -> int:
    """Delete every activity owned by a user, emitting cleanup events.

    The account-deletion path. Deleting the user row alone would let the database
    FK cascade remove the activities silently, orphaning every thumbnail and
    stored source file the user ever produced. The caller commits.

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The number of activities deleted.
    """
    return activity_service.delete_all_activities_for_user(user_id, db, source="api:delete_user")


def filter_existing_activity_ids(activity_ids: Sequence[int], db: Session) -> set[int]:
    """Return which of the given activity IDs still have a row.

    Used by storage sweeps to tell a live blob from one whose activity is gone.

    Args:
        activity_ids: The IDs to look up.
        db: Database session.

    Returns:
        The subset of ``activity_ids`` that exist.
    """
    return activity_crud.get_existing_activity_ids(activity_ids, db)
