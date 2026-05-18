"""Login title: mushroom-colored letters inside a brick wall frame."""

from __future__ import annotations

import random
from typing import List, Optional, Sequence, Tuple

import pygame

from ui.fonts import get_ui_font

LOGIN_TITLE = "Super Mario - Online"
LOGIN_TITLE_MAIN = "Super Mario"
LOGIN_TITLE_SEP = " - "
LOGIN_TITLE_ONLINE = "ONLINE"
LOGIN_TITLE_FULL = LOGIN_TITLE_MAIN + LOGIN_TITLE_SEP + LOGIN_TITLE_ONLINE
TITLE_FONT_SIZE = 46
ONLINE_LETTER_GAP = 2
TITLE_Y_OFFSET = 24
LOGIN_INNER_EXTRA_ROWS = 1
TITLE_INNER_PAD = 14
# Extra inner width (32px per side) so ONLINE is not flush against the brick wall.
TITLE_EXTRA_SIDE_TILES = 1

# O, n, l, i, n, e — red, green, blue, purple, yellow, black
ONLINE_COLORS: Tuple[Tuple[int, int, int], ...] = (
    (220, 40, 40),
    (40, 180, 60),
    (50, 120, 220),
    (140, 60, 200),
    (240, 200, 40),
    (20, 20, 20),
)

_FALLBACK_MUSHROOM_PALETTE: Tuple[Tuple[int, int, int], ...] = (
    (228, 72, 52),
    (196, 48, 36),
    (255, 248, 236),
    (255, 218, 168),
    (168, 96, 56),
    (120, 64, 36),
)


def _title_font(font_size: int = TITLE_FONT_SIZE) -> pygame.font.Font:
    return get_ui_font(font_size, bold=True)


