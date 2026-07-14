"""Publish the activities domain events through the platform publish facade.

Thin domain layer co-locating the module's event publishers: each function knows
its channel and correlation metadata and delegates envelope assembly, ambient
request-id stamping, best-effort delivery, and the future transactional outbox to
:mod:`core.platform.publisher`. Producers (``store_activity``, the delete route)
call these instead of building events themselves, so they stay ignorant of the
substrate and of who subscribes.
"""

import activities.activity.events as activity_events
import core.platform.events as platform_events
import core.platform.publisher as platform_publisher


def publish_activity_created(activity_id: int, user_id: int | None) -> None:
    """Publish ``activity.created`` for a freshly stored activity.

    Args:
        activity_id: The stored activity's ID.
        user_id: The owning user's ID. Carried in the **payload** (a subscriber
            such as thumbnail generation needs the owner to load the activity's
            own streams) and mirrored into the **metadata** for event-log
            correlation.

    Returns:
        None.
    """
    platform_publisher.publish(
        activity_events.ACTIVITY_CREATED,
        {"activity_id": activity_id, "user_id": user_id},
        source="api:store_activity",
        metadata={
            platform_events.META_ACTIVITY_ID: activity_id,
            platform_events.META_USER_ID: user_id,
        },
    )


def publish_activity_deleted(activity_id: int, user_id: int | None) -> None:
    """Publish ``activity.deleted`` after an activity row has been removed.

    Args:
        activity_id: The removed activity's ID.
        user_id: The owning user's ID, attached as correlation metadata.

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
    )
