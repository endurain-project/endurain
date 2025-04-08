from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
import websocket.schema as websocket_schema

# Define the API router
router = APIRouter()


@router.websocket("/{user_id}")
async def websocket_endpoint(
    user_id: int,
    websocket: WebSocket,
    websocket_manager: Annotated[
        websocket_schema.WebSocketManager,
        Depends(websocket_schema.get_websocket_manager),
    ],
):
    # Connect and manage WebSocket connections using the manager
    await websocket_manager.connect(user_id, websocket)

    try:
        while True:
            # Handle incoming messages if necessary (currently just keeping connection alive)
            data = await websocket.receive_json()
    except WebSocketDisconnect:
        # Disconnect using the manager
        websocket_manager.disconnect(user_id)
