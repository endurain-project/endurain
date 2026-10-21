"""WebSocket module for real-time notifications and communication."""

from .manager import WebSocketManager, get_websocket_manager

__all__ = [
    "WebSocketManager",
    "get_websocket_manager",
]
