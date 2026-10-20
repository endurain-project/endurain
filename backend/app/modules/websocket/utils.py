from fastapi import HTTPException, status

import modules.websocket.manager as websocket_manager
import modules.websocket.manager as websocket_manager_module


async def notify_frontend(
    user_id: int,
    websocket_manager: websocket_manager.WebSocketManager,
    json_data: dict,
) -> bool:
    """
    Send a JSON message to all of a user's WebSocket connections.

    Attempts to send data to the user's WebSocket. For MFA
    verification, raises an exception if no connection exists.

    Args:
        user_id: The target user's identifier.
        websocket_manager: The WebSocket connection manager.
        json_data: JSON-serializable data to send.

    Returns:
        True if the message reached at least one connection, False if there is none.

    Raises:
        HTTPException: If MFA_REQUIRED but no connection exists.
        Exception: The first send failure, when every connection of the user failed.
    """
    connections = websocket_manager.get_connections(user_id)
    if connections:
        failures = await websocket_manager_module.send_json_to_all(connections, json_data)
        if len(failures) == len(connections):
            raise failures[0]
        return True

    if json_data.get("message") == "MFA_REQUIRED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No WebSocket connection for user {user_id}",
        )
    return False
