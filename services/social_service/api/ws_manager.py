from typing import Dict, List
from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder


class ConnectionManager:
    """
    Stores active WebSocket connections.

    Structure:
    {
        conversation_id: {
            user_id: [websocket_connection_1, websocket_connection_2]
        }
    }

    A list is used because the same user may open the app on phone + emulator.
    FastAPI does not remember connected chat users automatically.
    This manager stores live users by conversation_id.
    When User A sends a message, this manager broadcasts it to User A and User B instantly.
    """

    def __init__(self):
        self.active_connections: Dict[int, Dict[str, List[WebSocket]]] = {}

    async def connect(self, conversation_id: int, user_id: str, websocket: WebSocket):
        await websocket.accept()

        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = {}

        if user_id not in self.active_connections[conversation_id]:
            self.active_connections[conversation_id][user_id] = []

        self.active_connections[conversation_id][user_id].append(websocket)

    def disconnect(self, conversation_id: int, user_id: str, websocket: WebSocket):
        conversation = self.active_connections.get(conversation_id)

        if not conversation:
            return

        sockets = conversation.get(user_id, [])

        if websocket in sockets:
            sockets.remove(websocket)

        if not sockets and user_id in conversation:
            del conversation[user_id]

        if not conversation:
            del self.active_connections[conversation_id]

    async def send_to_user(self, conversation_id: int, user_id: str, event: dict):
        sockets = (
            self.active_connections
            .get(conversation_id, {})
            .get(user_id, [])
        )

        for socket in list(sockets):
            try:
                await socket.send_json(jsonable_encoder(event))
            except Exception:
                self.disconnect(conversation_id, user_id, socket)

    async def broadcast_to_conversation(self, conversation_id: int, event: dict):
        conversation = self.active_connections.get(conversation_id, {})

        for user_id, sockets in list(conversation.items()):
            for socket in list(sockets):
                try:
                    await socket.send_json(jsonable_encoder(event))
                except Exception:
                    self.disconnect(conversation_id, user_id, socket)


manager = ConnectionManager()