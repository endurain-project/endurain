from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

import auth.security as auth_security
import websocket.manager as websocket_manager

import core.logger as core_logger

# Define the API router
router = APIRouter()


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    token_user_id: Annotated[
        int, Depends(auth_security.validate_websocket_access_token)
    ],
    websocket_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
) -> None:
    """
    Handle WebSocket connections for real-time notifications.

    Establishes authenticated WebSocket connection for receiving
    real-time notifications, MFA requests, and activity updates.

    Args:
        websocket: The WebSocket connection instance.
        user_id: Authenticated user ID from access token.
        websocket_manager: Manager for WebSocket connections.
    """
    await websocket_manager.connect(token_user_id, websocket)

    try:
        while True:
            try:
                # Keep connection alive, handle incoming messages
                await websocket.receive_json()
            except ValueError:
                # Log malformed JSON, keep connection alive
                core_logger.print_to_log(
                    f"Received malformed JSON from user {token_user_id}",
                    "warning",
                )
    except WebSocketDisconnect:
        websocket_manager.disconnect(token_user_id)
