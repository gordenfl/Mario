"""UDP messaging helpers shared by the multiplayer server."""

from __future__ import annotations

import struct
import time
from typing import Tuple

MSG_HELLO = 0x00
MSG_PLAYER_STATE = 0x01
MSG_PROJECTILE_STATE = 0x02
MSG_ACTION = 0x03
MSG_HELLO_ACK = 0x80

HEADER_STRUCT = struct.Struct("!BBHI")


def current_millis() -> int:
    return int(time.time() * 1000) & 0xFFFFFFFF


def pack_message(msg_type: int, client_id: int, seq: int, timestamp: int, payload: bytes = b"") -> bytes:
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes-like")
    header = HEADER_STRUCT.pack(msg_type & 0xFF, client_id & 0xFF, seq & 0xFFFF, timestamp & 0xFFFFFFFF)
    return header + payload


def unpack_message(data: bytes) -> Tuple[int, int, int, int, bytes]:
    if len(data) < HEADER_STRUCT.size:
        raise ValueError("packet too short")
    msg_type, client_id, seq, timestamp = HEADER_STRUCT.unpack_from(data)
    payload = data[HEADER_STRUCT.size :]
    return msg_type, client_id, seq, timestamp, payload


