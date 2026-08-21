"""The activities surface consumed by other modules (Strava, Garmin, gears, account deletion).

A small, curated interface so consumers depend on a stable, intentional set of
activity operations instead of reaching into the full ``activity.crud`` (a large
ORM surface, most of it internal to the activities module). It is the
read/gear/delete counterpart to the ingestion seam: ingestion
(:mod:`~modules.activities.activity.ingestion_service` /
:mod:`~modules.activities.activity_ingestion.pipeline`) is how a caller
*stores* a parsed activity; this is how a caller *looks up*, *re-gears*,
*aggregates*, and *bulk-deletes* activities. Every function returns schemas/DTOs
— no ORM row crosses the boundary.

Bulk deletes here also publish one ``activity.deleted`` per removed row, so the
thumbnail and source-file cleanup subscribers reclaim each activity's blobs. That
is the whole reason account deletion and Strava unlinking route through this
module rather than issuing their own DELETE (or relying on the FK cascade). The
publishing itself belongs to ``activity.service``, which owns this module's write
orchestration and its transaction boundaries; every function below is a
delegation, so a write cannot be arranged two different ways depending on whether
it was reached from a route or from another module.

Enforced by the ``provider-activities-boundary`` import-linter contract:
``modules.strava`` / ``modules.garmin`` / ``modules.gears`` must not import
``activity.crud`` or the activities ORM directly; they go through this interface.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

import modules.activities.activity.child_access as activity_child_access
import modules.activities.activity.child_collection as activity_child_collection
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.ingestion_service as activity_ingestion_service
import modules.activities.activity.schema as activities_schema
import modules.activities.activity.service as activity_service

ChildCollection = activity_child_collection.ChildCollection


def get_activity_by_strava_id(
    strava_activity_id: int,
    user_id: int,
    db: Session,
) -> activities_schema.Activity | None:
    """Return the user's activity imported from the given Strava activity id.

    Args:
        strava_activity_id: The Strava provider activity id.
        user_id: The owning user id.
        db: Database session.

    Returns:
        The matching activity, or ``None`` when the user has no such import.
    """
    return activities_crud.get_activity_by_strava_id_from_user_id(strava_activity_id, user_id, db)


def get_activity_by_garminconnect_id(
    garminconnect_activity_id: int,
    user_id: int,
    db: Session,
) -> activities_schema.Activity | None:
    """Return the user's activity imported from the given Garmin Connect activity id.

    Args:
        garminconnect_activity_id: The Garmin Connect provider activity id.
        user_id: The owning user id.
        db: Database session.

    Returns:
        The matching activity, or ``None`` when the user has no such import.
    """
    return activities_crud.get_activity_by_garminconnect_id_from_user_id(garminconnect_activity_id, user_id, db)


def list_user_activities(user_id: int, db: Session) -> list[activities_schema.Activity] | None:
    """Return all of a user's activities (used by provider gear reconciliation).

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The user's activities, or ``None`` when they have none.
    """
    return activities_crud.get_user_activities(user_id, db)


def list_user_activities_with_garminconnect_gear(
    user_id: int,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Return a user's activities that carry a Garmin Connect gear id.

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The matching activities, or ``None`` when there are none.
    """
    return activities_crud.get_user_activities_by_user_id_and_garminconnect_gear_set(user_id, db)


