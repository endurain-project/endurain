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

from sqlalchemy.orm import Session

import infra.events as platform_events
import infra.publisher as platform_publisher
import modules.activities.activity.events as activity_events


def publish_activity_created(
    activity_id: int,
    user_id: int | None,
    duplicate_start_time: bool = False,
    db: Session | None = None,
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

    Returns:
        None.
    """
    platform_publisher.publish(
        activity_events.ACTIVITY_CREATED,
        {
            "activity_id": activity_id,
            "user_id": user_id,
            "duplicate_start_time": duplicate_start_time,
        },
        source="api:store_activity",
        metadata={
            platform_events.META_ACTIVITY_ID: activity_id,
            platform_events.META_USER_ID: user_id,
        },
        db=db,
    )


def publish_activity_updated(
    activity_id: int,
    user_id: int | None,
    changed: list[str] | None = None,
    db: Session | None = None,
) -> None:
    """Publish ``activity.updated`` after an activity's metadata was edited.

    Args:
        activity_id: The edited activity's ID.
        user_id: The owning user's ID. Carried in the payload (a subscriber may
            need the owner to load the activity) and mirrored into the metadata
            for event-log correlation.
        changed: The names of the fields the edit changed (best-effort; the edit
            route derives them from the submitted payload). Carried so subscribers
            can react selectively (reindex, feed refresh, ...).
        db: The producer's DB session, used for durable outbox delivery when
            durable jobs are enabled.

    Returns:
        None.
    """
    platform_publisher.publish(
        activity_events.ACTIVITY_UPDATED,
        {"activity_id": activity_id, "user_id": user_id, "changed": changed},
        source="api:edit_activity",
        metadata={
            platform_events.META_ACTIVITY_ID: activity_id,
            platform_events.META_USER_ID: user_id,
        },
        db=db,
    )


def publish_activity_deleted(activity_id: int, user_id: int | None, db: Session | None = None) -> None:
    """Publish ``activity.deleted`` after an activity row has been removed.

    Args:
        activity_id: The removed activity's ID.
        user_id: The owning user's ID, attached as correlation metadata.
        db: The producer's DB session, used for durable outbox delivery when
            durable jobs are enabled.

    Returns:
        None.
    """
    platform_publisher.publish(
        activity_events.ACTIVITY_DELETED,
        {"activity_id": activity_id},
        source="api:delete_activity",
        metadata={
            platform_events.META_ACTIVITY_ID: activity_id,
            platform_events.META_USER_ID: user_id,
        },
        db=db,
    )
