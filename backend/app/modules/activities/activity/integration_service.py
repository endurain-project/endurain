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
module rather than issuing their own DELETE (or relying on the FK cascade).

Enforced by the ``provider-activities-boundary`` import-linter contract:
``modules.strava`` / ``modules.garmin`` / ``modules.gears`` must not import
``activity.crud`` or the activities ORM directly; they go through this interface.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

import core.logger as core_logger
import infra.providers as platform_providers
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.event_publishers as activity_event_publishers
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.activities.activity_file_storage.service as activity_file_storage_service
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.service as activity_media_service
import modules.activities.activity_media.signing as activity_media_signing
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema

logger = core_logger.get_logger(__name__)


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

    Publishes one ``activity.updated`` per changed row, atomically with the
    updates. A provider re-syncing gear mutates activities from outside the
    activities module, so without the event a consumer would see the same silent
    change bulk deletes used to make.

    Args:
        user_id: The owning user id (ownership is enforced by the update).
        gear_assignments: Map of activity id -> gear id (or ``None`` to clear).
        db: Database session.

    Returns:
        The number of activities updated.
    """
    updated_ids = activities_crud.bulk_set_activities_gear_id(user_id, gear_assignments, db, commit=False)
    activity_event_publishers.publish_activities_updated(
        updated_ids,
        user_id,
        ["gear_id"],
        db,
        db.commit,
        source="api:bulk_set_activities_gear",
    )
    logger.info(
        "Bulk-assigned gear to activities",
        extra=core_logger.context(user_id=user_id, requested=len(gear_assignments), updated=len(updated_ids)),
    )
    return len(updated_ids)


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


def delete_all_strava_activities(user_id: int, db: Session) -> int:
    """Delete all of a user's Strava-sourced activities.

    Emits one ``activity.deleted`` per removed activity, atomically with the
    deletes, so the thumbnail and source-file cleanup subscribers reclaim the
    blobs each activity owned. Without it the rows vanished silently and their
    artifacts were orphaned in storage permanently.

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The number of activities deleted.
    """
    deleted_ids = activities_crud.delete_all_strava_activities_for_user(user_id, db, commit=False)
    activity_event_publishers.publish_activities_deleted(
        deleted_ids,
        user_id,
        db,
        db.commit,
        source="api:delete_all_strava_activities",
    )
    # Irreversible and triggered from another module, so the count is recorded
    # here rather than left to the caller.
    logger.info(
        "Deleted all Strava-sourced activities for user",
        extra=core_logger.context(user_id=user_id, deleted_count=len(deleted_ids)),
    )
    return len(deleted_ids)


def delete_all_activities_for_user(user_id: int, db: Session) -> int:
    """Delete every activity owned by a user, emitting cleanup events.

    The account-deletion path. Deleting the user row alone would let the database
    FK cascade remove the activities silently, orphaning every thumbnail and
    stored source file the user ever produced — an incomplete erasure. Removing
    them explicitly first yields the ids needed to publish ``activity.deleted``,
    so the cleanup subscribers delete the blobs too.

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The number of activities deleted.
    """
    deleted_ids = activities_crud.delete_all_activities_for_user(user_id, db, commit=False)
    activity_event_publishers.publish_activities_deleted(
        deleted_ids,
        user_id,
        db,
        db.commit,
        source="api:delete_user",
    )
    logger.info(
        "Deleted all activities for user",
        extra=core_logger.context(user_id=user_id, deleted_count=len(deleted_ids)),
    )
    return len(deleted_ids)


# ---------------------------------------------------------------------------
# Child sub-resources (laps / sets / streams / workout steps / exercise titles)
#
# The profile export and import are the only callers outside this domain that
# need an activity's *children*. They used to import each child package's
# ``crud`` module directly — five persistence modules reached across a module
# boundary, which is what the ``consumer-activities-boundary`` contract exists to
# prevent for the parent. Routing them through here means the activities domain
# owns which child operations are public, and a consumer keeps one import.
# ---------------------------------------------------------------------------


def list_activities_laps(
    activity_ids: list[int],
    user_id: int,
    db: Session,
    activities: list[activities_schema.Activity] | None = None,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """Return the laps of many of a user's activities (profile export)."""
    return activity_laps_crud.get_activities_laps(activity_ids, user_id, db, activities)


