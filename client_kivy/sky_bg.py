"""Kivy canvas helper for login sky background (matches client/ui/sky_background.py)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from kivy.graphics import Color, Rectangle

from client.ui.sky_background import CLOUD_HEIGHT, CLOUD_TILE, CLOUD_WIDTH
from client.viewport import VIRTUAL_H, VIRTUAL_W

from .sprites_loader import SpriteRepository

_CLIENT_ROOT = Path(__file__).resolve().parents[1] / "client"
_repo: SpriteRepository | None = None


def _repo_singleton() -> SpriteRepository:
    global _repo
    if _repo is None:
        _repo = SpriteRepository(_CLIENT_ROOT)
        _repo.load_all()
    return _repo


def _scale_positions(
    cloud_positions: Sequence[Tuple[int, int]],
    width: float,
    height: float,
    layout_w: float,
    layout_h: float,
) -> List[Tuple[float, float]]:
    if layout_w <= 0 or layout_h <= 0:
        return [(float(x), float(y)) for x, y in cloud_positions]
    sx = width / layout_w
    sy = height / layout_h
    return [(x * sx, y * sy) for x, y in cloud_positions]


def paint_login_sky(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    cloud_positions: Optional[Sequence[Tuple[int, int]]] = None,
    layout_size: Tuple[float, float] = (VIRTUAL_W, VIRTUAL_H),
) -> None:
    """Draw tiled sky + full clouds; call inside `with widget.canvas.before:`."""
    repo = _repo_singleton()
    sky = repo.static.get("sky")
    if not sky:
        Color(137 / 255.0, 207 / 255.0, 240 / 255.0, 1)
        Rectangle(pos=(x, y), size=(width, height))
        return

    sky_tex, (tw, th) = sky
    cols = int(width // tw) + 2
    rows = int(height // th) + 2
    for row in range(rows):
        for col in range(cols):
            px = x + col * tw
            py = y + height - (row + 1) * th
            Rectangle(texture=sky_tex, pos=(px, py), size=(tw, th))

    if not cloud_positions:
        return

    layout_w, layout_h = layout_size
    scaled = _scale_positions(cloud_positions, width, height, layout_w, layout_h)
    sx = width / layout_w if layout_w > 0 else 1.0
    sy = height / layout_h if layout_h > 0 else 1.0
    cloud_w = CLOUD_WIDTH * sx
    cloud_h = CLOUD_HEIGHT * sy
    tile_w = CLOUD_TILE * sx
    tile_h = CLOUD_TILE * sy

    for cx, cy in scaled:
        for row, prefix in enumerate(("cloud1", "cloud2")):
            for i in range(1, 4):
                tup = repo.static.get(f"{prefix}_{i}")
                if not tup:
                    continue
                tex, _ = tup
                px = x + cx + (i - 1) * tile_w
                # cy is top-down; Kivy Y is bottom-up.
                row_y_top = cy + row * CLOUD_TILE * sy
                py = y + height - row_y_top - tile_h
                Rectangle(texture=tex, pos=(px, py), size=(tile_w, tile_h))
