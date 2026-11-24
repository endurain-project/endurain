"""Stand-ins for what a websocket test cannot run for real: a client socket and an unreachable state backend."""

import asyncio
from typing import Any

from fastapi import WebSocketDisconnect
from jasil.backends.state_memory import MemoryState
from jasil.providers import ClockProvider, StateBackendUnavailableError


class FakeWebSocket:
    """A client socket that records what the server sends and closes, and plays back the frames it is given.

    Attributes:
        accepted: Whether the server accepted the connection.
        sent: The JSON messages sent, in order.
        closed_with: The codes the server closed with, in order.
        received: Set once a message was sent, for a test that waits for a delivery on another thread.
        closed: Set once the server closed the socket.
        frames: What ``receive`` plays back, in order; an exception is raised, and once empty ``receive`` waits for
            ever like a quiet client.
        send_failure: Raised by every ``send_json`` when set.
        close_failure: Raised by every ``close`` when set.
        stall_sends: Makes ``send_json`` wait for ever, like a client that stopped reading.
        stall_closes: Makes ``close`` wait for ever.
    """

    def __init__(self, frames: list[dict[str, Any] | BaseException] | None = None) -> None:
        """Create a socket that plays back ``frames``."""
        self.accepted = False
        self.sent: list[dict[str, Any]] = []
        self.closed_with: list[int] = []
        self.received = asyncio.Event()
        self.closed = asyncio.Event()
        self.frames = list(frames or [])
        self.send_failure: BaseException | None = None
        self.close_failure: BaseException | None = None
        self.stall_sends = False
        self.stall_closes = False

    async def accept(self) -> None:
        """Record that the connection was accepted."""
        self.accepted = True

    async def send_json(self, data: Any) -> None:
        """Record a message, or fail or stall as configured."""
        if self.stall_sends:
            await asyncio.Event().wait()
        if self.send_failure is not None:
            raise self.send_failure
        self.sent.append(data)
        self.received.set()

    async def close(self, code: int = 1000) -> None:
        """Record a close, or fail or stall as configured."""
        if self.stall_closes:
            await asyncio.Event().wait()
        if self.close_failure is not None:
            raise self.close_failure
        self.closed_with.append(code)
        self.closed.set()

    async def receive(self) -> dict[str, Any]:
        """Play back the next frame; a client with nothing left to say waits for ever."""
        if not self.frames:
            await asyncio.Event().wait()
        frame = self.frames.pop(0)
        if isinstance(frame, BaseException):
            raise frame
        return frame


def disconnect_frame(code: int = 1001) -> dict[str, Any]:
    """A client leaving, as the receive loop sees it."""
    return {"type": "websocket.disconnect", "code": code}


def data_frame(**fields: Any) -> dict[str, Any]:
    """A data frame from the client (``text=`` or ``bytes=``), which the one-way protocol refuses."""
    return {"type": "websocket.receive", **fields}


def client_left() -> WebSocketDisconnect:
    """The error a socket raises when the client already went."""
    return WebSocketDisconnect()


class UnavailableState(MemoryState):
    """A state backend that cannot be reached: every call raises what a lost Redis connection raises."""

    def incr(self, *_args: Any, **_kwargs: Any) -> int:
        """Fail like an unreachable backend."""
        raise StateBackendUnavailableError("down")

    def set_if_absent(self, *_args: Any, **_kwargs: Any) -> bool:
        """Fail like an unreachable backend."""
        raise StateBackendUnavailableError("down")

    def get_and_delete(self, *_args: Any, **_kwargs: Any) -> bytes | None:
        """Fail like an unreachable backend."""
        raise StateBackendUnavailableError("down")


class CollidingState(MemoryState):
    """A state backend whose first ``set_if_absent`` finds the key taken, as a ticket collision would."""

    def __init__(self, clock: ClockProvider) -> None:
        """Create the backend, reading time from ``clock``, with one collision pending."""
        super().__init__(clock)
        self.collisions_left = 1

    def set_if_absent(self, key: str, value: bytes, ttl_seconds: int | None = None) -> bool:
        """Refuse the first write as if the key existed, then behave normally."""
        if self.collisions_left:
            self.collisions_left -= 1
            return False
        return super().set_if_absent(key, value, ttl_seconds)
