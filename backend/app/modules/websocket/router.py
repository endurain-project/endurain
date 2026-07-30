from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, WebSocketException, status

import core.logger as core_logger
import modules.auth.dependencies as auth_dependencies
import modules.websocket.manager as websocket_manager
import modules.websocket.ticket_store as ws_ticket_store

logger = core_logger.get_logger(__name__)

# Define the API router
router = APIRouter()


@router.post("/ticket", response_model=dict[str, str], status_code=201)
def issue_ws_ticket(
    user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    ticket_store: Annotated[
        ws_ticket_store.WsTicketStore,
        Depends(ws_ticket_store.get_ws_ticket_store),
    ],
) -> dict[str, str]:
    """
    Issue a short-lived WebSocket authentication ticket.

    Returns a single-use opaque ticket valid for 30 seconds,
    bound to the authenticated user. Use the ticket as the
    ?ticket= query parameter when connecting to the WebSocket
    endpoint, so the real access token never appears in a URL.

    Args:
        user_id: Authenticated user ID from auth dependency.
        ticket_store: WsTicketStore for issuing tickets.

    Returns:
        JSON object with a single "ticket" key.
    """
    ticket = ticket_store.create_ticket(user_id)
    return {"ticket": ticket}


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: Annotated[str, Query(alias="ticket")],
    ticket_store: Annotated[
        ws_ticket_store.WsTicketStore,
        Depends(ws_ticket_store.get_ws_ticket_store),
    ],
    manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
) -> None:
    """
    Handle WebSocket connections for real-time notifications.

    Validates the short-lived ticket before accepting the
    connection, then establishes an authenticated WebSocket
    for real-time notifications, MFA requests, and activity
    updates. The ticket is consumed on first use (single-use).

    Args:
        websocket: The WebSocket connection instance.
        ticket: Single-use ticket from ?ticket= query param.
        ticket_store: WsTicketStore for ticket validation.
        manager: Manager for WebSocket connections.
    """
    user_id = ticket_store.consume_ticket(ticket)
    if user_id is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid or expired ticket",
        )

    await manager.connect(user_id, websocket)

    try:
        while True:
            try:
                # Keep connection alive, handle incoming messages
                await websocket.receive_json()
            except ValueError:
                # Log malformed JSON, keep connection alive
                logger.warning(f"Received malformed JSON from user {user_id}")
    except WebSocketDisconnect:
        manager.disconnect(user_id)
