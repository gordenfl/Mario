from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RemotePeer:
    """Minimal networked avatar state for drawing (synced from UDP/TCP)."""

    username: str
    x: float = 0.0
    y: float = 0.0
    w: float = 32.0
    h: float = 64.0
    vx: float = 0.0
    vy: float = 0.0
    heading: int = 1
    flags: int = 0
    on_ground: bool = True
    anim_tick: int = 0
    visible: bool = False
    last_udp_mono: float = 0.0

    def apply_udp(self, state: dict, timestamp: int | None = None) -> None:
        self.x = float(state.get("x", self.x))
        self.y = float(state.get("y", self.y))
        self.vx = float(state.get("vx", self.vx))
        self.vy = float(state.get("vy", self.vy))
        self.flags = int(state.get("flags", self.flags))
        self.on_ground = bool(self.flags & 0b0001)
        hd = int(state.get("heading", self.heading))
        self.heading = hd if hd != 0 else self.heading
        self.anim_tick += 1
        self.visible = True
        self.last_udp_mono = time.monotonic()

    def apply_tcp_state(self, state: dict) -> None:
        # Lower rate than UDP; skip if UDP was very recent (same idea as pygame RemotePlayer).
        now = time.monotonic()
        if self.last_udp_mono and (now - self.last_udp_mono) < 0.45:
            return
        pos = state.get("position", [self.x, self.y])
        vel = state.get("velocity", [self.vx, self.vy])
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            self.x, self.y = float(pos[0]), float(pos[1])
        if isinstance(vel, (list, tuple)) and len(vel) >= 2:
            self.vx, self.vy = float(vel[0]), float(vel[1])
        self.anim_tick += 1
        self.on_ground = abs(self.vy) < 0.85  # coarse when TCP omits flags
        self.visible = True

    def apply_snapshot_player(self, player: dict) -> None:
        now = time.monotonic()
        if self.last_udp_mono and (now - self.last_udp_mono) < 0.35:
            return
        self.x = float(player.get("x", self.x))
        self.y = float(player.get("y", self.y))
        self.vx = float(player.get("vx", self.vx))
        self.vy = float(player.get("vy", self.vy))
        fl = player.get("flags")
        if isinstance(fl, int):
            self.flags = fl
            self.on_ground = bool(fl & 0b0001)
        hd = player.get("heading")
        if hd is not None:
            self.heading = int(hd) if int(hd) != 0 else self.heading
        self.anim_tick += 1
        self.visible = True