def list_activities_sets(
    activity_ids: list[int],
    user_id: int,
    db: Session,
    activities: list[activities_schema.Activity] | None = None,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """Return the workout sets of many of a user's activities (profile export)."""
    return activity_sets_crud.get_activities_sets(activity_ids, user_id, db, activities)


def list_activities_streams(
    activity_ids: list[int],
    user_id: int,
    db: Session,
    activities: list[activities_schema.Activity] | None = None,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Return the streams of many of a user's activities (profile export)."""
    return activity_streams_crud.get_activities_streams(activity_ids, user_id, db, activities)


def list_activities_workout_steps(
    activity_ids: list[int],
    user_id: int,
    db: Session,
    activities: list[activities_schema.Activity] | None = None,
) -> list[activity_workout_steps_schema.ActivityWorkoutSteps]:
    """Return the workout steps of many of a user's activities (profile export)."""
    return activity_workout_steps_crud.get_activities_workout_steps(activity_ids, user_id, db, activities)


def list_exercise_titles(db: Session) -> list[activity_exercise_titles_schema.ActivityExerciseTitles]:
    """Return the server-wide exercise-title reference rows (profile export)."""
    return activity_exercise_titles_crud.get_activity_exercise_titles(db)


def list_activities_media(
    activity_ids: list[int],
    user_id: int,
    db: Session,
    activities: list[activities_schema.Activity] | None = None,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """Return the media records of many of a user's activities (profile export).

    ``activities`` is accepted and ignored so every batch read in the export
    shares one call shape; the media query resolves ownership itself.
    """
    return activity_media_crud.get_activities_media(activity_ids, user_id, db)


def restore_activity_media(
    media: list[activity_media_contracts.ActivityMediaCreate],
    activity_id: int,
    db: Session,
) -> None:
    """Persist a restored activity's media records (profile import)."""
    activity_media_crud.create_activity_medias(media, activity_id, db)


def restore_activity_laps(laps: list[dict], activity_id: int, db: Session) -> None:
    """Persist a restored activity's laps (profile import)."""
    activity_laps_crud.create_activity_laps(laps, activity_id, db)


def restore_activity_sets(
    sets: list[activity_sets_schema.ActivitySetsCreate | list],
    activity_id: int,
    db: Session,
) -> None:
    """Persist a restored activity's workout sets (profile import)."""
    activity_sets_crud.create_activity_sets(sets, activity_id, db)


def restore_activity_streams(
    streams: list[activity_streams_schema.ActivityStreamsCreate],
    activity: activities_schema.Activity,
    db: Session,
) -> None:
    """Persist a restored activity's streams (profile import)."""
    activity_streams_crud.create_activity_streams(streams, activity, db)


def restore_activity_workout_steps(
    steps: list[activity_workout_steps_schema.ActivityWorkoutSteps],
    activity_id: int,
    db: Session,
) -> None:
    """Persist a restored activity's workout steps (profile import)."""
    activity_workout_steps_crud.create_activity_workout_steps(steps, activity_id, db)


def restore_exercise_titles(
    titles: list[activity_exercise_titles_schema.ActivityExerciseTitles],
    db: Session,
) -> None:
    """Persist restored exercise-title reference rows (profile import)."""
    activity_exercise_titles_crud.create_activity_exercise_titles(titles, db)


def recompute_hr_zones_for_user(user_id: int, db: Session) -> None:
    """Re-derive every stored HR-zone breakdown for a user.

    Called by the users module when a change to max heart rate or birthdate
    invalidates the zones computed at import time. It logs and swallows its own
    errors, so it cannot fail the profile edit that triggered it.

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        None.
    """
    activity_streams_crud.recompute_hr_zone_percentages_for_user(user_id, db)


# ---------------------------------------------------------------------------
# Activity blobs
#
# An activity owns two kinds of blob — the retained source file it was parsed
# from, and its photos — and the profile export/import needs both. It used to
# get them by importing ``activity_file_storage.service`` and
# ``activity_media.signing``, then calling the storage provider itself with the
# activities module's own area name and key prefix. That made a second module a
# co-author of the activities storage layout: change the key shape and the
# export silently stops finding anything.
#
# These take the ``StorageProvider`` rather than resolving it, because the
# caller already holds one (a profile export runs against the platform it was
# handed) and passing it keeps this surface free of runtime lookups.


def get_activity_source_file(
    activity_id: int,
    storage: platform_providers.StorageProvider,
) -> tuple[str, bytes] | None:
    """Read an activity's retained source file.

    Args:
        activity_id: The owning activity id.
        storage: The blob-storage provider.

    Returns:
        A ``(filename, data)`` pair, or ``None`` when nothing was retained.
    """
    return activity_file_storage_service.get_activity_file(activity_id, storage)


def store_activity_source_file(
    activity_id: int,
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> str:
    """Persist a source file against an activity (profile import).

    Args:
        activity_id: The owning activity id.
        extension: The source-file extension (e.g. ``".fit"``).
        data: The raw, already-validated file bytes.
        storage: The blob-storage provider.

    Returns:
        The filename the file was stored under.
    """
    return activity_file_storage_service.store_activity_file(activity_id, extension, data, storage)


def list_activity_media_blobs(
    activity_id: int,
    storage: platform_providers.StorageProvider,
) -> list[tuple[str, bytes]]:
    """Read every media blob attached to an activity.

    Args:
        activity_id: The owning activity id.
        storage: The blob-storage provider.

    Returns:
        ``(filename, data)`` pairs, empty when the activity has no media or the
        blobs could not be listed. Individual unreadable blobs are skipped: a
        profile export must not fail wholesale over one missing photo.
    """
    try:
        keys = storage.list_keys(activity_media_signing.MEDIA_STORAGE_AREA, f"{activity_id}_")
    except Exception as err:
        logger.warning(
            "Could not list an activity's media blobs",
            exc_info=err,
            extra=core_logger.context(activity_id=activity_id),
        )
        return []
    blobs: list[tuple[str, bytes]] = []
    for key in keys:
        try:
            data = storage.get(activity_media_signing.MEDIA_STORAGE_AREA, key)
        except Exception as err:
            logger.warning(
                "Could not read a media blob; skipping it",
                exc_info=err,
                extra=core_logger.context(storage_key=key),
            )
            continue
        if data is None:
            logger.warning("Media blob is missing behind its key", extra=core_logger.context(storage_key=key))
            continue
        blobs.append((key, data))
    return blobs


def store_activity_media_blob(
    activity_id: int,
    suffix: str,
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> str:
    """Restore one media blob against an activity (profile import).

    Restores the blob only — the media *row* is restored separately from the
    exported table dump, which is what keeps the two halves of an export in
    step.

    Args:
        activity_id: The owning activity id.
        suffix: The exported blob's unique suffix, preserved so the restored
            key still matches the restored row.
        extension: The image extension, with leading dot.
        data: The raw, already-validated image bytes.
        storage: The blob-storage provider.

    Returns:
        The filename the blob was stored under.
    """
    key = f"{activity_id}_{suffix}{extension}"
    storage.save(activity_media_signing.MEDIA_STORAGE_AREA, key, data)
    return key


def attach_media_bytes(
    activity_id: int,
    original_filename: str | None,
    data: bytes,
    db: Session,
) -> activity_media_contracts.ActivityMediaRecord:
    """Register already-validated image bytes as media for an activity.

    For a server-side import that ships photos alongside its activity files (a
    Strava bulk export). The caller owns validation — it holds the file, not an
    upload — and everything after that stays inside the activities module.

    Args:
        activity_id: The activity to attach the media to.
        original_filename: The source filename, used only for its extension.
        data: The raw, already-validated image bytes.
        db: Database session.

    Returns:
        The created media record.
    """
    return activity_media_service.store_activity_media_bytes(activity_id, original_filename, data, db)
