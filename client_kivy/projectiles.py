from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .rect import Rect
from .level import TILE, Level

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from client.network.protocol import (  # noqa: E402
    PROJECTILE_FLAG_DESPAWN,
    PROJECTILE_FLAG_UPDATE,
)


class Fireball:
    """Authoritative sim matches pygame `entities.fireball.Fireball`; remotes driven by UDP state."""

    GRAVITY = 0.45
    BOUNCE_FACTOR = 1.0
    MAX_LIFETIME_FRAMES = 360

    def __init__(
        self,
        key: str,
        owner: str,
        projectile_id: Optional[int],
        x: float,
        y: float,
        vx: float,
        vy: float,
        level: Level,
        base_speed: float = 8.0,
    ) -> None:
        self.key = key
        self.owner = owner
        self.projectile_id = projectile_id
        self.level = level
        self.base_speed = max(0.1, base_speed)
        diag_speed = self.base_speed / math.sqrt(2)
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.direction = 1 if self.vx >= 0 else -1
        self.bounce_vertical_speed = diag_speed * abs(self.BOUNCE_FACTOR)
        self.rect = Rect(0.0, 0.0, 16.0, 16.0)
        self.rect.centerx = self.x
        self.rect.centery = self.y
        self.lifetime_frames = 0
        self.bounces = 0
        self.hit_wall = False

    def authoritative(self, online: bool, local_username: str) -> bool:
        if not online:
            return True
        return self.owner == local_username

    def apply_network_state(self, state: dict) -> None:
        self.x = float(state.get("x", self.x))
        self.y = float(state.get("y", self.y))
        new_vx = float(state.get("vx", self.vx))
        if new_vx != 0:
            self.direction = 1 if new_vx > 0 else -1
        self.vx = new_vx
        self.vy = float(state.get("vy", self.vy))
        self.rect.centerx = self.x
        self.rect.centery = self.y
        if int(state.get("flags", 0)) & PROJECTILE_FLAG_DESPAWN:
            self.hit_wall = True

    def update_simulation(self) -> None:
        self.vy += self.GRAVITY
        self.x += self.vx
        self.y += self.vy
        self.rect.centerx = self.x
        self.rect.centery = self.y
        self._resolve_ground_collision()
        self.lifetime_frames += 1

    def _resolve_ground_collision(self) -> None:
        if self.vy >= 0:
            bottom_x = self.rect.centerx
            bottom_y = self.rect.bottom + 1
            if self.level.is_solid_at_pixel(bottom_x, bottom_y):
                tile_y = int(bottom_y // TILE)
                tile_top = tile_y * TILE
                self.y = tile_top - self.rect.h * 0.5 - 1
                self.rect.centery = self.y
                self.vy = -self.bounce_vertical_speed
                self.bounces += 1
        left_x = self.rect.left - 1
        right_x = self.rect.right + 1
        mid_y = self.rect.centery
        if self.level.is_solid_at_pixel(left_x, mid_y):
            self.hit_wall = True
        elif self.level.is_solid_at_pixel(right_x, mid_y):
            self.hit_wall = True

    def should_despawn(self, level_width: float) -> bool:
        if self.rect.right < 0 or self.rect.left > level_width:
            return True
        if self.lifetime_frames > self.MAX_LIFETIME_FRAMES:
            return True
        return self.hit_wall


class ProjectileSystem:
    def __init__(self) -> None:
        self.by_key: Dict[str, Fireball] = {}
        self._offline_counter = 0

    def clear(self) -> None:
        self.by_key.clear()
        self._offline_counter = 0

    def spawn_offline(self, x: float, y: float, direction: int, level: Level) -> None:
        self._offline_counter += 1
        key = f"local_{self._offline_counter}"
        diag_speed = 8.0 / math.sqrt(2)
        vx = diag_speed * (1 if direction >= 0 else -1)
        vy = diag_speed
        self.by_key[key] = Fireball(
            key=key,
            owner="",
            projectile_id=None,
            x=x,
            y=y,
            vx=vx,
            vy=vy,
            level=level,
        )

    def upsert_from_udp(self, proj_key: str, owner: str, state: dict, level: Level) -> None:
        flags = int(state.get("flags", 0))
        if flags & PROJECTILE_FLAG_DESPAWN:
            self.by_key.pop(proj_key, None)
            return
        pid = state.get("projectile_id")
        if pid is None:
            return
        if proj_key not in self.by_key:
            self.by_key[proj_key] = Fireball(
                key=proj_key,
                owner=owner,
                projectile_id=int(pid),
                x=float(state.get("x", 0)),
                y=float(state.get("y", 0)),
                vx=float(state.get("vx", 0)),
                vy=float(state.get("vy", 0)),
                level=level,
            )
        else:
            self.by_key[proj_key].apply_network_state(state)
            self.by_key[proj_key].owner = owner
            self.by_key[proj_key].projectile_id = int(pid)

    def step(
        self,
        level: Level,
        level_width: float,
        *,
        online: bool,
        local_username: str,
        remotes: dict,
    ) -> List[Tuple[int, float, float, float, float, int, Optional[str]]]:
        """Simulate owner projectiles; returns UDP payloads for authoritative bullets."""
        out: List[Tuple[int, float, float, float, float, int, Optional[str]]] = []
        to_remove: List[str] = []

        for key, fb in list(self.by_key.items()):
            if not fb.authoritative(online, local_username):
                continue
            fb.update_simulation()
            hit_target: Optional[str] = None
            for un, rp in remotes.items():
                if un == local_username or not getattr(rp, "visible", False):
                    continue
                rr = Rect(rp.x, rp.y, rp.w, rp.h)
                if fb.rect.colliderect(rr):
                    hit_target = un
                    break
            despawn = hit_target is not None or fb.should_despawn(level_width)
            flags = PROJECTILE_FLAG_UPDATE
            if despawn:
                flags |= PROJECTILE_FLAG_DESPAWN
            pid = fb.projectile_id
            if online and pid is not None:
                out.append((pid, fb.x, fb.y, fb.vx, fb.vy, flags, hit_target))
            if despawn:
                to_remove.append(key)

        for key in to_remove:
            self.by_key.pop(key, None)
        return out

    def cull_hits_local_player(
        self,
        mario_rect: Rect,
        *,
        online: bool,
        local_username: str,
        mario_dead: bool,
    ) -> None:
        if mario_dead:
            return
        for key, fb in list(self.by_key.items()):
            if fb.authoritative(online, local_username):
                continue
            if fb.rect.colliderect(mario_rect):
                self.by_key.pop(key, None)
