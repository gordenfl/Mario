"""Tiled Mario sky + drifting clouds for the login screen."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import pygame

from ui.wall_title import measure_login_title_frame_rect

# Full cloud: 3×32px wide upper row (cloud1_*) + lower row (cloud2_*).
CLOUD_TILE = 32
CLOUD_WIDTH = CLOUD_TILE * 3
CLOUD_HEIGHT = CLOUD_TILE * 2
LOGIN_CLOUD_COUNT = 4
_CLOUD_SPEED = 22.0
_EDGE_MARGIN = 12


@dataclass
class _DriftCloud:
    x: float
    y: int
    speed: float


def login_ui_forbidden_rects(screen_w: int, screen_h: int) -> List[pygame.Rect]:
    """Rects used for legacy layout helpers (clouds no longer avoid UI)."""
    cx = screen_w // 2
    pad = 18
    rects = [
        measure_login_title_frame_rect((cx, 160)).inflate(pad, pad),
        pygame.Rect(cx - 160, 296, 320, 48).inflate(pad, pad),
        pygame.Rect(cx - 60, 376, 120, 48).inflate(pad, pad),
        pygame.Rect(cx - 300, 408, 600, 64).inflate(pad, pad),
    ]
    return [r for r in rects if r.colliderect(pygame.Rect(0, 0, screen_w, screen_h))]


def _blit_full_cloud(surface: pygame.Surface, sprites, x: int, y: int) -> None:
    for row, prefix in enumerate(("cloud1", "cloud2"), start=0):
        for i in range(1, 4):
            sprite = sprites.get(f"{prefix}_{i}")
            if sprite and sprite.image:
                surface.blit(sprite.image, (x + (i - 1) * CLOUD_TILE, y + row * CLOUD_TILE))


class LoginDriftingClouds:
    """Clouds on the bottom layer, drifting right across the screen.

    All clouds share one speed and are spaced evenly on a closed track so
    each cloud leaving on the right is matched by one entering from the left.
    """

    def __init__(
        self,
        screen_w: int,
        screen_h: int,
        *,
        count: int = LOGIN_CLOUD_COUNT,
        rng: Optional[random.Random] = None,
    ):
        self.screen_w = screen_w
        self.screen_h = screen_h
        # Full path: left edge from -CLOUD_WIDTH (just off left) to screen_w (just off right).
        self._cycle = float(screen_w + CLOUD_WIDTH)
        rng = rng or random.Random()
        max_y = max(_EDGE_MARGIN, screen_h - CLOUD_HEIGHT - _EDGE_MARGIN)
        self._clouds: List[_DriftCloud] = []
        for i in range(count):
            phase = (i / count) * self._cycle
            x = -CLOUD_WIDTH + phase
            y = rng.randint(_EDGE_MARGIN, max_y)
            self._clouds.append(_DriftCloud(x, y, _CLOUD_SPEED))

    def update(self, dt_ms: int) -> None:
        dt = max(0.0, dt_ms) / 1000.0
        right_exit = float(self.screen_w)
        for cloud in self._clouds:
            cloud.x += cloud.speed * dt
            while cloud.x >= right_exit:
                cloud.x -= self._cycle

    def draw(self, surface: pygame.Surface, sprites) -> None:
        for cloud in self._clouds:
            _blit_full_cloud(surface, sprites, int(cloud.x), cloud.y)


def generate_login_cloud_layout(
    screen_w: int,
    screen_h: int,
    forbidden: Optional[Sequence[pygame.Rect]] = None,
    *,
    rng: Optional[random.Random] = None,
) -> List[Tuple[int, int]]:
    """Static snapshot of cloud positions (Kivy / legacy)."""
    clouds = LoginDriftingClouds(screen_w, screen_h, rng=rng)
    return [(int(c.x), c.y) for c in clouds._clouds]


DEFAULT_GROUND_ROWS = 2


def ground_tile_height(sprites) -> int:
    sky_sprite = sprites.get("sky")
    if sky_sprite and sky_sprite.image:
        return sky_sprite.image.get_height()
    return 32


def ground_band_rect(screen_w: int, screen_h: int, sprites, *, ground_rows: int = DEFAULT_GROUND_ROWS) -> pygame.Rect:
    """Screen rect covered by the bottom ground tile rows."""
    th = ground_tile_height(sprites)
    band_h = th * ground_rows
    return pygame.Rect(0, screen_h - band_h, screen_w, band_h)


def draw_sky_tiles(surface: pygame.Surface, sprites) -> None:
    """Tiled sky only (no clouds or ground)."""
    sky = sprites.get("sky")
    if not sky or not sky.image:
        surface.fill((137, 207, 240))
        return
    sky_img = sky.image
    tw, th = sky_img.get_size()
    width, height = surface.get_size()
    for y in range(0, height, th):
        for x in range(0, width, tw):
            surface.blit(sky_img, (x, y))


def draw_ground_tiles(
    surface: pygame.Surface,
    sprites,
    *,
    ground_rows: int = DEFAULT_GROUND_ROWS,
) -> None:
    """Ground tile band along the bottom (like the menu)."""
    width, height = surface.get_size()
    sky_sprite = sprites.get("sky")
    ground_sprite = sprites.get("ground")
    if not sky_sprite or not sky_sprite.image:
        return
    sky_img = sky_sprite.image
    ground_img = (
        ground_sprite.image
        if ground_sprite and ground_sprite.image
        else sky_img
    )
    tw = sky_img.get_width()
    th = sky_img.get_height()
    ground_band = th * ground_rows
    gy = height - ground_band
    while gy < height:
        x = 0
        while x < width:
            surface.blit(ground_img, (x, gy))
            x += tw
        gy += th


def draw_sky_ground_background(
    surface: pygame.Surface,
    sprites,
    *,
    ground_rows: int = DEFAULT_GROUND_ROWS,
) -> None:
    """Full-screen sky with game ground tiles along the bottom (like the menu)."""
    draw_sky_tiles(surface, sprites)
    draw_ground_tiles(surface, sprites, ground_rows=ground_rows)


def draw_login_sky(
    surface: pygame.Surface,
    sprites,
    cloud_positions: Optional[Sequence[Tuple[int, int]]] = None,
    *,
    drifting_clouds: Optional[LoginDriftingClouds] = None,
) -> None:
    """Sky tiles only; draw clouds via drifting_clouds.draw() on the same surface after."""
    sky = sprites.get("sky")
    if not sky or not sky.image:
        surface.fill((137, 207, 240))
    else:
        sky_img = sky.image
        tw, th = sky_img.get_size()
        width, height = surface.get_size()
        for y in range(0, height, th):
            for x in range(0, width, tw):
                surface.blit(sky_img, (x, y))

    if drifting_clouds is not None:
        drifting_clouds.draw(surface, sprites)
    elif cloud_positions:
        for x, y in cloud_positions:
            _blit_full_cloud(surface, sprites, x, y)
