"""Applies realtime hints and control messages to the sockets this process holds, and turns revocations into control messages."""

import uuid
from typing import Any

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.async_bridge as core_async_bridge
import core.logger as core_logger
import modules.auth.sessions.events as sessions_events
import modules.websocket.keys as websocket_keys
import modules.websocket.manager as websocket_manager
import modules.websocket.service as websocket_service

logger = core_logger.get_logger(__name__)


def on_realtime_hint(key: str, hint: dict[str, Any]) -> None:
    """Handle one hint from the realtime channel.

    Every started process receives every hint, so most are for a user whose socket is
    held elsewhere and are dropped on the loop. A control message (see
    ``integration_service.close_revoked_sockets``) closes sockets and is never sent to a client.
    The channel is server-wide, so a key that addresses neither a user nor a control message is ignored. This runs on the channel's subscriber thread (inline
    on the publisher for the in-process channel), so the send is handed to the main
    event loop, which owns the sockets.

    Args:
        key: The audience the hint was published for.
        hint: The hint to push.
    """
    control_user_id = websocket_keys.parse_control_key(key)
    if control_user_id is not None:
        _close_revoked_sockets(control_user_id, hint)
        return
    user_id = websocket_keys.parse_user_key(key)
    if user_id is None:
        logger.debug("Ignored a realtime hint that does not address a user")
        return
    # The registry belongs to the event loop, so whether this process holds the user's
    # socket is answered there (deliver_hint returns at once when it does not).
    core_async_bridge.dispatch(websocket_service.deliver_hint(user_id, hint, websocket_manager.get_websocket_manager()))


def _optional_uuid(value: object) -> uuid.UUID | None:
    """Parse an optional UUID text from a control message.

    Args:
        value: The field of the control message.

    Returns:
        The UUID, or None when the field is absent.

    Raises:
        TypeError: When the field is neither absent nor a string.
        ValueError: When the text is not a UUID.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("a session id is text")
    return uuid.UUID(value)


def _close_revoked_sockets(user_id: uuid.UUID, message: dict[str, Any]) -> None:
    """Close, on the event loop, the sockets a control message names.

    Args:
        user_id: The user the control key addresses.
        message: The control message, which anyone may have published.
    """
    try:
        session_id = _optional_uuid(message.get("session_id"))
        except_session_id = _optional_uuid(message.get("except_session_id"))
    except (TypeError, ValueError):
        logger.debug("Ignored a malformed socket control message")
        return
    core_async_bridge.dispatch(
        websocket_service.close_revoked_connections(
            user_id, session_id, except_session_id, websocket_manager.get_websocket_manager()
        )
    )


def close_sockets_for_event(event: Event) -> None:
    """Turn an ``auth.sessions_revoked`` event into a control message for every replica.

    The event reaches one process, but the sockets may be held by any, so the close goes out on the
    realtime channel instead of being applied here.

    Args:
        event: The ``auth.sessions_revoked`` event.
    """
    payload = platform_event_versioning.parse_payload(sessions_events.SessionsRevokedPayload, event)
    if not platform_runtime.is_platform_active():
        logger.debug(
            "The platform is not running; dropped a socket close", extra=core_logger.context(user_id=payload.user_id)
        )
        return
    platform_runtime.get_active_platform().realtime.notify(
        websocket_keys.control_key(payload.user_id),
        {
            "session_id": None if payload.session_id is None else str(payload.session_id),
            "except_session_id": None if payload.except_session_id is None else str(payload.except_session_id),
        },
    )
    logger.debug("Announced the end of sockets to every replica", extra=core_logger.context(user_id=payload.user_id))


on_sessions_revoked_close_sockets = best_effort(close_sockets_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the websocket event consumers on the running bus."""
    events.subscribe(sessions_events.SESSIONS_REVOKED, on_sessions_revoked_close_sockets)
