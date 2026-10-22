"""Consume activity and follower events to create user notifications."""

from collections.abc import Callable

import jasil.event_versioning as platform_event_versioning
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.events as activity_events
import modules.followers.events as followers_events
import modules.notifications.integration_service as notifications_integration
import modules.notifications.schema as notifications_schema
import modules.notifications.service as notifications_service

logger = core_logger.get_logger(__name__)

ACTIVITY_NOTIFICATION_SUBSCRIBER_ID = "activity.notify_created"
FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID = "followers.notify_requested"
FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID = "followers.notify_accepted"


def _notify_and_push(
    event: Event,
    recipient_user_id: int,
    create: Callable[[Session], tuple[notifications_schema.NotificationRead, str, bool]],
) -> bool:
    """Create a notification for an event and push it to the recipient.

    A user who no longer exists cannot be notified and a retry cannot change that,
    so the event is dropped instead of failing the durable job.

    Args:
        event: The event being handled, named in the log context.
        recipient_user_id: The user who owns the notification and receives the push.
        create: Stages and commits the notification on the given session.

    Returns:
        True when this call created the notification, False when it was skipped.
    """
    try:
        with core_database.SessionLocal() as db:
            notification, ws_message, created = create(db)
    except core_exceptions.NotFoundError:
        logger.warning(
            "Skipped notification for a user that no longer exists",
            extra=core_logger.context(event_id=event.event_id, event_type=event.event_type),
        )
        return False
    if not created:
        logger.debug(
            "Skipped duplicate notification",
            extra=core_logger.context(event_id=event.event_id, event_type=event.event_type),
        )
        return False
    notifications_integration.push_notification(recipient_user_id, notification, ws_message)
    return True


def notify_activity_created_for_event(event: Event) -> None:
    """Create the notification for a newly stored activity."""
    payload = platform_event_versioning.parse_payload(activity_events.ActivityCreatedPayload, event)
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_activity_created_notification(
            payload.user_id,
            payload.activity_id,
            payload.duplicate_start_time,
            event.event_id,
            db,
        ),
    )
    if created:
        logger.debug(
            "Created new-activity notification",
            extra=core_logger.context(activity_id=payload.activity_id, user_id=payload.user_id),
        )


def notify_follower_requested_for_event(event: Event) -> None:
    """Notify the target user of a new follow request."""
    payload = platform_event_versioning.parse_payload(followers_events.FollowerRequestedPayload, event)
    created = _notify_and_push(
        event,
        payload.target_user_id,
        lambda db: notifications_service.create_follow_request_notification(
            payload.requester_user_id,
            payload.target_user_id,
            event.event_id,
            db,
        ),
    )
    if created:
        logger.debug(
            "Created follow-request notification",
            extra=core_logger.context(
                requester_user_id=payload.requester_user_id,
                target_user_id=payload.target_user_id,
            ),
        )


def notify_follower_accepted_for_event(event: Event) -> None:
    """Notify the requester that their follow request was accepted."""
    payload = platform_event_versioning.parse_payload(followers_events.FollowerAcceptedPayload, event)
    created = _notify_and_push(
        event,
        payload.requester_user_id,
        lambda db: notifications_service.create_follow_accepted_notification(
            payload.accepter_user_id,
            payload.requester_user_id,
            event.event_id,
            db,
        ),
    )
    if created:
        logger.debug(
            "Created follow-accepted notification",
            extra=core_logger.context(
                accepter_user_id=payload.accepter_user_id,
                requester_user_id=payload.requester_user_id,
            ),
        )


on_activity_created_notify = best_effort(notify_activity_created_for_event)
on_follower_requested_notify = best_effort(notify_follower_requested_for_event)
on_follower_accepted_notify = best_effort(notify_follower_accepted_for_event)


def register_notification_subscribers(events: EventBusProvider) -> None:
    """Register every notification event consumer on the running bus."""
    events.subscribe(activity_events.ACTIVITY_CREATED, on_activity_created_notify)
    events.subscribe(followers_events.FOLLOWER_REQUESTED, on_follower_requested_notify)
    events.subscribe(followers_events.FOLLOWER_ACCEPTED, on_follower_accepted_notify)


def register_notification_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register every retryable notification event consumer."""
    registry.register(
        activity_events.ACTIVITY_CREATED,
        ACTIVITY_NOTIFICATION_SUBSCRIBER_ID,
        notify_activity_created_for_event,
    )
    registry.register(
        followers_events.FOLLOWER_REQUESTED,
        FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID,
        notify_follower_requested_for_event,
    )
    registry.register(
        followers_events.FOLLOWER_ACCEPTED,
        FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID,
        notify_follower_accepted_for_event,
    )
