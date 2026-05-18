"""Kivy login title with brick border and mushroom-colored markup."""

from __future__ import annotations

import random
from pathlib import Path

from kivy.graphics import Rectangle
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from client.ui.wall_title import (
    LOGIN_TITLE_MAIN,
    LOGIN_TITLE_ONLINE,
    LOGIN_TITLE_SEP,
    ONLINE_COLORS,
    _FALLBACK_MUSHROOM_PALETTE,
)

from .sprites_loader import SpriteRepository

_CLIENT_ROOT = Path(__file__).resolve().parents[1] / "client"
_HEITI_FONT = "PingFang SC"
_repo: SpriteRepository | None = None


def _repo_singleton() -> SpriteRepository:
    global _repo
    if _repo is None:
        _repo = SpriteRepository(_CLIENT_ROOT)
        _repo.load_all()
    return _repo


def _markup_title(palette) -> str:
    rng = random.Random()
    parts = []
    for char in LOGIN_TITLE_MAIN + LOGIN_TITLE_SEP:
        if char == " ":
            parts.append(" ")
            continue
        r, g, b = rng.choice(palette)
        parts.append(f"[color={r:02x}{g:02x}{b:02x}ff]{char}[/color]")
    for idx, char in enumerate(LOGIN_TITLE_ONLINE):
        r, g, b = ONLINE_COLORS[idx % len(ONLINE_COLORS)]
        parts.append(f"[color={r:02x}{g:02x}{b:02x}ff]{char}[/color]")
    return "".join(parts)


class WallFramedTitle(FloatLayout):
    """Brick-framed title with mushroom-colored letters."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._brick_tex = None
        self._brick_size = (32, 32)
        repo = _repo_singleton()
        bricks = repo.static.get("bricks")
        if bricks:
            self._brick_tex, self._brick_size = bricks

        palette = _FALLBACK_MUSHROOM_PALETTE
        self.label = Label(
            text=f"[b]{_markup_title(palette)}[/b]",
            font_size="40sp",
            bold=True,
            font_name=_HEITI_FONT,
            color=(1, 1, 1, 1),
            halign="center",
            valign="top",
            markup=True,
        )
        self.add_widget(self.label)
        self.bind(pos=self._relayout, size=self._relayout)

    def _relayout(self, *_args):
        self.canvas.before.clear()
        if not self.width or not self.height or not self._brick_tex:
            return
        tw, th = self._brick_size
        pad = 10
        x, y, w, h = self.x, self.y, self.width, self.height
        cols = max(1, int(w // tw))
        rows = max(1, int(h // th))
        with self.canvas.before:
            for col in range(cols):
                Rectangle(texture=self._brick_tex, pos=(x + col * tw, y), size=(tw, th))
                if rows > 1:
                    Rectangle(
                        texture=self._brick_tex,
                        pos=(x + col * tw, y + h - th),
                        size=(tw, th),
                    )
            for row in range(1, rows - 1):
                Rectangle(texture=self._brick_tex, pos=(x, y + row * th), size=(tw, th))
                Rectangle(
                    texture=self._brick_tex,
                    pos=(x + w - tw, y + row * th),
                    size=(tw, th),
                )

        self.label.size = (w - 2 * tw - 2 * pad, h - 2 * th - 2 * pad)
        self.label.pos = (x + tw + pad, y + th + pad)
        self.label.text_size = (self.label.size[0], None)
