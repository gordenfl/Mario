from __future__ import annotations

import random
from typing import List

from .level import TILE, Level
from .rect import Rect

# Match pygame `SkyDrop` / `SkyMushroom` sizes and tuning.
MW, MH = 28, 28
GRAVITY_FALL = 0.55
GRAVITY_WALK = 0.6
SPEED = 1.2
LANDING_COOLDOWN_FRAMES = 2


class MushroomEntity:
    """Red mushroom: falls from spawn, then walks with gravity (pipe tops + ledges)."""

    __slots__ = (
        "rect",
        "mode",
        "vel_y",
        "direction",
        "pos_x",
        "pos_y",
        "landing_cooldown",
        "was_on_ground",
    )

    def __init__(self, center_x: float, top_y: float) -> None:
        self.rect = Rect(0.0, 0.0, float(MW), float(MH))
        self.rect.centerx = center_x
        self.rect.top = top_y
        self.mode = "fall"
        self.vel_y = 0.0
        self.direction = random.choice([-1, 1])
        self.pos_x = float(self.rect.x)
        self.pos_y = float(self.rect.y)
        self.landing_cooldown = 0
        self.was_on_ground = False

    def update(self, level: Level, world_width_px: float) -> bool:
        """Advance physics. Returns True if still alive."""
        if self.mode == "fall":
            return self._update_fall(level, world_width_px)
        return self._update_walk(level, world_width_px)

    def _update_fall(self, level: Level, world_width_px: float) -> bool:
        self.vel_y += GRAVITY_FALL
        self.pos_y += self.vel_y
        self.rect.y = int(self.pos_y)

        if level.is_solid_at_pixel(self.rect.centerx, float(self.rect.bottom + 1)):
            ty = int((self.rect.bottom + 1) // TILE)
            self.rect.bottom = float(ty * TILE)
            self.pos_y = float(self.rect.y)
            self.vel_y = 0.0
            self.mode = "walk"
            self.landing_cooldown = LANDING_COOLDOWN_FRAMES
            self.was_on_ground = True
        self._clamp_x(world_width_px)
        if self.rect.top > 900.0:
            return False
        return True

    def _update_walk(self, level: Level, world_width_px: float) -> bool:
        self.vel_y += GRAVITY_WALK
        self.pos_y += self.vel_y
        self.rect.y = int(self.pos_y)

        below = float(self.rect.bottom + 1)
        on_ground = level.is_solid_at_pixel(self.rect.centerx, below)
        if on_ground:
            ty = int(below // TILE)
            self.rect.bottom = float(ty * TILE)
            self.pos_y = float(self.rect.y)
            self.vel_y = 0.0
            if not self.was_on_ground:
                self.landing_cooldown = LANDING_COOLDOWN_FRAMES
            self.was_on_ground = True
        else:
            self.was_on_ground = False

        prev_x = self.pos_x
        self.pos_x += SPEED * float(self.direction)
        self.rect.x = int(self.pos_x)

        if on_ground:
            foot = float(self.rect.bottom - 4)
            left_wall = level.is_solid_at_pixel(float(self.rect.left - 1), foot)
            right_wall = level.is_solid_at_pixel(float(self.rect.right + 1), foot)
            if self.landing_cooldown > 0:
                self.landing_cooldown -= 1
            elif left_wall or right_wall:
                self.pos_x = prev_x
                self.rect.x = int(self.pos_x)
                self.direction *= -1

        self._clamp_x(world_width_px)

        if self.rect.top > 720.0:
            return False
        return True

    def _clamp_x(self, world_width_px: float) -> None:
        if self.rect.left < 0.0:
            self.rect.left = 0.0
            self.pos_x = float(self.rect.x)
            if self.mode == "walk":
                self.direction = 1
        elif self.rect.right > world_width_px:
            self.rect.right = float(world_width_px)
            self.pos_x = float(self.rect.x)
            if self.mode == "walk":
                self.direction = -1


class MushroomSystem:
    def __init__(self) -> None:
        self.entities: List[MushroomEntity] = []

    def clear(self) -> None:
        self.entities.clear()

    def spawn(self, center_x: float, top_y: float) -> None:
        self.entities.append(MushroomEntity(center_x, top_y))

    def update(self, level: Level, mario_rect: Rect) -> int:
        """Returns number collected by Mario this tick."""
        wpx = max(1, level.length_tiles) * TILE
        alive: List[MushroomEntity] = []
        eaten = 0
        for m in self.entities:
            if not m.update(level, wpx):
                continue
            if m.rect.colliderect(mario_rect):
                eaten += 1
            else:
                alive.append(m)
        self.entities = alive
        return eaten
