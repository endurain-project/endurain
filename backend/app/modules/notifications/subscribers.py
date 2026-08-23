"""Consume activity and follower events to create user notifications."""

import jasil.event_versioning as platform_event_versioning
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.async_bridge as core_async_bridge
import core.database as core_database
import core.logger as core_logger
import modules.activities.activity.events as activity_events
import modules.followers.events as followers_events
import modules.notifications.integration_service as notifications_integration
import modules.websocket.integration_service as websocket_integration

logger = core_logger.get_logger(__name__)

ACTIVITY_NOTIFICATION_SUBSCRIBER_ID = "activity.notify_created"
FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID = "followers.notify_requested"
FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID = "followers.notify_accepted"


def notify_activity_created_for_event(event: Event) -> None:
    """Create the notification for a newly stored activity."""
    payload = platform_event_versioning.parse_payload(activity_events.ActivityCreatedPayload, event)
    with core_database.SessionLocal() as db:
        notification, ws_message = notifications_integration.create_activity_created_notification(
            payload.user_id,
            payload.activity_id,
            payload.duplicate_start_time,
            db,
        )
    core_async_bridge.dispatch(
        websocket_integration.push_to_user(
            payload.user_id,
            {"message": ws_message, "notification_id": notification.id},
        )
    )
    logger.debug(
        "Created new-activity notification",
        extra=core_logger.context(
            activity_id=payload.activity_id,
            user_id=payload.user_id,
            notification_id=notification.id,
        ),
    )


def notify_follower_requested_for_event(event: Event) -> None:
    """Notify the target user of a new follow request."""
    payload = platform_event_versioning.parse_payload(followers_events.FollowerRequestedPayload, event)
    with core_database.SessionLocal() as db:
        notification, ws_message = notifications_integration.create_follow_request_notification(
            payload.requester_user_id,
            payload.target_user_id,
            db,
        )
    core_async_bridge.dispatch(
        websocket_integration.push_to_user(
            payload.target_user_id,
            {"message": ws_message, "notification_id": notification.id},
        )
    )
    logger.debug(
        "Created follow-request notification",
        extra=core_logger.context(
            requester_user_id=payload.requester_user_id,
            target_user_id=payload.target_user_id,
            notification_id=notification.id,
        ),
    )


def notify_follower_accepted_for_event(event: Event) -> None:
    """Notify the requester that their follow request was accepted."""
    payload = platform_event_versioning.parse_payload(followers_events.FollowerAcceptedPayload, event)
    with core_database.SessionLocal() as db:
        notification, ws_message = notifications_integration.create_follow_accepted_notification(
            payload.accepter_user_id,
            payload.requester_user_id,
            db,
        )
    core_async_bridge.dispatch(
        websocket_integration.push_to_user(
            payload.requester_user_id,
            {"message": ws_message, "notification_id": notification.id},
        )
    )
    logger.debug(
        "Created follow-accepted notification",
        extra=core_logger.context(
            accepter_user_id=payload.accepter_user_id,
            requester_user_id=payload.requester_user_id,
            notification_id=notification.id,
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
