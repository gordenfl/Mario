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
PLAYER_STATE_STRUCT = struct.Struct("!hhhhBb")
VELOCITY_SCALE = 100


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


def pack_player_state(x: float, y: float, vx: float, vy: float, flags: int, heading: int) -> bytes:
    x_i = int(round(x))
    y_i = int(round(y))
    vx_i = int(round(vx * VELOCITY_SCALE))
    vy_i = int(round(vy * VELOCITY_SCALE))
    flags = flags & 0xFF
    heading_i = int(max(-128, min(127, heading)))
    return PLAYER_STATE_STRUCT.pack(x_i, y_i, vx_i, vy_i, flags, heading_i)


def unpack_player_state(payload: bytes) -> dict:
    if len(payload) < PLAYER_STATE_STRUCT.size:
        raise ValueError("player state payload too short")
    x_i, y_i, vx_i, vy_i, flags, heading_i = PLAYER_STATE_STRUCT.unpack_from(payload)
    return {
        "x": x_i,
        "y": y_i,
        "vx": vx_i / VELOCITY_SCALE,
        "vy": vy_i / VELOCITY_SCALE,
        "flags": flags,
        "heading": heading_i,
    }


