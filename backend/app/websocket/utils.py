from fastapi import HTTPException, status

import websocket.manager as websocket_manager


async def notify_frontend(
    user_id: int,
    websocket_manager: websocket_manager.WebSocketManager,
    json_data: dict,
) -> bool:
    """
    Send a JSON message to a user's WebSocket connection.

    Attempts to send data to the user's WebSocket. For MFA
    verification, raises an exception if no connection exists.

    Args:
        user_id: The target user's identifier.
        websocket_manager: The WebSocket connection manager.
        json_data: JSON-serializable data to send.

    Returns:
        True if message was sent, False if no connection.

    Raises:
        HTTPException: If MFA_REQUIRED but no connection exists.
    """
    websocket = websocket_manager.get_connection(user_id)
    if websocket:
        await websocket.send_json(json_data)
        return True

    if json_data.get("message") == "MFA_REQUIRED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No WebSocket connection for user {user_id}",
        )
    return False
