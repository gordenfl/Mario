"""Shared UI fonts for login screens (system sans-serif, not pixel/handwritten)."""

from __future__ import annotations

from functools import lru_cache

import pygame

_UI_FONT_CANDIDATES = (
    "PingFang SC",
    "Hiragino Sans GB",
    "STHeiti",
    "Microsoft YaHei",
    "Segoe UI",
    "Helvetica Neue",
    "Arial",
)


@lru_cache(maxsize=32)
def get_ui_font(size: int, *, bold: bool = False) -> pygame.font.Font:
    for name in _UI_FONT_CANDIDATES:
        path = pygame.font.match_font(name, bold=bold)
        if path:
            return pygame.font.Font(path, size)
        try:
            font = pygame.font.SysFont(name, size, bold=bold)
            if font:
                return font
        except Exception:
            continue
    return pygame.font.SysFont(None, size, bold=bold)
