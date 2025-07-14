from fastapi import HTTPException, status

import websocket.schema as websocket_schema


async def notify_frontend(
    user_id: int, websocket_manager: websocket_schema.WebSocketManager, json_data: dict
):
    """
    Sends a JSON message to the frontend via an active WebSocket connection for a specific user.

    Args:
        user_id (int): The ID of the user to notify.
        websocket_manager (websocket_schema.WebSocketManager): The manager handling WebSocket connections.
        json_data (dict): The JSON-serializable data to send to the frontend.

    Raises:
        HTTPException: If there is no active WebSocket connection for the specified user.
    """
    # Check if the user has an active WebSocket connection

    websocket = websocket_manager.get_connection(user_id)
    if websocket:
        await websocket.send_json(json_data)
    else:
        if json_data.get("message") == "MFA_REQUIRED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No active WebSocket connection for user {user_id}",
            )
