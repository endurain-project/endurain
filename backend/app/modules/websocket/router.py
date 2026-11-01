"""WebSocket routes: the ticket that authenticates a connection, and the connection itself."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security, WebSocket, WebSocketException, status
from starlette.concurrency import run_in_threadpool

import core.attempt_state as core_attempt_state
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.websocket.dependencies as websocket_dependencies
import modules.websocket.manager as websocket_manager
import modules.websocket.schema as websocket_schema
import modules.websocket.service as websocket_service
import modules.websocket.ticket_store as websocket_ticket_store

router = APIRouter()


@router.post(
    "/ticket",
    response_model=websocket_schema.WsTicketRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def issue_ws_ticket(
    request: Request,
    user_id: auth_dependencies.CurrentUserId,
    ticket_store: Annotated[
        websocket_ticket_store.WsTicketStore,
        Depends(websocket_dependencies.get_ws_ticket_store),
    ],
) -> websocket_schema.WsTicketRead:
    """Issue a short-lived WebSocket authentication ticket.

    Returns a single-use opaque ticket valid for 30 seconds,
    bound to the authenticated user. Use the ticket as the
    ?ticket= query parameter when connecting to the WebSocket
    endpoint, so the real access token never appears in a URL.

    Args:
        request: The request, which the rate limiter keys on.
        user_id: Authenticated user ID from auth dependency.
        ticket_store: WsTicketStore for issuing tickets.

    Returns:
        The ticket.
    """
    return websocket_schema.WsTicketRead(ticket=ticket_store.create_ticket(user_id))


@router.websocket("", dependencies=[Depends(websocket_dependencies.require_allowed_origin)])
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: Annotated[str, Query(alias="ticket", min_length=1, max_length=64)],
    ticket_store: Annotated[
        websocket_ticket_store.WsTicketStore,
        Depends(websocket_dependencies.get_ws_ticket_store),
    ],
    manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
) -> None:
    """Handle WebSocket connections for real-time hints.

    Refuses a browser origin the API does not serve, then validates the short-lived ticket before accepting the connection, then serves an
    authenticated WebSocket that receives "something changed, refetch" hints. The ticket
    is consumed on first use (single-use). A ticket store that cannot be reached closes the
    connection with ``1013`` so the client retries. The ticket lookup goes to the shared state, so
    it runs off the event loop.

    Args:
        websocket: The WebSocket connection instance.
        ticket: Single-use ticket from ?ticket= query param.
        ticket_store: WsTicketStore for ticket validation.
        manager: Manager for WebSocket connections.
    """
    try:
        user_id = await run_in_threadpool(ticket_store.consume_ticket, ticket)
    except core_attempt_state.StateUnavailableError as err:
        raise WebSocketException(
            code=status.WS_1013_TRY_AGAIN_LATER,
            reason="Ticket storage unavailable",
        ) from err
    if user_id is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid or expired ticket",
        )

    await websocket_service.serve_connection(websocket, user_id, manager)
