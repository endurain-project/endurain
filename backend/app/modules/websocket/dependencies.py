"""FastAPI dependencies for the websocket routes."""

from typing import Annotated

from fastapi import Depends, WebSocket, WebSocketException, status
from jasil.providers import StateProvider

import core.dependencies as core_dependencies
import modules.websocket.ticket_store as websocket_ticket_store


def get_ws_ticket_store(
    state: Annotated[StateProvider, Depends(core_dependencies.get_platform_state)],
) -> websocket_ticket_store.WsTicketStore:
    """Provide the ticket store over the platform state.

    Args:
        state: The platform state provider.

    Returns:
        A ticket store backed by that state.
    """
    return websocket_ticket_store.WsTicketStore(state)


def require_allowed_origin(websocket: WebSocket) -> None:
    """Refuse a browser connection that comes from an origin the API does not serve.

    Browsers attach the ``Origin`` header to a websocket handshake and do not apply
    CORS to it, so a page on another site could otherwise open the socket with the
    user's credentials. A client that sends no ``Origin`` is not a browser and is
    let through; the ticket still authenticates it. The allowed origins are the CORS
    ones, set at startup; when they are missing every browser origin is refused.

    Args:
        websocket: The connection being opened.

    Raises:
        WebSocketException: With a policy-violation close code when the origin is not allowed.
    """
    origin = websocket.headers.get("origin")
    if origin is None:
        return
    if origin not in getattr(websocket.app.state, "cors_allow_origins", ()):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Origin not allowed")