def mushroom_palette_from_sprite(sprites) -> Tuple[Tuple[int, int, int], ...]:
    """Sample visible colors from the in-game mushroom sprite."""
    sprite = sprites.get("mushroom") if sprites else None
    if not sprite or not sprite.image:
        return _FALLBACK_MUSHROOM_PALETTE

    img = sprite.image.convert_alpha()
    w, h = img.get_size()
    if w <= 0 or h <= 0:
        return _FALLBACK_MUSHROOM_PALETTE

    seen: set[Tuple[int, int, int]] = set()
    palette: List[Tuple[int, int, int]] = []
    rng = random.Random()
    for _ in range(1200):
        x = rng.randint(0, w - 1)
        y = rng.randint(0, h - 1)
        r, g, b, a = img.get_at((x, y))
        if a < 80:
            continue
        key = (r // 20, g // 20, b // 20)
        if key in seen or (r + g + b) < 40:
            continue
        seen.add(key)
        palette.append((r, g, b))
        if len(palette) >= 14:
            break
    return tuple(palette) if palette else _FALLBACK_MUSHROOM_PALETTE


def build_title_letter_colors(
    sprites,
    *,
    rng: Optional[random.Random] = None,
) -> List[Tuple[int, int, int]]:
    """Mushroom-random colors for 'Super Mario - '; fixed rainbow for 'ONLINE'."""
    palette = mushroom_palette_from_sprite(sprites)
    rng = rng or random.Random()
    colors: List[Tuple[int, int, int]] = []
    for char in LOGIN_TITLE_MAIN + LOGIN_TITLE_SEP:
        colors.append(rng.choice(palette) if char != " " else rng.choice(palette))
    for idx, _char in enumerate(LOGIN_TITLE_ONLINE):
        colors.append(ONLINE_COLORS[idx % len(ONLINE_COLORS)])
    return colors


def measure_login_title_text_size(font_size: int = TITLE_FONT_SIZE) -> Tuple[int, int]:
    font = _title_font(font_size)
    online_w = sum(font.size(char)[0] + ONLINE_LETTER_GAP for char in LOGIN_TITLE_ONLINE)
    online_w -= ONLINE_LETTER_GAP
    tw = (
        font.size(LOGIN_TITLE_MAIN)[0]
        + font.size(LOGIN_TITLE_SEP)[0]
        + online_w
    )
    return tw, font.get_height()


def _draw_brick_outline(surface: pygame.Surface, brick_img: pygame.Surface, rect: pygame.Rect) -> None:
    tw, th = brick_img.get_size()
    if tw <= 0 or th <= 0:
        return
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    cols = max(1, w // tw)
    rows = max(1, h // th)
    for col in range(cols):
        surface.blit(brick_img, (x + col * tw, y))
        if rows > 1:
            surface.blit(brick_img, (x + col * tw, y + h - th))
    for row in range(1, rows - 1):
        surface.blit(brick_img, (x, y + row * th))
        surface.blit(brick_img, (x + w - tw, y + row * th))


def measure_login_title_frame_rect(
    center: Tuple[int, int],
    *,
    font_size: int = TITLE_FONT_SIZE,
    inner_pad: int = TITLE_INNER_PAD,
    inner_extra_rows: int = LOGIN_INNER_EXTRA_ROWS,
    tile: int = 32,
    **_kwargs,
) -> pygame.Rect:
    tw, th = measure_login_title_text_size(font_size)
    side_extra = tile * TITLE_EXTRA_SIDE_TILES * 2
    inner_w = tw + inner_pad * 2 + side_extra
    inner_h = th + inner_pad * 2 + tile * inner_extra_rows
    border_px = tile
    frame_w = max(tile, ((inner_w + border_px * 2) + tile - 1) // tile * tile)
    frame_h = max(tile, ((inner_h + border_px * 2) + tile - 1) // tile * tile)
    cx, cy = center
    cy += TITLE_Y_OFFSET
    return pygame.Rect(cx - frame_w // 2, cy - frame_h // 2, frame_w, frame_h)


def measure_login_title_inner_rect(
    center: Tuple[int, int],
    *,
    tile: int = 32,
    **kwargs,
) -> pygame.Rect:
    return measure_login_title_frame_rect(center, tile=tile, **kwargs).inflate(-tile * 2, -tile * 2)


def measure_title_mushroom_floor(title_center: Tuple[int, int], *, font_size: int = TITLE_FONT_SIZE) -> pygame.Rect:
    """Bottom row inside the brick frame for patrolling mushrooms."""
    inner = measure_login_title_inner_rect(title_center, font_size=font_size)
    band_h = 32
    return pygame.Rect(inner.left, inner.bottom - band_h, inner.width, band_h)


def draw_login_title_text(
    surface: pygame.Surface,
    center: Tuple[int, int],
    letter_colors: Sequence[Tuple[int, int, int]],
    *,
    font_size: int = TITLE_FONT_SIZE,
) -> None:
    font = _title_font(font_size)
    tw, th = measure_login_title_text_size(font_size)
    cx, _cy = center
    inner = measure_login_title_inner_rect(center, font_size=font_size)
    x = inner.left + (inner.width - tw) // 2
    y = inner.top + TITLE_INNER_PAD

    color_idx = 0
    for part in (LOGIN_TITLE_MAIN, LOGIN_TITLE_SEP, LOGIN_TITLE_ONLINE):
        for i, char in enumerate(part):
            if color_idx >= len(letter_colors):
                break
            if char == " ":
                x += font.size(" ")[0]
                color_idx += 1
                continue
            color = letter_colors[color_idx]
            rendered = font.render(char, True, color)
            surface.blit(rendered, (x, y + (th - rendered.get_height()) // 2))
            x += rendered.get_width()
            if part is LOGIN_TITLE_ONLINE and i < len(part) - 1:
                x += ONLINE_LETTER_GAP
            color_idx += 1


def draw_wall_frame_bricks(
    surface: pygame.Surface,
    sprites,
    center: Tuple[int, int],
    **kwargs,
) -> pygame.Rect:
    brick = sprites.get("bricks")
    brick_img = brick.image if brick and brick.image else None
    tile = brick_img.get_width() if brick_img else 32
    frame_rect = measure_login_title_frame_rect(center, tile=tile, **kwargs)
    if brick_img:
        _draw_brick_outline(surface, brick_img, frame_rect)
    return frame_rect


def draw_wall_framed_title(
    surface: pygame.Surface,
    sprites,
    center: Tuple[int, int],
    letter_colors: Sequence[Tuple[int, int, int]],
    **kwargs,
) -> pygame.Rect:
    frame_rect = draw_wall_frame_bricks(surface, sprites, center, **kwargs)
    draw_login_title_text(surface, center, letter_colors, **kwargs)
    return frame_rect
