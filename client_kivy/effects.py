from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image
from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture

from .level import TILE
from .sprites_loader import pil_to_texture

# Matches client/entities/brick_debris.py BrickDebrisEffect.lifetime
BRICK_DEBRIS_LIFETIME_FRAMES = 45


@dataclass
class BrickPiece:
    tex: Texture
    size: Tuple[int, int]
    pos: List[float]  # [x, y] in world pixels (top-left origin)
    vel: List[float]  # [vx, vy] in pixels/frame


@dataclass
class BrickBreakEffect:
    """One brick break: shared lifetime like pygame BrickDebrisEffect."""

    pieces: List[BrickPiece]
    ttl: int = BRICK_DEBRIS_LIFETIME_FRAMES


class BrickDebrisSystem:
    def __init__(self) -> None:
        self._effects: List[BrickBreakEffect] = []
        self.gravity = 0.6
        self._brick_quads: Optional[List[Tuple[Texture, Tuple[int, int]]]] = None

    def clear(self) -> None:
        self._effects.clear()

    def _ensure_quads(self, bricks_tex: Texture, bricks_wh: Tuple[int, int]) -> None:
        if self._brick_quads is not None:
            return
        w, h = bricks_wh
        im = Image.frombytes("RGBA", (w, h), bricks_tex.pixels)
        qw, qh = max(1, w // 2), max(1, h // 2)
        quads: List[Tuple[Texture, Tuple[int, int]]] = []
        for qy in range(2):
            for qx in range(2):
                crop = im.crop((qx * qw, qy * qh, (qx + 1) * qw, (qy + 1) * qh)).copy()
                tex = pil_to_texture(crop)
                tex.mag_filter = "nearest"
                tex.min_filter = "nearest"
                quads.append((tex, (qw, qh)))
        self._brick_quads = quads

    def spawn_brick_break(self, tile_x: int, tile_y: int, bricks_tex: Texture, bricks_wh: Tuple[int, int]) -> None:
        self._ensure_quads(bricks_tex, bricks_wh)
        if not self._brick_quads:
            return

        base_x = tile_x * TILE
        base_y = tile_y * TILE
        offsets = [(-12, -14), (12, -16), (-10, -6), (10, -8)]
        velocities = [(-3.2, -9.5), (3.2, -10), (-2.4, -7), (2.4, -7.5)]
        pieces: List[BrickPiece] = []
        for idx in range(4):
            tex, (pw, ph) = self._brick_quads[idx]
            ox, oy = offsets[idx]
            vx, vy = velocities[idx]
            pieces.append(
                BrickPiece(
                    tex=tex,
                    size=(pw, ph),
                    pos=[base_x + ox, base_y + oy],
                    vel=[vx, vy],
                )
            )
        self._effects.append(BrickBreakEffect(pieces=pieces, ttl=BRICK_DEBRIS_LIFETIME_FRAMES))

    def update(self) -> None:
        # Same order as pygame BrickDebrisEffect.update: lifetime -= 1, then integrate.
        # Last frame is when ttl becomes 0 after decrement (still simulate + draw).
        alive: List[BrickBreakEffect] = []
        for eff in self._effects:
            eff.ttl -= 1
            if eff.ttl < 0:
                continue
            for p in eff.pieces:
                p.vel[1] += self.gravity
                p.pos[0] += p.vel[0]
                p.pos[1] += p.vel[1]
            alive.append(eff)
        self._effects = alive

    def draw(self, camera_x: float, virtual_h: float, max_y: float = 4000.0) -> None:
        for eff in self._effects:
            for p in eff.pieces:
                if p.pos[1] > max_y:
                    continue
                x = p.pos[0] + camera_x
                y = virtual_h - p.pos[1] - p.size[1]
                Color(1, 1, 1, 1)
                Rectangle(texture=p.tex, pos=(x, y), size=p.size)
