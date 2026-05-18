"""Sky/ground decorations for the multiplayer lobby."""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

import pygame
from pygame.transform import flip

from ui.sky_background import LoginDriftingClouds

_RUN_FRAMES = ("mario_run1", "mario_run2", "mario_run3")
_RUN_FRAME_MS = 90
_WALK_SPEED = 2.8
_JUMP_GRAVITY = 0.42
_SPOT_JUMP = -6.8
_ARRIVE_DIST = 8
_SPOT_STAY_MS = (2800, 4500)
_LOOK_AROUND_MS = 1100
_SPOT_JUMP_CHANCE = 0.03
_TURN_BACK_CHANCE = 0.02
_BUSH_NAMES = ("bush_1", "bush_2", "bush_3")
_BUSH_GROUP_W = 96
_BUSH_COUNT_DIVISOR = 128


def _sprite_image(sprites, name: str) -> Optional[pygame.Surface]:
    sprite = sprites.get(name)
    return sprite.image if sprite and sprite.image else None


class _LobbyPatrolMario:
    """Walks to random ground spots, hops once, then looks left and right."""

    def __init__(
        self,
        sprites,
        ground_top: int,
        min_x: int,
        max_x: int,
        *,
        rng: Optional[random.Random] = None,
    ):
        self._ground_top = ground_top
        self._rng = rng or random.Random()
        self._run_images = [
            im for im in (_sprite_image(sprites, n) for n in _RUN_FRAMES) if im
        ]
        self._idle = _sprite_image(sprites, "mario_idle")
        self._jump = _sprite_image(sprites, "mario_jump")
        if not self._run_images:
            self._run_images = [self._idle] if self._idle else []

        ref = self._run_images[0] if self._run_images else self._idle
        self._w = ref.get_width() if ref else 32
        self._h = ref.get_height() if ref else 32
        self._min_x = float(min_x)
        self._max_x = float(max_x - self._w)

        self.x = self._min_x
        self.heading = 1
        self._state = "walk"
        self._target_x = self._min_x
        self._run_index = 0
        self._run_timer = 0
        self._jump_offset = 0.0
        self._jump_vel = 0.0
        self._look_ms = 0
        self._look_flip_ms = 0
        self._walk_heading = 1
        self._pick_target()

    def _pick_target(self) -> None:
        self._target_x = self._rng.uniform(self._min_x, self._max_x)

    def _pick_target_after_look(self) -> None:
        """After looking around, sometimes walk back the way Mario came from."""
        if self._rng.random() < _TURN_BACK_CHANCE:
            gap = 24.0
            if self._walk_heading > 0:
                high = max(self._min_x, self.x - gap)
                if high > self._min_x + _ARRIVE_DIST:
                    self._target_x = self._rng.uniform(self._min_x, high)
                    return
            else:
                low = min(self._max_x, self.x + gap)
                if low < self._max_x - _ARRIVE_DIST:
                    self._target_x = self._rng.uniform(low, self._max_x)
                    return
        self._pick_target()

    def _draw_y(self) -> int:
        return self._ground_top - self._h + int(self._jump_offset)

    def _start_spot_jump(self) -> None:
        self._state = "air"
        self._jump_vel = _SPOT_JUMP
        self._jump_offset = 0.0

    def _begin_look_around(self) -> None:
        self._state = "look"
        self._look_ms = self._rng.randint(*_SPOT_STAY_MS)
        self._look_flip_ms = _LOOK_AROUND_MS
        self._walk_heading = self.heading

    def _arrive_at_spot(self) -> None:
        if self._rng.random() < _SPOT_JUMP_CHANCE:
            self._start_spot_jump()
        else:
            self._begin_look_around()

    def _update_walk(self, dt_ms: int, dt: float) -> None:
        if abs(self.x - self._target_x) <= _ARRIVE_DIST:
            self._arrive_at_spot()
            return

        step = _WALK_SPEED * 60.0 * dt
        self.heading = 1 if self._target_x > self.x else -1
        self._walk_heading = self.heading
        self.x += self.heading * step
        self.x = max(self._min_x, min(self.x, self._max_x))

        self._run_timer += dt_ms
        if self._run_timer >= _RUN_FRAME_MS:
            self._run_timer = 0
            self._run_index = (self._run_index + 1) % len(self._run_images)

    def _update_air(self, dt: float) -> None:
        self._jump_vel += _JUMP_GRAVITY * 60.0 * dt
        self._jump_offset += self._jump_vel * 60.0 * dt
        if self._jump_offset >= 0.0:
            self._jump_offset = 0.0
            self._jump_vel = 0.0
            self._begin_look_around()

    def _update_look(self, dt_ms: int) -> None:
        self._look_ms -= dt_ms
        self._look_flip_ms -= dt_ms
        if self._look_flip_ms <= 0:
            self.heading *= -1
            self._look_flip_ms = _LOOK_AROUND_MS
        if self._look_ms <= 0:
            self._pick_target_after_look()
            self._state = "walk"

    def update(self, dt_ms: int) -> None:
        dt = max(0.0, dt_ms) / 1000.0
        if self._state == "air":
            self._update_air(dt)
        elif self._state == "look":
            self._update_look(dt_ms)
        else:
            self._update_walk(dt_ms, dt)

    def draw(self, surface: pygame.Surface) -> None:
        if self._state == "air" and self._jump:
            image = self._jump
        elif self._state == "look" and self._idle:
            image = self._idle
        elif self._run_images:
            image = self._run_images[self._run_index]
        elif self._idle:
            image = self._idle
        else:
            return
        if self.heading < 0:
            image = flip(image, True, False)
        surface.blit(image, (int(self.x), self._draw_y()))


