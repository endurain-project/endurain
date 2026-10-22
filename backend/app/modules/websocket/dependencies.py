"""FastAPI dependencies for the websocket routes."""

from typing import Annotated

from fastapi import Depends
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
