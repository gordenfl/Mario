from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from .rect import Rect
from .level import TILE, Level

_CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"
if str(_CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CLIENT_DIR))
from jump_constants import (  # noqa: E402
    MARIO_GRAVITY,
    apply_jump_trait_end_of_frame,
    jump_deacceleration_height,
)


@dataclass
class Vec2:
    x: float = 0.0
    y: float = 0.0


class Mario:
    def __init__(self, x_tiles: float, y_tiles: float, level: Level) -> None:
        self.level = level
        self.rect = Rect(x_tiles * TILE, y_tiles * TILE, 32, 64)
        self.vel = Vec2(0.0, 0.0)
        self.gravity = MARIO_GRAVITY
        self.on_ground = False
        self.heading = 1  # 1 right, -1 left
        # Keep parity with legacy client powerUpState: 0 small, 1 big, 2 fire.
        # Kivy client currently starts as big+fire visuals.
        self.power_state = 2
        self.obey_gravity = True
        self.in_jump = False
        self.jump_start_y = 0.0
        self.jump_deaccel_height = jump_deacceleration_height(self.gravity)

        # Controls
        self.move_dir = 0.0  # [-1..1]
        self.jump_requested = False
        self.jump_held = False

        # Fire
        self.fire_requested = False
        self.fire_cooldown = 0

        self.hp = 30
        self.dead = False
        self.coins = 0
        self.mushrooms_eaten = 0

    def apply_controls(self, *, move_dir: float, jump: bool, fire: bool) -> None:
        if self.dead:
            return
        self.move_dir = max(-1.0, min(1.0, float(move_dir)))
        self.jump_requested = bool(jump)
        self.jump_held = bool(jump)
        self.fire_requested = bool(fire)
        if self.move_dir != 0:
            self.heading = 1 if self.move_dir > 0 else -1

    def update(self) -> None:
        if self.dead:
            return
        # Horizontal acceleration / friction
        # Match pygame `traits.go.GoTrait` (maxVel 3.2, accelVel 0.4, decelVel 0.25).
        max_v = 3.2
        accel = 0.4
        decel = 0.25
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

        # Pygame frame order: moveMario -> applyGravity -> JumpTrait.jump (Input).
        self._move_y(self.vel.y)
        self._move_x(self.vel.x)
        self._clamp_to_level_horizontal()

        if self.obey_gravity:
            self.vel.y += self.gravity

        # Shared JumpTrait.jump (after move + gravity; initial vel applies next tick).
        (
            self.vel.y,
            self.on_ground,
            self.jump_start_y,
            self.in_jump,
            self.obey_gravity,
        ) = apply_jump_trait_end_of_frame(
            jumping=self.jump_requested,
            on_ground=self.on_ground,
            rect_y=self.rect.y,
            jump_start_y=self.jump_start_y,
            vel_y=self.vel.y,
            in_jump=self.in_jump,
            obey_gravity=self.obey_gravity,
            deaccel_height=self.jump_deaccel_height,
        )

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

    def _clamp_to_level_horizontal(self) -> None:
        """Keep Mario inside the level width (same span as camera scroll)."""
        width_px = max(1, self.level.length_tiles) * TILE
        if self.rect.left < 0.0:
            self.rect.left = 0.0
            self.vel.x = 0.0
        elif self.rect.right > width_px:
            self.rect.right = float(width_px)
            self.vel.x = 0.0

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
                    # Hit tile from below: allow bricks to break.
                    # Use the tile directly above Mario's top edge.
                    self.level.handle_tile_hit_from_below(tx, ty, self)
                    self.rect.top = tile.bottom
                self.vel.y = 0.0
                if self.on_ground:
                    # Legacy JumpTrait.reset()
                    self.in_jump = False
                    self.obey_gravity = True
                break

