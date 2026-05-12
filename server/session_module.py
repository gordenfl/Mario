"""TCP session registry, login, and outbound messaging."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from interfaces import RoomPort
from models import ROOM_PHASE_WAITING, ClientSession
from state import ServerState


class SessionModule:
    def __init__(self, state: ServerState, lock: asyncio.Lock):
        self._state = state
        self._lock = lock
        self._room: Optional[RoomPort] = None

    def attach_room(self, room: RoomPort) -> None:
        self._room = room

    async def handle_login(self, client: ClientSession, message: Dict[str, Any]) -> None:
        username = message.get("username")
        if not username:
            await self.send_error(client, "invalid_username", "Username is required")
            return
        client.username = username
        logging.info("Client %s logged in as %s", client.peername, username)
        await self.send(
            client,
            {
                "type": "login_ok",
                "username": username,
            },
        )
        await self.send_rooms_snapshot(client)

    async def send_rooms_snapshot(self, client: ClientSession) -> None:
        rooms_payload = [
            {
                "room_id": room_id,
                "players": [member.username for member in room.members.values()],
                "is_full": room.is_full(),
                "phase": room.phase,
            }
            for room_id, room in self._state.rooms.items()
            if room.phase == ROOM_PHASE_WAITING and not room.is_full()
        ]
        await self.send(client, {"type": "rooms", "rooms": rooms_payload})

    async def broadcast_rooms_to_lobby(self) -> None:
        async with self._lock:
            recipients = [c for c in self._state.clients.values() if c.username and c.room_id is None]
        for client in recipients:
            await self.send_rooms_snapshot(client)

    async def send(self, client: ClientSession, message: Dict[str, Any]) -> None:
        data = json.dumps(message) + "\n"
        client.writer.write(data.encode("utf-8"))
        try:
            await client.writer.drain()
        except ConnectionResetError:
            pass

    async def send_error(self, client: ClientSession, code: str, message: str) -> None:
        await self.send(client, {"type": "error", "code": code, "message": message})

    async def cleanup_client(self, client: ClientSession) -> None:
        logging.info("Cleaning up client %s", client.username or client.peername)
        if self._room:
            await self._room.handle_leave_room(client)
        try:
            client.writer.close()
            await client.writer.wait_closed()
        except Exception:
            pass
        self._state.clients.pop(client.id, None)
