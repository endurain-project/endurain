"""Publish the activities domain events through the platform publish facade.

Thin domain layer co-locating the module's event publishers: each function knows
its channel and correlation metadata and delegates envelope assembly, ambient
request-id stamping, best-effort delivery, and the durable outbox to
:mod:`jasil.publisher`. Producers (``store_activity``, the edit/bulk-edit
service, the delete route) call these instead of building events themselves, so
they stay ignorant of the substrate and of who subscribes. They only stage: the
caller commits, and the event follows that commit. When durable jobs are enabled
the outbox row joins the caller's transaction, so it commits or rolls back with
the domain rows; otherwise the event dispatches on the bus after the outermost
commit and is dropped on rollback.
"""

from collections.abc import Iterable, Sequence

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.activities.activity.events as activity_events


def publish_activity_created(
    activity_id: int,
    user_id: int,
    db: Session,
    *,
    source: str,
    duplicate_start_time: bool = False,
) -> None:
    """Publish ``activity.created`` for a freshly stored activity.

    Args:
        activity_id: The stored activity's ID.
        user_id: The owning user's ID. Carried in the **payload** (a subscriber
            such as thumbnail generation needs the owner to load the activity's
            own streams) and mirrored into the **metadata** for event-log
            correlation.
        db: The producer's DB session, used for durable outbox delivery when
            durable jobs are enabled.
        source: Where the activity came from (e.g. ``ingest:upload``), for event-log
            correlation.
        duplicate_start_time: Whether the activity duplicates an existing
            activity's start time (marked hidden on store). Carried in the
            payload so the notification subscriber can raise the duplicate
            variant instead of the new-activity notification.
    """
    payload = activity_events.ActivityCreatedPayload(
        activity_id=activity_id,
        user_id=user_id,
        duplicate_start_time=duplicate_start_time,
    )
    metadata = {
        core_event_metadata.META_ACTIVITY_ID: activity_id,
        core_event_metadata.META_USER_ID: user_id,
    }
    platform_publisher.publish_on_commit(
        activity_events.ACTIVITY_CREATED,
        payload.model_dump(),
        source=source,
        metadata=metadata,
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_activity_updated(
    activity_id: int,
    user_id: int | None,
    db: Session,
    *,
    changed_fields: Iterable[str],
) -> None:
    """Publish ``activity.updated`` after an activity's own columns changed.

    Args:
        activity_id: The updated activity's ID.
        user_id: The owning user's ID, carried in the payload (a subscriber needs
            the owner to re-read the activity) and mirrored into the metadata for
            event-log correlation.
        changed_fields: The columns this update wrote. Sorted before publishing so
            an event-log reader (and a test) sees a stable order regardless of the
            producer's iteration order.
        db: The producer's DB session, used for durable outbox delivery when
            durable jobs are enabled.
    """
    payload = activity_events.ActivityUpdatedPayload(
        activity_id=activity_id,
        user_id=user_id,
        changed_fields=sorted(changed_fields),
    )
    metadata = {
        core_event_metadata.META_ACTIVITY_ID: activity_id,
        core_event_metadata.META_USER_ID: user_id,
    }
    platform_publisher.publish_on_commit(
        activity_events.ACTIVITY_UPDATED,
        payload.model_dump(),
        source="api:edit_activity",
        metadata=metadata,
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_activities_updated(
    activity_ids: Sequence[int],
    user_id: int | None,
    db: Session,
    *,
    changed_fields: Iterable[str],
    source: str,
) -> None:
    """Publish one ``activity.updated`` per activity touched by a bulk update.

    One event per row rather than a single "many activities changed" event: a
    subscriber's unit of work is one activity, so a batched fact would force
    every consumer to re-derive the id list the producer already has — the same
    reasoning as :func:`publish_activities_deleted`.

    The whole batch is staged in the caller's transaction and published with
    :func:`jasil.publisher.publish_many_on_commit`, so the updates and their
    events commit together.

    Args:
        activity_ids: IDs of the updated activities. May be empty, in which case
            nothing is published.
        user_id: The owning user's ID, attached as correlation metadata.
        changed_fields: The columns the bulk update wrote (identical for every
            row in the batch, which is what makes one field list correct here).
        db: The producer's DB session holding the staged updates.
        source: Origin label identifying the bulk operation.
    """
    fields = sorted(changed_fields)
    platform_publisher.publish_many_on_commit(
        activity_events.ACTIVITY_UPDATED,
        [
            activity_events.ActivityUpdatedPayload(
                activity_id=activity_id, user_id=user_id, changed_fields=fields
            ).model_dump()
            for activity_id in activity_ids
        ],
        source=source,
        metadata_for=lambda payload: {
            core_event_metadata.META_ACTIVITY_ID: payload["activity_id"],
            core_event_metadata.META_USER_ID: user_id,
        },
        db=db,
        schema_version=activity_events.ActivityUpdatedPayload.SCHEMA_VERSION,
    )


def publish_activity_deleted(
    activity_id: int,
    user_id: int | None,
    db: Session,
) -> None:
    """Publish ``activity.deleted`` after an activity row has been removed.

    Args:
        activity_id: The removed activity's ID.
        user_id: The owning user's ID, attached as correlation metadata.
        db: The producer's DB session, used for durable outbox delivery when
            durable jobs are enabled.
    """
    deleted = activity_events.ActivityDeletedPayload(activity_id=activity_id)
    metadata = {
        core_event_metadata.META_ACTIVITY_ID: activity_id,
        core_event_metadata.META_USER_ID: user_id,
    }
    platform_publisher.publish_on_commit(
        activity_events.ACTIVITY_DELETED,
        deleted.model_dump(),
        source="api:delete_activity",
        metadata=metadata,
        db=db,
        schema_version=deleted.SCHEMA_VERSION,
    )


def publish_activities_deleted(
    activity_ids: Sequence[int],
    user_id: int | None,
    db: Session,
    *,
    source: str,
) -> None:
    """Publish one ``activity.deleted`` per activity removed by a bulk delete.

    Bulk removals (unlinking Strava, deleting a user account) must publish too:
    the cleanup subscribers key a blob off the deleted activity's id, and no row
    remains to find it from afterwards. Their storage sweeps are the net for a
    dropped event, but the event is what reclaims the blobs promptly. Emitting the
    same fact the single-activity delete route emits keeps every consumer's
    contract identical regardless of how the rows were removed.

    The whole batch is staged in the caller's transaction and published with
    :func:`jasil.publisher.publish_many_on_commit`, so the deletes and their
    events commit together.

    Args:
        activity_ids: IDs of the removed activities. May be empty, in which case
            nothing is published.
        user_id: The owning user's ID, attached as correlation metadata.
        db: The producer's DB session holding the staged deletes.
        source: Origin label identifying the bulk operation.
    """
    platform_publisher.publish_many_on_commit(
        activity_events.ACTIVITY_DELETED,
        [activity_events.ActivityDeletedPayload(activity_id=activity_id).model_dump() for activity_id in activity_ids],
        source=source,
        metadata_for=lambda payload: {
            core_event_metadata.META_ACTIVITY_ID: payload["activity_id"],
            core_event_metadata.META_USER_ID: user_id,
        },
        db=db,
        schema_version=activity_events.ActivityDeletedPayload.SCHEMA_VERSION,
    )
