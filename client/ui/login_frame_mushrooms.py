"""Two mushrooms walking inside the login title brick frame."""

from __future__ import annotations

import random
from typing import Optional, Tuple

import pygame
from pygame.transform import flip

from ui.wall_title import measure_title_mushroom_floor

_WALK_SPEED = 1.6


class _PatrolMushroom:
    def __init__(
        self,
        sprites,
        floor: pygame.Rect,
        rng: random.Random,
        *,
        speed: float = _WALK_SPEED,
    ):
        self._image = self._load_image(sprites)
        self._w = self._image.get_width() if self._image else 32
        self._h = self._image.get_height() if self._image else 32
        self._ground_y = floor.bottom - self._h
        # Walk the full inner width; turn only at the brick side walls.
        self._min_x = float(floor.left)
        self._max_x = float(floor.right - self._w)
        self._speed = speed
        self.heading = rng.choice((-1, 1))
        self.x = float(rng.uniform(self._min_x, self._max_x))

    @staticmethod
    def _load_image(sprites) -> Optional[pygame.Surface]:
        sprite = sprites.get("mushroom")
        return sprite.image if sprite and sprite.image else None

    def update(self, dt_ms: int) -> None:
        if not self._image:
            return
        dt = max(0, dt_ms) / 1000.0
        step = self._speed * 60.0 * dt
        next_x = self.x + self.heading * step

        if next_x <= self._min_x:
            self.x = self._min_x
            self.heading = 1
        elif next_x >= self._max_x:
            self.x = self._max_x
            self.heading = -1
        else:
            self.x = next_x

    def draw(self, surface: pygame.Surface) -> None:
        if not self._image:
            return
        image = self._image
        if self.heading < 0:
            image = flip(image, True, False)
        surface.blit(image, (int(self.x), self._ground_y))


class LoginFrameMushrooms:
    """Two mushrooms patrolling the floor between the frame's left/right brick walls."""

    def __init__(
        self,
        sprites,
        title_center: Tuple[int, int],
        *,
        rng: Optional[random.Random] = None,
    ):
        self._rng = rng or random.Random()
        floor = measure_title_mushroom_floor(title_center)
        self._mushrooms = [
            _PatrolMushroom(sprites, floor, self._rng, speed=1.5),
            _PatrolMushroom(sprites, floor, self._rng, speed=1.7),
        ]

    def update(self, dt_ms: int) -> None:
        for mushroom in self._mushrooms:
            mushroom.update(dt_ms)

    def draw(self, surface: pygame.Surface) -> None:
        for mushroom in self._mushrooms:
            mushroom.draw(surface)
