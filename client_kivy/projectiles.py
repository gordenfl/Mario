from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .rect import Rect
from .level import TILE, Level


@dataclass
class Fireball:
    rect: Rect
    vx: float
    ttl: int = 240

    def update(self, level: Level) -> bool:
        """Returns alive."""
        self.rect.move_ip(self.vx, 0)
        self.ttl -= 1
        if self.ttl <= 0:
            return False

        # Collide with solid tiles using a few sample points.
        sample = [
            (self.rect.centerx, self.rect.centery),
            (self.rect.left, self.rect.centery),
            (self.rect.right, self.rect.centery),
        ]
        for px, py in sample:
            if level.is_solid_at_pixel(px, py):
                return False
        return True


class ProjectileSystem:
    def __init__(self) -> None:
        self.fireballs: List[Fireball] = []

    def spawn_fireball(self, x: float, y: float, direction: int) -> None:
        speed = 8.0
        w = 16
        h = 16
        rect = Rect(x - w * 0.5, y - h * 0.5, w, h)
        self.fireballs.append(Fireball(rect=rect, vx=float(direction) * speed))

    def update(self, level: Level) -> None:
        self.fireballs = [fb for fb in self.fireballs if fb.update(level)]

