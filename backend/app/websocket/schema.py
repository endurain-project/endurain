from fastapi import WebSocket
from typing import Dict


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_message(self, user_id: int, message: str):
        if user_id in self.active_connections:
            websocket = self.active_connections[user_id]
            await websocket.send_json(message)

    async def broadcast(self, message: str):
        for websocket in self.active_connections.values():
            await websocket.send_json(message)

    def get_connection(self, user_id: int) -> WebSocket | None:
        return self.active_connections.get(user_id)


def get_websocket_manager():
    return websocket_manager


websocket_manager = WebSocketManager()
