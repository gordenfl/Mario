"""Lobby toolbar icons (drawn at runtime, Mario-style chunky glyphs)."""

from __future__ import annotations

import math
from typing import Dict

import pygame

ICON_CANVAS = 32
_STROKE = 3
_FG = (255, 255, 255)
_OUTLINE = (25, 25, 35)


def _surface() -> pygame.Surface:
    return pygame.Surface((ICON_CANVAS, ICON_CANVAS), pygame.SRCALPHA)


def _arc_poly(cx: float, cy: float, r: float, a0: float, a1: float, steps: int = 14):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        a = a0 + (a1 - a0) * t
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _draw_refresh(surface: pygame.Surface) -> None:
    cx, cy = ICON_CANVAS / 2, ICON_CANVAS / 2
    r = 11
    arc = _arc_poly(cx, cy, r, math.radians(130), math.radians(-70), 16)
    for color, w in ((_OUTLINE, 5), (_FG, _STROKE)):
        pygame.draw.lines(surface, color, False, arc, w)
    tip = arc[-1]
    dx, dy = tip[0] - cx, tip[1] - cy
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    head = [
        tip,
        (tip[0] - ux * 7 + px * 4, tip[1] - uy * 7 + py * 4),
        (tip[0] - ux * 7 - px * 4, tip[1] - uy * 7 - py * 4),
    ]
    for color, w in ((_OUTLINE, 5), (_FG, _STROKE)):
        pygame.draw.polygon(surface, color, head)
        if w > _STROKE:
            pygame.draw.polygon(surface, color, head, w)


def _draw_create_room(surface: pygame.Surface) -> None:
    frame = pygame.Rect(7, 9, 18, 16)
    for color, w in ((_OUTLINE, 5), (_FG, _STROKE)):
        pygame.draw.rect(surface, color, frame, w, border_radius=3)
    cx, cy = ICON_CANVAS // 2, 17
    for color, w in ((_OUTLINE, 5), (_FG, _STROKE + 1)):
        pygame.draw.line(surface, color, (cx, 12), (cx, 22), w)
        pygame.draw.line(surface, color, (12, cy), (20, cy), w)


def _draw_logout(surface: pygame.Surface) -> None:
    door = pygame.Rect(6, 8, 14, 18)
    for color, w in ((_OUTLINE, 5), (_FG, _STROKE)):
        pygame.draw.rect(surface, color, door, w, border_radius=2)
    pygame.draw.circle(surface, (90, 55, 30), (16, 18), 2)
    mid_y = 17
    shaft = [(20, mid_y), (27, mid_y)]
    for color, w in ((_OUTLINE, 5), (_FG, _STROKE)):
        pygame.draw.lines(surface, color, False, shaft, w)
    head = [(25, mid_y - 4), (29, mid_y), (25, mid_y + 4)]
    for color, w in ((_OUTLINE, 5), (_FG, _STROKE)):
        pygame.draw.polygon(surface, color, head)
        if w > _STROKE:
            pygame.draw.polygon(surface, color, head, w)


def build_lobby_icons() -> Dict[str, pygame.Surface]:
    builders = {
        "refresh": _draw_refresh,
        "create": _draw_create_room,
        "logout": _draw_logout,
    }
    icons: Dict[str, pygame.Surface] = {}
    for key, draw in builders.items():
        surf = _surface()
        draw(surf)
        icons[key] = surf
    return icons
