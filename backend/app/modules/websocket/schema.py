"""Pydantic shapes for the websocket routes."""

from pydantic import BaseModel, StrictStr


class WsTicketRead(BaseModel):
    """A single-use ticket that authenticates a websocket handshake.

    Attributes:
        ticket: Opaque, URL-safe ticket, valid for a short time and for one connection.
    """

    ticket: StrictStr
