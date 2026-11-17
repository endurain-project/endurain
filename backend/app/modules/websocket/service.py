"""Serving websocket connections and delivering hints to them."""

import asyncio
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect, status

import core.database as core_database
import core.logger as core_logger
import modules.auth.sessions.integration_service as sessions_integration
import modules.websocket.manager as websocket_manager

logger = core_logger.get_logger(__name__)

# A revoked session closes its sockets at once (``close_revoked_connections``); this is the backstop for a revocation
# that was not announced and for one that happened while the ticket was in flight. The client reconnects with a fresh
# ticket, which needs a valid access token.
MAX_CONNECTION_SECONDS = 900


async def deliver_hint(
    user_id: uuid.UUID, message: dict[str, Any], manager: websocket_manager.WebSocketManager
) -> bool:
    """Send a hint to each of a user's websockets held by this process.

    A connection that fails is dropped from the registry, and the others still get
    the hint.

    Args:
        user_id: The target user.
        message: The JSON-serializable hint.
        manager: The process-local connection registry.

    Returns:
        True when the hint reached at least one connection, False when the user has
        none here or every send failed.
    """
    connections = manager.get_connections(user_id)
    if not connections:
        return False
    failures = await websocket_manager.send_json_to_all(connections, message)
    for _, err in failures:
        logger.debug(
            "Websocket push failed; the durable record is unaffected",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )
    manager.discard_failed(failures)
    return len(failures) < len(connections)


def has_live_session(user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    """Say whether a user's session still exists and has not expired.

    Opens its own short-lived database session, so nothing is held while the socket lives. It blocks on the
    database, so the caller runs it off the event loop.

    Args:
        user_id: The user the ticket was issued to.
        session_id: The session the ticket was issued for.

    Returns:
        True when the session exists, belongs to the user and has not expired.
    """
    with core_database.SessionLocal() as db:
        session = sessions_integration.get_session_by_id_not_expired(session_id, db)
    return session is not None and session.user_id == user_id


async def close_revoked_connections(
    user_id: uuid.UUID,
    session_id: uuid.UUID | None,
    except_session_id: uuid.UUID | None,
    manager: websocket_manager.WebSocketManager,
) -> None:
    """Close the websockets of a user's revoked sessions that this process holds.

    Args:
        user_id: The user whose sessions were revoked.
        session_id: The one revoked session, or None for every session of the user.
        except_session_id: With no ``session_id``, the session that was kept.
        manager: The process-local connection registry.
    """
    for websocket in manager.get_session_connections(user_id, session_id, except_session_id):
        manager.disconnect(user_id, websocket)
        await websocket_manager.close_quietly(websocket, websocket_manager.SESSION_ENDED_CLOSE_CODE, user_id)


async def serve_connection(
    websocket: WebSocket, user_id: uuid.UUID, session_id: uuid.UUID, manager: websocket_manager.WebSocketManager
) -> None:
    """Register an authenticated connection and keep it open until the client leaves.

    Traffic is one-way: the client has nothing to send, so a data frame is a protocol
    violation and closes the connection; control frames are enough to notice a closed one.
    The connection is closed after ``MAX_CONNECTION_SECONDS`` and unregistered however
    the loop ends.

    Args:
        websocket: The connection to serve.
        user_id: The authenticated owner of the connection.
        session_id: The session the connection was opened for; its revocation closes the connection.
        manager: The process-local connection registry.
    """
    await manager.connect(user_id, session_id, websocket)
    try:
        async with asyncio.timeout(MAX_CONNECTION_SECONDS):
            while (frame := await websocket.receive())["type"] != "websocket.disconnect":
                if frame.get("text") is not None or frame.get("bytes") is not None:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    break
    except TimeoutError:
        await websocket.close(code=status.WS_1001_GOING_AWAY)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, websocket)
