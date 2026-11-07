"""WebSocket routes: the ticket that authenticates a connection, and the connection itself."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, Security, WebSocket, WebSocketException, status
from starlette.concurrency import run_in_threadpool

import core.attempt_state as core_attempt_state
import core.cache_control as core_cache_control
import core.network as core_network
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
    response: Response,
    user_id: auth_dependencies.CurrentUserId,
    session_id: auth_dependencies.CurrentSessionId,
    ticket_store: Annotated[
        websocket_ticket_store.WsTicketStore,
        Depends(websocket_dependencies.get_ws_ticket_store),
    ],
) -> websocket_schema.WsTicketRead:
    """Issue a short-lived WebSocket authentication ticket.

    Returns a single-use opaque ticket valid for 30 seconds,
    bound to the authenticated user and session. Use the ticket as the
    ?ticket= query parameter when connecting to the WebSocket
    endpoint, so the real access token never appears in a URL.

    Args:
        request: The request, which the rate limiter keys on.
        response: The response, marked as not cacheable because it carries the credential.
        user_id: Authenticated user ID from auth dependency.
        session_id: Session of the access token, which the socket ends with.
        ticket_store: WsTicketStore for issuing tickets.

    Returns:
        The ticket.
    """
    core_cache_control.set_no_store(response)
    return websocket_schema.WsTicketRead(ticket=ticket_store.create_ticket(user_id, session_id))


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

    Refuses a browser origin the API does not serve, then counts the handshake against the client
    network and refuses it with ``1013`` past ``MAX_HANDSHAKES_PER_WINDOW`` a window, then validates the
    short-lived ticket before accepting the connection, then serves an authenticated WebSocket that
    receives "something changed, refetch" hints. The ticket is consumed on first use (single-use) and
    binds the socket to the session it was issued for; a ticket whose session no longer exists is accepted and closed with ``4401``, as a revocation would. A ticket store that cannot be reached closes the
    connection with ``1013`` so the client retries. The counter and the ticket lookup go to the shared
    state, so they run off the event loop.

    Args:
        websocket: The WebSocket connection instance.
        ticket: Single-use ticket from ?ticket= query param.
        ticket_store: WsTicketStore for ticket validation.
        manager: Manager for WebSocket connections.
    """
    network = core_network.client_network(core_network.get_ip_address(websocket))
    try:
        within_limit = await run_in_threadpool(ticket_store.allow_handshake, network)
        owner = await run_in_threadpool(ticket_store.consume_ticket, ticket) if within_limit else None
    except core_attempt_state.StateUnavailableError as err:
        raise WebSocketException(
            code=status.WS_1013_TRY_AGAIN_LATER,
            reason="Ticket storage unavailable",
        ) from err
    if not within_limit:
        raise WebSocketException(code=status.WS_1013_TRY_AGAIN_LATER, reason="Too many connection attempts")
    if owner is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid or expired ticket",
        )

    if not await run_in_threadpool(websocket_service.has_live_session, owner.user_id, owner.session_id):
        # The session ended after the ticket was issued, so no close event will ever reach this socket.
        await websocket.accept()
        await websocket.close(code=websocket_manager.SESSION_ENDED_CLOSE_CODE)
        return

    await websocket_service.serve_connection(websocket, owner.user_id, owner.session_id, manager)
