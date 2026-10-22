"""Serving websocket connections and delivering hints to them."""

from fastapi import WebSocket, WebSocketDisconnect

import core.logger as core_logger
import modules.websocket.manager as websocket_manager

logger = core_logger.get_logger(__name__)


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

    Traffic is one-way: whatever the client sends is read and discarded, so a closed
    connection is noticed. The connection is unregistered however the loop ends.

    Args:
        websocket: The connection to serve.
        user_id: The authenticated owner of the connection.
        manager: The process-local connection registry.
    """
    await manager.connect(user_id, websocket)
    try:
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, websocket)
