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
_EDGE_PAD = 8
_JUMP_IMPULSE = -9.2
_JUMP_GRAVITY = 0.44
_JUMP_COOLDOWN_MS = (900, 2200)
_PIPE_BODY_ROWS = 2
_BUSH_NAMES = ("bush_1", "bush_2", "bush_3")
_BUSH_GROUP_W = 96
_BUSH_STEP = 80


class _LobbyPipe:
    """Two-tile-wide pipe; extra body rows make it taller above the ground."""

    def __init__(self, sprites, x_left: int, ground_top: int, *, body_rows: int = _PIPE_BODY_ROWS):
        self.x_left = x_left
        self.ground_top = ground_top
        self.parts: List[Tuple[pygame.Surface, int, int]] = []
        th = 32
        body_l = _sprite_image(sprites, "pipe2L")
        body_r = _sprite_image(sprites, "pipe2R")
        head_l = _sprite_image(sprites, "pipeL")
        head_r = _sprite_image(sprites, "pipeR")
        if not all((body_l, body_r, head_l, head_r)):
            self.rect = pygame.Rect(x_left, ground_top - th, 64, th)
            return
        for row in range(body_rows):
            y = ground_top - (row + 1) * th
            self.parts.append((body_l, x_left, y))
            self.parts.append((body_r, x_left + th, y))
        head_y = ground_top - (body_rows + 1) * th
        self.parts.append((head_l, x_left, head_y))
        self.parts.append((head_r, x_left + th, head_y))
        self.rect = pygame.Rect(x_left, head_y, th * 2, ground_top - head_y)

    def draw(self, surface: pygame.Surface) -> None:
        for img, x, y in self.parts:
            surface.blit(img, (x, y))


def _sprite_image(sprites, name: str) -> Optional[pygame.Surface]:
    sprite = sprites.get(name)
    return sprite.image if sprite and sprite.image else None


class _LobbyPatrolMario:
    """Walks the lobby ground, jumps over the pipe, turns at edges."""

    def __init__(
        self,
        sprites,
        ground_top: int,
        pipe: _LobbyPipe,
        min_x: int,
        max_x: int,
        *,
        rng: Optional[random.Random] = None,
    ):
        self._sprites = sprites
        self._ground_top = ground_top
        self._pipe = pipe
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
        self._run_index = 0
        self._run_timer = 0
        self._jump_offset = 0.0
        self._jump_vel = 0.0
        self._jumping = False
        self._jump_cooldown_ms = 0

    def _feet_rect(self) -> pygame.Rect:
        y = self._ground_top - self._h + int(self._jump_offset)
        return pygame.Rect(int(self.x), y, self._w, self._h)

    def _start_jump(self) -> None:
        if self._jumping:
            return
        self._jumping = True
        self._jump_vel = _JUMP_IMPULSE
        self._jump_cooldown_ms = self._rng.randint(*_JUMP_COOLDOWN_MS)

    def _needs_pipe_jump(self) -> bool:
        if self._jumping or self._jump_cooldown_ms > 0:
            return False
        feet = self._feet_rect()
        pipe = self._pipe.rect
        if not pipe.width:
            return False
        ahead = pipe.inflate(14, 0)
        if self.heading > 0:
            return feet.colliderect(ahead) and feet.right >= pipe.left - 6
        return feet.colliderect(ahead) and feet.left <= pipe.right + 6

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
            if self._needs_pipe_jump():
                self._start_jump()

        self.x += self.heading * step
        if self.x <= self._min_x:
            self.x = self._min_x
            self.heading = 1
        elif self.x >= self._max_x:
            self.x = self._max_x
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
        y = self._ground_top - self._h + int(self._jump_offset)
        surface.blit(image, (int(self.x), y))


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
        pipe_x = patrol_min + (patrol_max - patrol_min) // 2 - 32
        self._pipe = _LobbyPipe(sprites, pipe_x, ground_top, body_rows=_PIPE_BODY_ROWS)
        self._bushes: List[Tuple[pygame.Surface, int, int]] = []
        self._build_bushes()
        self._mario = _LobbyPatrolMario(
            sprites,
            ground_top,
            self._pipe,
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
        pipe_zone = self._pipe.rect.inflate(24, 8)
        x = 16
        while x + _BUSH_GROUP_W <= self._panel_left - 24:
            group_rect = pygame.Rect(x, self._ground_top - group_h, _BUSH_GROUP_W, group_h)
            if not group_rect.colliderect(pipe_zone):
                for i, img in enumerate(images):
                    self._bushes.append((img, x + i * 32, self._ground_top - img.get_height()))
            x += _BUSH_STEP

    def update(self, dt_ms: int) -> None:
        self._clouds.update(dt_ms)
        self._mario.update(dt_ms)

    def draw(self, surface: pygame.Surface) -> None:
        self._clouds.draw(surface, self._sprites)
        for img, x, y in self._bushes:
            surface.blit(img, (x, y))
        self._pipe.draw(surface)
        self._mario.draw(surface)

    def draw_divider(self, surface: pygame.Surface, top: int, bottom: int) -> None:
        x = self._panel_left - 18
        pygame.draw.line(surface, (255, 255, 255), (x, top), (x, bottom), 2)
        pygame.draw.line(surface, (60, 120, 180), (x + 2, top), (x + 2, bottom), 1)
