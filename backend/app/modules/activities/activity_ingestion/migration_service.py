"""The ingestion operations the reprocess data migration needs, and nothing else.

Imported only by ``app/migrations``. Each write is a wrapper that owns its commit, which CRUD never performs.
"""

import uuid

import jasil.providers as platform_providers

import core.database as core_database
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_ingestion.reprocess_service as activity_ingestion_reprocess_service
import modules.activities.activity_streams.integration_service as activity_streams_integration
import modules.activities.computation as activities_computation

ReprocessOutcome = activity_ingestion_reprocess_service.ReprocessOutcome

#: The analysis version activities are reprocessed up to.
ANALYSIS_VERSION = activities_computation.ANALYSIS_VERSION


def reprocess_activity(activity_id: uuid.UUID, storage: platform_providers.StorageProvider) -> ReprocessOutcome:
    """Recompute one activity from its retained file and write it over the stored values.

    Opens its own short sessions, so none is held while the file is read, parsed or adopted, and commits one transaction
    per step: the adoption of a file stored before file rows, then the activity (a multisport activity with its legs).
    It publishes no event. An activity with no retained file, no session that starts where it does, or an unreadable
    file keeps its values, though its file, when it has one, is adopted.

    Args:
        activity_id: The activity to reprocess.
        storage: The blob-storage provider the source file is retained in.

    Returns:
        What was done.
    """
    return activity_ingestion_reprocess_service.reprocess_activity(activity_id, storage)


def convert_legacy_streams(activity_id: uuid.UUID) -> bool:
    """Convert the old waypoint streams of an activity the reprocess did not rewrite to its samples, and delete them.

    Commits its own transaction.

    Args:
        activity_id: The activity.

    Returns:
        ``True`` when the activity had old streams.
    """
    with core_database.SessionLocal() as db:
        converted = activity_streams_integration.convert_legacy_streams(activity_id, db)
        db.commit()
    return converted


def list_activities_to_reprocess(limit: int) -> list[uuid.UUID]:
    """Return the activities the reprocess has not visited yet, in id order.

    These are the activities below the current analysis version, a leg of a multisport activity included: a leg
    alone has no file of its own, so it is stamped, and its parent's reprocess re-derives it.

    Args:
        limit: The most ids to return.

    Returns:
        Up to ``limit`` activity ids; empty when every activity is at the current analysis version.
    """
    with core_database.SessionLocal() as db:
        return activity_integration.list_ids_below_analysis_version(activities_computation.ANALYSIS_VERSION, limit, db)


def mark_reprocess_visited(activity_id: uuid.UUID) -> None:
    """Stamp the current analysis version on an activity the reprocess did not rewrite.

    Without it the walk would list the activity again. A write that leaves ``version`` and ``updated_at`` alone and
    commits its own transaction.

    Args:
        activity_id: The activity to stamp.
    """
    with core_database.SessionLocal() as db:
        activity_integration.stamp_analysis_version(activity_id, activities_computation.ANALYSIS_VERSION, db)
        db.commit()