def bulk_set_activities_gear(
    user_id: int,
    gear_assignments: dict[int, int | None],
    db: Session,
) -> int:
    """Assign gear to many of a user's activities at once.

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


def get_gear_usage_totals(gear_id: int, db: Session) -> activities_contracts.ActivityUsageTotals:
    """Return the total distance and moving time recorded against a gear.

    Args:
        gear_id: The gear to accumulate usage for.
        db: Database session.

    Returns:
        The gear's totals; zeroes when it has no activities.
    """
    return activities_crud.sum_gear_usage(gear_id, db)


def get_gear_usage_totals_by_window(
    gear_id: int,
    windows: Sequence[activities_contracts.GearUsageWindow],
    db: Session,
) -> dict[int, activities_contracts.ActivityUsageTotals]:
    """Return per-window usage totals for one gear, in a single query.

    Used to attribute a gear's activities to whichever component was fitted at
    the time. Window bounds are calendar dates evaluated in each activity's own
    timezone, which is why this lives in the activities module rather than being
    joined from the gears side.

    Args:
        gear_id: The gear whose activities to accumulate.
        windows: The date windows to accumulate over, keyed by the caller.
        db: Database session.

    Returns:
        Totals per window key; every requested key is present, zeroed when the
        window matched nothing.
    """
    return activities_crud.sum_gear_usage_by_window(gear_id, windows, db)


def list_user_activities_page(
    user_id: int,
    page_number: int,
    num_records: int,
    db: Session,
) -> list[activities_schema.Activity]:
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
    activities = activities_crud.get_user_activities_with_pagination(
        user_id=user_id,
        db=db,
        page_number=page_number,
        num_records=num_records,
        # Newest first, so an export produced in batches stays in a stable order.
        sort_by="start_time",
        sort_order="desc",
        user_is_owner=True,
    )
    return activities or []


def list_user_activities_in_timeframe_by_types(
    user_id: int,
    activity_types: list[int],
    start: datetime,
    end: datetime,
    db: Session,
    *,
    exclude_hidden: bool = True,
) -> list[activities_schema.Activity]:
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
    activities = activities_crud.get_user_activities_per_timeframe_and_activity_types(
        user_id,
        activity_types,
        start,
        end,
        db,
        True,
        exclude_hidden=exclude_hidden,
    )
    return activities or []


def restore_activity(
    activity: activities_contracts.ActivityCore,
    db: Session,
) -> activities_schema.Activity:
    """Persist an activity from a profile restore **without** publishing events.

    Deliberately not the ``store_parsed_activity`` ingestion seam: a bulk restore
    must not publish ``activity.created`` per row. Doing so would spam the user
    with one "new activity" notification each and, on the in-process bus, render
    every map thumbnail, score HR zones, and reverse-geocode inline inside the
    import loop. The derived artifacts are re-created afterwards by the scheduled
    thumbnail, HR-zone, and geocoding backfills — the reconciliation nets that
    exist for exactly this case.

    Args:
        activity: The activity to persist.
        db: Database session.

    Returns:
        The created activity.
    """
    return activities_crud.create_activity(activity, db)


def store_parsed_activity(
    parsed: activities_contracts.ParsedActivity,
    db: Session,
) -> activities_schema.Activity:
    """Persist a canonical parsed activity through the atomic ingestion seam.

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
) -> activities_schema.Activity | None:
    """Return the parent activity when an authenticated caller may read it."""
    return activity_child_access.resolve_readable_parent(activity_id, requester_user_id, db)


def resolve_public_parent(activity_id: int, db: Session) -> activities_schema.Activity | None:
    """Return the parent activity when it is publicly shareable."""
    return activity_child_access.resolve_public_parent(activity_id, db)


def owns_activity(activity_id: int, user_id: int, db: Session) -> bool:
    """Return whether a user owns an activity."""
    return activity_service.owns_activity(activity_id, user_id, db)


def get_activity_scoring_context(
    activity_id: int,
    db: Session,
) -> activities_contracts.ActivityScoringContext | None:
    """Return parent columns needed to score one activity's streams."""
    return activities_crud.get_activity_scoring_context(activity_id, db)


def get_activity_scoring_contexts(
    activity_ids: list[int],
    db: Session,
) -> dict[int, activities_contracts.ActivityScoringContext]:
    """Return stream-scoring contexts keyed by activity id."""
    return activities_crud.get_activity_scoring_contexts(activity_ids, db)


def list_user_activity_scoring_contexts(
    user_id: int,
    db: Session,
    *,
    after_id: int = 0,
    batch_size: int = 500,
) -> list[activities_contracts.ActivityScoringContext]:
    """Return a bounded batch of one user's stream-scoring contexts."""
    return activities_crud.list_user_activity_scoring_contexts(
        user_id,
        db,
        after_id=after_id,
        batch_size=batch_size,
    )


def set_thumbnail_key(activity_id: int, key: str | None, db: Session) -> None:
    """Record or clear an activity's stored thumbnail key."""
    activity_service.set_thumbnail_key(activity_id, key, db)


def clear_all_thumbnail_keys(db: Session) -> None:
    """Clear every stored activity thumbnail key."""
    activity_service.clear_all_thumbnail_keys(db)


def list_activities_with_thumbnail(db: Session) -> list[activities_contracts.ActivityThumbnailRef]:
    """Return activity references carrying a stored thumbnail key."""
    return activity_service.list_activities_with_thumbnail(db)


def list_activities_without_thumbnail(db: Session) -> list[activities_contracts.ActivityThumbnailRef]:
    """Return activity references that have no stored thumbnail key."""
    return activity_service.list_activities_without_thumbnail(db)


def list_activities_missing_location(
    db: Session,
    limit: int = 200,
) -> list[activities_contracts.ActivityLocationRef]:
    """Return bounded activity references whose location is unresolved."""
    return activity_service.list_activities_missing_location(db, limit)


def set_activity_location(
    activity_id: int,
    city: str | None,
    town: str | None,
    country: str | None,
    db: Session,
) -> bool:
    """Persist a reverse-geocoded activity location."""
    return activity_service.set_activity_location(activity_id, city, town, country, db)


def delete_all_strava_activities(user_id: int, db: Session) -> int:
    """Delete all of a user's Strava-sourced activities.

    Emits one ``activity.deleted`` per removed activity so the thumbnail and
    source-file cleanup subscribers reclaim the blobs each one owned.

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
    stored source file the user ever produced.

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The number of activities deleted.
    """
    return activity_service.delete_all_activities_for_user(user_id, db, source="api:delete_user")
