"""Publish the activities domain events through the platform publish facade.

Thin domain layer co-locating the module's event publishers: each function knows
its channel and correlation metadata and delegates envelope assembly, ambient
request-id stamping, best-effort delivery, and the durable outbox to
:mod:`infra.publisher`. Producers (``store_activity``, the delete route)
call these instead of building events themselves, so they stay ignorant of the
substrate and of who subscribes. They pass their DB session so that, when durable
jobs are enabled, the event is staged in the outbox for durable per-subscriber
delivery (best-effort at the seam; the subscriber's reconciliation net is the
safety net).
"""

from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

import infra.events as platform_events
import infra.publisher as platform_publisher
import modules.activities.activity.events as activity_events


def publish_activity_created(
    activity_id: int,
    user_id: int | None,
    duplicate_start_time: bool = False,
    db: Session | None = None,
    commit: Callable[[], None] | None = None,
) -> None:
    """Publish ``activity.created`` for a freshly stored activity.

    Args:
        activity_id: The stored activity's ID.
        user_id: The owning user's ID. Carried in the **payload** (a subscriber
            such as thumbnail generation needs the owner to load the activity's
            own streams) and mirrored into the **metadata** for event-log
            correlation.
        duplicate_start_time: Whether the activity duplicates an existing
            activity's start time (marked hidden on store). Carried in the
            payload so the notification subscriber can raise the duplicate
            variant instead of the new-activity notification.
        db: The producer's DB session, used for durable outbox delivery when
            durable jobs are enabled.
        commit: When provided, the event is published transactionally around this
            zero-arg commit callable (:func:`infra.publisher.publish_committing`):
            the ingestion service owns a single commit for the activity + its
            children, and the durable outbox row joins that same transaction (or
            the event dispatches on the bus post-commit). When ``None`` the event
            is published best-effort after the caller has already committed.

    Returns:
        None.
    """
    payload = {
        "activity_id": activity_id,
        "user_id": user_id,
        "duplicate_start_time": duplicate_start_time,
    }
    metadata = {
        platform_events.META_ACTIVITY_ID: activity_id,
        platform_events.META_USER_ID: user_id,
    }
    if commit is not None:
        platform_publisher.publish_committing(
            activity_events.ACTIVITY_CREATED,
            payload,
            source="api:store_activity",
            metadata=metadata,
            db=db,
            commit=commit,
        )
    else:
        platform_publisher.publish(
            activity_events.ACTIVITY_CREATED,
            payload,
            source="api:store_activity",
            metadata=metadata,
            db=db,
        )


def publish_activity_deleted(
    activity_id: int,
    user_id: int | None,
    db: Session | None = None,
    commit: Callable[[], None] | None = None,
) -> None:
    """Publish ``activity.deleted`` after an activity row has been removed.

    Args:
        activity_id: The removed activity's ID.
        user_id: The owning user's ID, attached as correlation metadata.
        db: The producer's DB session, used for durable outbox delivery when
            durable jobs are enabled.
        commit: When provided, the event is published transactionally around this
            zero-arg commit callable (:func:`infra.publisher.publish_committing`):
            the delete is staged uncommitted and the durable outbox row joins that
            same transaction, so the row deletion and the cleanup event commit
            together (a crash cannot delete the activity while orphaning its
            thumbnail / source-file blobs). When ``None`` the event is published
            best-effort after the caller has already committed.

    Returns:
        None.
    """
    metadata = {
        platform_events.META_ACTIVITY_ID: activity_id,
        platform_events.META_USER_ID: user_id,
    }
    if commit is not None:
        platform_publisher.publish_committing(
            activity_events.ACTIVITY_DELETED,
            {"activity_id": activity_id},
            source="api:delete_activity",
            metadata=metadata,
            db=db,
            commit=commit,
        )
    else:
        platform_publisher.publish(
            activity_events.ACTIVITY_DELETED,
            {"activity_id": activity_id},
            source="api:delete_activity",
            metadata=metadata,
            db=db,
        )


def publish_activities_deleted(
    activity_ids: Sequence[int],
    user_id: int | None,
    db: Session,
    commit: Callable[[], None],
    *,
    source: str,
) -> None:
    """Publish one ``activity.deleted`` per activity removed by a bulk delete.

    Bulk removals (unlinking Strava, deleting a user account) used to delete rows
    without publishing anything, so the thumbnail and source-file cleanup
    subscribers never ran and their blobs were orphaned forever — and because both
    subscribers are deliberately reconciliation-net exempt (a teardown has no
    create-derived state to re-derive), nothing else ever reclaimed them. Emitting
    the same fact the single-activity delete route emits keeps every consumer's
    contract identical regardless of how the rows were removed, which also makes
    account deletion actually erase the user's stored artifacts.

    The whole batch is staged in the caller's transaction and committed once via
    :func:`infra.publisher.publish_many_committing`, so the deletes and their
    events are atomic rather than one commit per activity.

    Args:
        activity_ids: IDs of the removed activities. May be empty, in which case
            ``commit`` still runs exactly once.
        user_id: The owning user's ID, attached as correlation metadata.
        db: The producer's DB session holding the staged deletes.
        commit: Zero-arg callable that commits the caller's unit of work.
        source: Origin label identifying the bulk operation.

    Returns:
        None.
    """
    platform_publisher.publish_many_committing(
        activity_events.ACTIVITY_DELETED,
        [{"activity_id": activity_id} for activity_id in activity_ids],
        source=source,
        metadata_for=lambda payload: {
            platform_events.META_ACTIVITY_ID: payload["activity_id"],
            platform_events.META_USER_ID: user_id,
        },
        db=db,
        commit=commit,
    )
