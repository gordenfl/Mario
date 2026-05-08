from __future__ import annotations

from dataclasses import dataclass

from .rect import Rect
from .level import TILE, Level


@dataclass
class Vec2:
    x: float = 0.0
    y: float = 0.0


class Mario:
    def __init__(self, x_tiles: float, y_tiles: float, level: Level) -> None:
        self.level = level
        self.rect = Rect(x_tiles * TILE, y_tiles * TILE, 32, 64)
        self.vel = Vec2(0.0, 0.0)
        self.gravity = 0.8
        self.on_ground = False
        self.heading = 1  # 1 right, -1 left

        # Controls
        self.move_dir = 0.0  # [-1..1]
        self.jump_requested = False
        self.jump_held = False

        # Fire
        self.fire_requested = False
        self.fire_cooldown = 0

    def apply_controls(self, *, move_dir: float, jump: bool, fire: bool) -> None:
        self.move_dir = max(-1.0, min(1.0, float(move_dir)))
        self.jump_requested = bool(jump)
        self.jump_held = bool(jump)
        self.fire_requested = bool(fire)
        if self.move_dir != 0:
            self.heading = 1 if self.move_dir > 0 else -1

    def update(self) -> None:
        # Horizontal acceleration / friction
        max_v = 3.2
        accel = 0.45
        decel = 0.30
        if abs(self.move_dir) > 0.05:
            target = self.move_dir * max_v
            if self.vel.x < target:
                self.vel.x = min(target, self.vel.x + accel)
            elif self.vel.x > target:
                self.vel.x = max(target, self.vel.x - accel)
        else:
            if self.vel.x > 0:
                self.vel.x = max(0.0, self.vel.x - decel)
            elif self.vel.x < 0:
                self.vel.x = min(0.0, self.vel.x + decel)

        # Jump (up direction on joystick)
        if self.jump_requested and self.on_ground:
            self.vel.y = -11.5
            self.on_ground = False

        # Gravity
        self.vel.y += self.gravity

        # Integrate + collide Y then X (top-left coordinate system)
        self._move_y(self.vel.y)
        self._move_x(self.vel.x)

        if self.fire_cooldown > 0:
            self.fire_cooldown -= 1

    def can_fire(self) -> bool:
        return self.fire_cooldown <= 0

    def consume_fire(self) -> bool:
        if self.fire_requested and self.can_fire():
            self.fire_cooldown = 18
            return True
        return False

    def _move_x(self, dx: float) -> None:
        if dx == 0:
            return
        self.rect.move_ip(dx, 0)
        # Sample collision points along vertical span.
        if dx > 0:
            points = [
                (self.rect.right, self.rect.top + 4),
                (self.rect.right, self.rect.centery),
                (self.rect.right, self.rect.bottom - 2),
            ]
        else:
            points = [
                (self.rect.left, self.rect.top + 4),
                (self.rect.left, self.rect.centery),
                (self.rect.left, self.rect.bottom - 2),
            ]
        for px, py in points:
            if self.level.is_solid_at_pixel(px, py):
                tx = int(px // TILE)
                ty = int(py // TILE)
                tile = self.level.tile_rect(tx, ty)
                if dx > 0:
                    self.rect.right = tile.left
                else:
                    self.rect.left = tile.right
                self.vel.x = 0.0
                break

    def _move_y(self, dy: float) -> None:
        self.on_ground = False
        self.rect.move_ip(0, dy)
        if dy > 0:
            points = [
                (self.rect.left + 4, self.rect.bottom),
                (self.rect.centerx, self.rect.bottom),
                (self.rect.right - 4, self.rect.bottom),
            ]
        else:
            points = [
                (self.rect.left + 4, self.rect.top),
                (self.rect.centerx, self.rect.top),
                (self.rect.right - 4, self.rect.top),
            ]
        for px, py in points:
            if self.level.is_solid_at_pixel(px, py):
                tx = int(px // TILE)
                ty = int(py // TILE)
                tile = self.level.tile_rect(tx, ty)
                if dy > 0:
                    self.rect.bottom = tile.top
                    self.on_ground = True
                else:
                    self.rect.top = tile.bottom
                self.vel.y = 0.0
                break