class LobbyDecor:
    def __init__(
        self,
        screen_w: int,
        screen_h: int,
        sprites,
        *,
        ground_top: int,
        panel_left: int,
        rng: Optional[random.Random] = None,
    ):
        self._sprites = sprites
        self._ground_top = ground_top
        self._panel_left = panel_left
        self._rng = rng or random.Random()
        self._clouds = LoginDriftingClouds(screen_w, screen_h, count=5, rng=self._rng)

        patrol_min = 24
        patrol_max = panel_left - 72
        self._bushes: List[Tuple[pygame.Surface, int, int]] = []
        self._build_bushes()
        self._mario = _LobbyPatrolMario(
            sprites,
            ground_top,
            patrol_min,
            patrol_max,
            rng=self._rng,
        )

    def _build_bushes(self) -> None:
        self._bushes.clear()
        images = [_sprite_image(self._sprites, n) for n in _BUSH_NAMES]
        if not all(images):
            return
        group_h = max(im.get_height() for im in images)
        min_x = 16
        max_x = self._panel_left - _BUSH_GROUP_W - 24
        if max_x <= min_x:
            return

        target = max(1, (max_x - min_x) // _BUSH_COUNT_DIVISOR)
        placed: List[pygame.Rect] = []
        attempts = 0
        while len(placed) < target and attempts < target * 24:
            attempts += 1
            x = self._rng.randint(min_x, max_x)
            rect = pygame.Rect(x, self._ground_top - group_h, _BUSH_GROUP_W, group_h)
            if any(rect.colliderect(other.inflate(12, 0)) for other in placed):
                continue
            placed.append(rect)
            for i, img in enumerate(images):
                self._bushes.append(
                    (img, x + i * 32, self._ground_top - img.get_height())
                )

    def update(self, dt_ms: int) -> None:
        self._clouds.update(dt_ms)
        self._mario.update(dt_ms)

    def draw_clouds(self, surface: pygame.Surface) -> None:
        self._clouds.draw(surface, self._sprites)

    def draw_foreground(self, surface: pygame.Surface) -> None:
        for img, x, y in self._bushes:
            surface.blit(img, (x, y))
        self._mario.draw(surface)

    def draw(self, surface: pygame.Surface) -> None:
        self.draw_clouds(surface)
        self.draw_foreground(surface)

    def draw_divider(self, surface: pygame.Surface, top: int, bottom: int) -> None:
        x = self._panel_left - 18
        pygame.draw.line(surface, (255, 255, 255), (x, top), (x, bottom), 2)
        pygame.draw.line(surface, (60, 120, 180), (x + 2, top), (x + 2, bottom), 1)
