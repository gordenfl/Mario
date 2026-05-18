"""Mario patrolling the login title brick wall."""

from __future__ import annotations

import random
from typing import Optional, Tuple

import pygame
from pygame.transform import flip

from ui.wall_title import measure_login_title_frame_rect

_RUN_FRAMES = ("mario_run1", "mario_run2", "mario_run3")
_RUN_FRAME_MS = 90
_WALK_SPEED = 2.4
_EDGE_PAD = 6
_JUMP_IMPULSE = -5.2
_JUMP_GRAVITY = 0.38
_JUMP_COOLDOWN_MS = (1800, 4200)


class LoginWallMario:
    """Runs on top of the title brick frame, turns at edges, occasional small hops."""

    def __init__(
        self,
        sprites,
        title_center: Tuple[int, int],
        *,
        rng: Optional[random.Random] = None,
    ):
        self._sprites = sprites
        self._title_center = title_center
        self._rng = rng or random.Random()
        self._frame_rect = measure_login_title_frame_rect(title_center)
        self._run_images = [
            self._image(name) for name in _RUN_FRAMES
        ]
        self._idle = self._image("mario_idle")
        self._jump = self._image("mario_jump")
        self._run_images = [im for im in self._run_images if im is not None]
        if not self._run_images:
            self._run_images = [self._idle] if self._idle else []

        ref = self._run_images[0] if self._run_images else self._idle
        self._w = ref.get_width() if ref else 32
        self._h = ref.get_height() if ref else 32
        self._ground_y = self._frame_rect.top - self._h
        self._min_x = self._frame_rect.left + _EDGE_PAD
        self._max_x = self._frame_rect.right - self._w - _EDGE_PAD

        self.x = float(self._min_x)
        self.heading = 1
        self._run_index = 0
        self._run_timer = 0
        self._jump_offset = 0.0
        self._jump_vel = 0.0
        self._jumping = False
        self._jump_cooldown_ms = self._rng.randint(*_JUMP_COOLDOWN_MS)

    def _image(self, name: str) -> Optional[pygame.Surface]:
        sprite = self._sprites.get(name)
        return sprite.image if sprite and sprite.image else None

    def _start_jump(self) -> None:
        self._jumping = True
        self._jump_vel = _JUMP_IMPULSE
        self._jump_cooldown_ms = self._rng.randint(*_JUMP_COOLDOWN_MS)

    def update(self, dt_ms: int) -> None:
        dt = max(0, dt_ms) / 1000.0
        step = _WALK_SPEED * 60.0 * dt

        if self._jumping:
            self._jump_vel += _JUMP_GRAVITY * 60.0 * dt
            self._jump_offset += self._jump_vel * 60.0 * dt
            if self._jump_offset >= 0.0:
                self._jump_offset = 0.0
                self._jump_vel = 0.0
                self._jumping = False
        else:
            self._jump_cooldown_ms = max(0, self._jump_cooldown_ms - dt_ms)
            if self._jump_cooldown_ms <= 0 and self._rng.random() < 0.0018 * dt_ms:
                self._start_jump()

        self.x += self.heading * step
        if self.x <= self._min_x:
            self.x = float(self._min_x)
            self.heading = 1
        elif self.x >= self._max_x:
            self.x = float(self._max_x)
            self.heading = -1

        if not self._jumping and self._run_images:
            self._run_timer += dt_ms
            if self._run_timer >= _RUN_FRAME_MS:
                self._run_timer = 0
                self._run_index = (self._run_index + 1) % len(self._run_images)

    def draw(self, surface: pygame.Surface) -> None:
        if self._jumping and self._jump:
            image = self._jump
        elif self._run_images:
            image = self._run_images[self._run_index]
        elif self._idle:
            image = self._idle
        else:
            return

        if self.heading < 0:
            image = flip(image, True, False)

        y = self._ground_y + int(self._jump_offset)
        surface.blit(image, (int(self.x), y))
