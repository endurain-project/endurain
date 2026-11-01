"""Serving websocket connections and delivering hints to them."""

import asyncio

from fastapi import WebSocket, WebSocketDisconnect, status

import core.logger as core_logger
import modules.websocket.manager as websocket_manager

logger = core_logger.get_logger(__name__)

# The ticket is checked only at connect time, so a connection is closed after this long: the client
# reconnects with a fresh ticket, which needs a valid access token, and a revoked session loses its socket.
MAX_CONNECTION_SECONDS = 900


async def deliver_hint(user_id: int, message: dict, manager: websocket_manager.WebSocketManager) -> bool:
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


async def serve_connection(websocket: WebSocket, user_id: int, manager: websocket_manager.WebSocketManager) -> None:
    """Register an authenticated connection and keep it open until the client leaves.

    Traffic is one-way: the client has nothing to send, so a data frame is a protocol
    violation and closes the connection; control frames are enough to notice a closed one.
    The connection is closed after ``MAX_CONNECTION_SECONDS`` and unregistered however
    the loop ends.

    Args:
        websocket: The connection to serve.
        user_id: The authenticated owner of the connection.
        manager: The process-local connection registry.
    """
    await manager.connect(user_id, websocket)
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
