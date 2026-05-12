"""Domain models for the multiplayer game server."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

ROOM_PHASE_WAITING = "waiting"
ROOM_PHASE_FIGHTING = "fighting"


@dataclass
class ClientSession:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    username: Optional[str] = None
    room_id: Optional[str] = None
    hp: int = 30
    udp_id: Optional[int] = None

    @property
    def peername(self) -> str:
        try:
            return f"{self.writer.get_extra_info('peername')}"
        except Exception:
            return self.id


@dataclass
class UdpClientInfo:
    token: str
    client_index: int
    address: Optional[Tuple[str, int]] = None
    last_seq: int = -1
    last_timestamp: int = 0
    next_server_seq: int = 0


@dataclass
class Room:
    room_id: str
    phase: str = ROOM_PHASE_WAITING
    members: Dict[str, ClientSession] = field(default_factory=dict)
    active_drops: Dict[str, Dict] = field(default_factory=dict)
    broken_tiles: set = field(default_factory=set)
    collected_floating_coins: set = field(default_factory=set)
    game_over: bool = False
    result: Optional[Dict[str, str]] = None
    udp_clients: Dict[str, UdpClientInfo] = field(default_factory=dict)
    udp_client_index_map: Dict[int, str] = field(default_factory=dict)
    latest_states: Dict[str, dict] = field(default_factory=dict)
    projectiles: Dict[int, dict] = field(default_factory=dict)
    projectile_counter: int = 0

    def is_full(self) -> bool:
        return len(self.members) >= 2

    def is_empty(self) -> bool:
        return len(self.members) == 0

    def add_member(self, client: ClientSession) -> None:
        self.members[client.id] = client
        client.room_id = self.room_id

    def remove_member(self, client_id: str) -> None:
        self.members.pop(client_id, None)

    def others(self, client_id: str):
        for cid, member in self.members.items():
            if cid != client_id:
                yield member
