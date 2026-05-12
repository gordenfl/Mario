"""Dispatch inbound JSON line messages to session or room modules."""

from __future__ import annotations

from typing import Any, Dict

from interfaces import RoomPort, SessionPort
from models import ClientSession


class TcpDispatch:
    def __init__(self, sessions: SessionPort, rooms: RoomPort):
        self._sessions = sessions
        self._rooms = rooms

    async def handle_message(self, client: ClientSession, message: Dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type == "login":
            await self._sessions.handle_login(client, message)
        elif msg_type == "list_rooms":
            await self._sessions.send_rooms_snapshot(client)
        elif msg_type == "create_room":
            await self._rooms.handle_create_room(client)
        elif msg_type == "join_room":
            await self._rooms.handle_join_room(client, message)
        elif msg_type == "leave_room":
            await self._rooms.handle_leave_room(client)
        elif msg_type == "state_update":
            await self._rooms.handle_state_update(client, message)
        elif msg_type == "bullet_event":
            await self._rooms.forward_to_room(client, message)
        elif msg_type == "player_hit":
            await self._rooms.handle_player_hit(client, message)
        elif msg_type == "player_fall":
            await self._rooms.handle_player_fall(client, message)
        elif msg_type == "drop_collected":
            await self._rooms.handle_drop_collected(client, message)
        elif msg_type == "drop_collision":
            await self._rooms.handle_drop_collision(client, message)
        elif msg_type == "tile_break":
            await self._rooms.handle_tile_break(client, message)
        elif msg_type == "floating_coin_collected":
            await self._rooms.handle_floating_coin_collected(client, message)
        else:
            await self._sessions.send_error(client, "unknown_type", f"Unknown message type: {msg_type}")
