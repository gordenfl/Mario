from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .remote_peer import RemotePeer


def compute_spawn_xy(spawn: str, level_length_tiles: int, viewport_w: float) -> Tuple[float, float]:
    """Match client/main.py compute_spawn_position (world pixels, top-left origin)."""
    base_y = 32 * 11
    if spawn == "right":
        if level_length_tiles:
            spawn_x = max((level_length_tiles - 3) * 32, viewport_w - 96)
        else:
            spawn_x = viewport_w - 96
    else:
        spawn_x = 48.0
    return float(spawn_x), float(base_y)


def build_remote_peers(
    room_ready: dict, local_username: str, level_length_tiles: int, viewport_w: float
) -> Dict[str, RemotePeer]:
    remotes: Dict[str, RemotePeer] = {}
    for player in room_ready.get("players", []) or []:
        un = player.get("username")
        if not un or un == local_username:
            continue
        rp = RemotePeer(username=un)
        spawn = player.get("spawn", "right")
        sx, sy = compute_spawn_xy(spawn, level_length_tiles, viewport_w)
        rp.x, rp.y = sx, sy
        rp.visible = True
        remotes[un] = rp
    return remotes


def build_udp_username_map(room_ready: dict, local_username: str) -> Tuple[Dict[int, str], int | None]:
    """Map UDP client_id -> username; local id prefers `players` row matching `local_username`."""
    udp_map: Dict[int, str] = {}
    local_id: int | None = None
    for player in room_ready.get("players", []) or []:
        un = player.get("username")
        cid = player.get("client_id")
        if isinstance(cid, int) and un:
            udp_map[cid] = un
            if un == local_username:
                local_id = cid
    udp_info = room_ready.get("udp")
    if isinstance(udp_info, dict) and local_id is None:
        cid = udp_info.get("client_id")
        if isinstance(cid, int):
            local_id = cid
    return udp_map, local_id


def collect_udp_state_kivy(mario) -> dict:
    flags = 0
    if getattr(mario, "on_ground", False):
        flags |= 0b0001
    if getattr(mario, "in_jump", False):
        flags |= 0b0010
    return {
        "x": mario.rect.x,
        "y": mario.rect.y,
        "vx": mario.vel.x,
        "vy": mario.vel.y,
        "flags": flags,
        "heading": int(getattr(mario, "heading", 1) or 1),
    }


def collect_tcp_state_kivy(mario) -> dict:
    return {
        "position": [mario.rect.x, mario.rect.y],
        "velocity": [mario.vel.x, mario.vel.y],
        "hp": getattr(mario, "hp", 30),
        "power": getattr(mario, "power_state", 0),
        "score": 0,
        "dying": getattr(mario, "dead", False),
        "death_timer": 0,
    }
