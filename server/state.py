"""Mutable server-wide state shared by modules under a single asyncio lock."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from models import ClientSession, Room


@dataclass
class ServerState:
    host: str
    port: int
    udp_port: int
    clients: Dict[str, ClientSession] = field(default_factory=dict)
    rooms: Dict[str, Room] = field(default_factory=dict)
    room_drop_tasks: Dict[str, asyncio.Task] = field(default_factory=dict)
    pending_udp_tokens: Dict[str, Tuple[str, str, int]] = field(default_factory=dict)
    udp_transport: Optional[asyncio.transports.DatagramTransport] = None
    udp_addr_map: Dict[Tuple[str, int], Tuple[str, str]] = field(default_factory=dict)
    udp_index_map: Dict[Tuple[str, int], str] = field(default_factory=dict)
    room_snapshot_tasks: Dict[str, asyncio.Task] = field(default_factory=dict)
