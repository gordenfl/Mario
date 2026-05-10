from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .rect import Rect


TILE = 32


@dataclass
class CellTile:
    """One cell in the pixel-art tile grid."""

    sprite_key: Optional[str]  # SpriteRepository.static key like "ground", "bricks"
    solid: bool
    redraw_sky_below: bool = False


class Level:
    """
    Level shaped like pygame `classes.Level`:
    tiles[ty][tx] corresponds to tile column tx, tile row ty (same as pygame `self.level`).
    """

    def __init__(self) -> None:
        self.length_tiles = 0
        self.nrow = 0
        self.ncol = 0
        self.tiles: List[List[CellTile]] = []
        self._solid: set[Tuple[int, int]] = set()
        self._broken_tiles: List[Tuple[int, int]] = []

    @classmethod
    def from_json(cls, path: Path) -> "Level":
        raw = json.loads(path.read_text(encoding="utf-8"))
        lvl = cls()
        lvl.length_tiles = max(1, int(raw.get("length", 1)))
        data_level = raw.get("level", {})
        lvl._build_blank_from_layers(data_level)
        lvl._apply_objects(data_level.get("objects", {}) or {})
        lvl._index_solids()
        return lvl

    def _ensure_size(self, needed_rows: int, needed_cols: int) -> None:
        if needed_cols > self.ncol:
            sky_cell = lambda: CellTile(sprite_key="sky", solid=False, redraw_sky_below=False)
            for row in self.tiles:
                while len(row) < needed_cols:
                    row.append(sky_cell())
            self.ncol = needed_cols

        sky_row = lambda: [
            CellTile(sprite_key="sky", solid=False, redraw_sky_below=False)
            for _ in range(self.ncol)
        ]

        while len(self.tiles) < needed_rows:
            self.tiles.append(sky_row())
        self.nrow = len(self.tiles)

    def _build_blank_from_layers(self, data: dict) -> None:
        layers = data["layers"]
        sky_range = tuple(layers["sky"]["x"])
        sky_y_range = tuple(layers["sky"]["y"])
        ground_y_range = tuple(layers["ground"]["y"])

        ncol = max(sky_range[1] - sky_range[0], self.length_tiles)
        ncol = max(1, ncol)

        sky_rows = sky_y_range[1] - sky_y_range[0]
        ground_rows = ground_y_range[1] - ground_y_range[0]
        nrow = sky_rows + ground_rows
        nrow = max(1, nrow)

        self.ncol = ncol
        self.length_tiles = max(self.length_tiles, ncol)
        self.tiles = []
        sky_cell = lambda: CellTile(sprite_key="sky", solid=False, redraw_sky_below=False)
        ground_cell = lambda: CellTile(
            sprite_key="ground", solid=True, redraw_sky_below=False
        )

        for ry in range(nrow):
            row: List[CellTile] = []
            if ry < sky_rows:
                row = [sky_cell() for _ in range(ncol)]
            else:
                row = [ground_cell() for _ in range(ncol)]
            self.tiles.append(row)
        self.nrow = nrow

    def _in_bounds(self, tx: int, ty: int) -> bool:
        return 0 <= ty < len(self.tiles) and tx >= 0 and tx < len(self.tiles[ty])

    def _apply_objects(self, objects: dict) -> None:

        for x, y in objects.get("ground", []):
            tx, ty = int(x), int(y)
            self._ensure_size(ty + 1, tx + 1)
            if self._in_bounds(tx, ty):
                self.tiles[ty][tx] = CellTile(
                    sprite_key="ground", solid=True, redraw_sky_below=False
                )

        for x, y in objects.get("bricks", []):
            tx, ty = int(x), int(y)
            self._ensure_size(ty + 1, tx + 1)
            self.tiles[ty][tx] = CellTile(
                sprite_key="bricks",
                solid=True,
                redraw_sky_below=False,
            )

        for item in objects.get("pipe", []):
            if len(item) < 3:
                continue
            px, py, plen = int(item[0]), int(item[1]), int(item[2])
            self._ensure_size(py + plen + 26, px + 4)
            if not self._in_bounds(px, py):
                continue
            self.tiles[py][px] = CellTile(sprite_key="pipeL", solid=True, redraw_sky_below=False)
            self.tiles[py][px + 1] = CellTile(
                sprite_key="pipeR", solid=True, redraw_sky_below=True
            )
            for i in range(1, plen + 21):
                row_y = py + i
                if self._in_bounds(px, row_y):
                    self.tiles[row_y][px] = CellTile(
                        sprite_key="pipe2L",
                        solid=True,
                        redraw_sky_below=True,
                    )
                    self.tiles[row_y][px + 1] = CellTile(
                        sprite_key="pipe2R",
                        solid=True,
                        redraw_sky_below=True,
                    )

        for x, y in objects.get("cloud", []):
            base_x, base_y = int(x), int(y)
            self._ensure_size(base_y + 3, base_x + 4)
            pattern = ["cloud1_1", "cloud1_2", "cloud1_3", "cloud2_1", "cloud2_2", "cloud2_3"]
            idx = 0
            for yy in range(2):
                for xx in range(3):
                    if self._in_bounds(base_x + xx, base_y + yy):
                        self.tiles[base_y + yy][base_x + xx] = CellTile(
                            sprite_key=pattern[idx],
                            solid=False,
                            redraw_sky_below=True,
                        )
                    idx += 1

        for x, y in objects.get("bush", []):
            bx, by = int(x), int(y)
            self._ensure_size(by + 1, bx + 4)
            trio = ["bush_1", "bush_2", "bush_3"]
            for i, key in enumerate(trio):
                if self._in_bounds(bx + i, by):
                    self.tiles[by][bx + i] = CellTile(
                        sprite_key=key,
                        solid=False,
                        redraw_sky_below=True,
                    )

        # Sky patches (clear solid decorations back to sky)
        for x, y in objects.get("sky", []):
            tx, ty = int(x), int(y)
            self._ensure_size(ty + 1, tx + 1)
            cell = self.tiles[ty][tx]
            if (
                cell.solid
                and cell.sprite_key
                and (cell.sprite_key.startswith("pipe"))
            ):
                continue
            self.tiles[ty][tx] = CellTile(
                sprite_key="sky",
                solid=False,
                redraw_sky_below=False,
            )

        self.length_tiles = max(self.length_tiles, self.ncol)

    def _index_solids(self) -> None:
        self._solid.clear()
        for ty, row in enumerate(self.tiles):
            for tx, c in enumerate(row):
                if c.solid:
                    self._solid.add((tx, ty))

    def get_cell(self, tx: int, ty: int) -> Optional[CellTile]:
        if not self._in_bounds(tx, ty):
            return None
        return self.tiles[ty][tx]

    def set_cell(self, tx: int, ty: int, cell: CellTile) -> None:
        if not self._in_bounds(tx, ty):
            return
        self.tiles[ty][tx] = cell
        if cell.solid:
            self._solid.add((tx, ty))
        else:
            self._solid.discard((tx, ty))

    def break_tile(self, tx: int, ty: int, *, record_break: bool = True) -> bool:
        cell = self.get_cell(tx, ty)
        if not cell:
            return False
        if cell.sprite_key != "bricks":
            return False
        # Replace with sky (non-solid).
        self.set_cell(tx, ty, CellTile(sprite_key="sky", solid=False, redraw_sky_below=False))
        if record_break:
            self._broken_tiles.append((tx, ty))
        return True

    def consume_broken_tiles(self) -> List[Tuple[int, int]]:
        if not self._broken_tiles:
            return []
        out = self._broken_tiles[:]
        self._broken_tiles.clear()
        return out

    def handle_tile_hit_from_below(self, tx: int, ty: int, entity) -> bool:
        """
        Match legacy `client/classes/Level.handle_tile_hit_from_below`.
        Kivy client currently always uses a 'big' Mario, so bricks are breakable.
        """
        cell = self.get_cell(tx, ty)
        if not cell:
            return False
        if cell.sprite_key == "bricks":
            power = int(getattr(entity, "power_state", 2))
            if power >= 1:
                return self.break_tile(tx, ty)
        return False

    def is_solid_at_pixel(self, x: float, y: float) -> bool:
        tx = int(x // TILE)
        ty = int(y // TILE)
        return (tx, ty) in self._solid

    def tile_rect(self, tx: int, ty: int) -> Rect:
        return Rect(tx * TILE, ty * TILE, TILE, TILE)
