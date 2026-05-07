from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .rect import Rect


TILE = 32


@dataclass(frozen=True)
class TileCell:
    x: int
    y: int
    kind: str


class Level:
    """
    Kivy-friendly level representation.
    Uses the existing JSON format from `client/levels/*.json`.

    Coordinates:
    - World space is pixel space with origin at top-left (pygame-style).
    - Rendering will convert to Kivy coordinates (origin bottom-left).
    """

    def __init__(self) -> None:
        self.length_tiles: int = 0
        self.solid_cells: Set[Tuple[int, int]] = set()
        self.decor_cells: List[TileCell] = []

    @staticmethod
    def from_json(path: Path) -> "Level":
        raw = json.loads(path.read_text(encoding="utf-8"))
        lvl = Level()
        lvl.length_tiles = int(raw.get("length", 0))
        objects: Dict[str, list] = raw.get("level", {}).get("objects", {}) or {}
        layers: Dict[str, dict] = raw.get("level", {}).get("layers", {}) or {}

        # Ground layer rectangles (solid)
        ground_layer = layers.get("ground") or {}
        gx0, gx1 = (ground_layer.get("x") or [0, 0])
        gy0, gy1 = (ground_layer.get("y") or [0, 0])
        for x in range(int(gx0), int(gx1)):
            for y in range(int(gy0), int(gy1)):
                lvl.solid_cells.add((x, y))

        # Object tiles
        for x, y in objects.get("ground", []):
            lvl.solid_cells.add((int(x), int(y)))
        for x, y in objects.get("bricks", []):
            lvl.solid_cells.add((int(x), int(y)))
        for x, y, length in objects.get("pipe", []):
            x = int(x)
            y = int(y)
            length = int(length)
            # Pipe head is 2 tiles wide, then body downwards.
            lvl.solid_cells.add((x, y))
            lvl.solid_cells.add((x + 1, y))
            for i in range(1, length + 20):
                lvl.solid_cells.add((x, y + i))
                lvl.solid_cells.add((x + 1, y + i))

        # Simple decor (non-solid) markers to draw later.
        for x, y in objects.get("bush", []):
            lvl.decor_cells.append(TileCell(int(x), int(y), "bush"))
        for x, y in objects.get("cloud", []):
            lvl.decor_cells.append(TileCell(int(x), int(y), "cloud"))

        return lvl

    def is_solid_at_pixel(self, x: float, y: float) -> bool:
        tx = int(x // TILE)
        ty = int(y // TILE)
        return (tx, ty) in self.solid_cells

    def tile_rect(self, tx: int, ty: int) -> Rect:
        return Rect(tx * TILE, ty * TILE, TILE, TILE)

    def iter_visible_tiles(self, camera_x: float, screen_w: float, screen_h: float):
        start_tx = max(int((-camera_x) // TILE) - 2, 0)
        end_tx = int(((-camera_x) + screen_w) // TILE) + 3
        max_ty = int(screen_h // TILE) + 3
        for (tx, ty) in self.solid_cells:
            if ty < 0 or ty > max_ty:
                continue
            if tx < start_tx or tx > end_tx:
                continue
            yield tx, ty

