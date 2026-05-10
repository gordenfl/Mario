from __future__ import annotations

import math
from pathlib import Path

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, PopMatrix, PushMatrix, Rectangle, Scale, Translate
from kivy.uix.widget import Widget

from .input import TouchControls
from .level import TILE, Level
from .mario import Mario
from .projectiles import ProjectileSystem
from .sprites_loader import SpriteRepository, mario_pick_frame_name
from .effects import BrickDebrisSystem


def _world_to_kivy_y(screen_h: float, y_top: float, tex_h: float) -> float:
    return screen_h - y_top - tex_h


class GameView(Widget):
    CLIENT_ROOT = Path(__file__).resolve().parents[1] / "client"
    VIRTUAL_W = 852.0
    VIRTUAL_H = 480.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.controls = TouchControls()
        self.sprite_repo = SpriteRepository(self.CLIENT_ROOT)
        self.sprite_repo.load_all()

        self.level = Level.from_json(self.CLIENT_ROOT / "levels" / "Level1-1.json")
        self.mario = Mario(2, 10, self.level)
        self.projectiles = ProjectileSystem()
        self.effects = BrickDebrisSystem()
        self.camera_x = 0.0
        self._dt = 1.0 / 60.0
        self._tick_i = 0
        self._view_scale = 1.0
        self._view_offset = (0.0, 0.0)

        Clock.schedule_interval(self._tick, self._dt)

    def on_touch_down(self, touch):
        vx, vy = self._to_virtual(touch.x, touch.y)
        # Create a lightweight touch-like object with virtual coords for controls.
        touch_v = type("TouchV", (), {})()
        touch_v.x = vx
        touch_v.y = vy
        touch_v.uid = touch.uid
        return self.controls.on_touch_down(touch_v, self.VIRTUAL_W, self.VIRTUAL_H) or super().on_touch_down(touch)

    def on_touch_move(self, touch):
        vx, vy = self._to_virtual(touch.x, touch.y)
        touch_v = type("TouchV", (), {})()
        touch_v.x = vx
        touch_v.y = vy
        touch_v.uid = touch.uid
        return self.controls.on_touch_move(touch_v) or super().on_touch_move(touch)

    def on_touch_up(self, touch):
        vx, vy = self._to_virtual(touch.x, touch.y)
        touch_v = type("TouchV", (), {})()
        touch_v.x = vx
        touch_v.y = vy
        touch_v.uid = touch.uid
        return self.controls.on_touch_up(touch_v) or super().on_touch_up(touch)

    def _tick(self, _dt):
        joy = self.controls.joy
        self.mario.apply_controls(move_dir=joy.move_dir, jump=joy.jump, fire=self.controls.fire_pressed)
        self.mario.update()
        self._tick_i += 1

        if self.mario.consume_fire():
            direction = self.mario.heading or 1
            self.projectiles.spawn_fireball(
                self.mario.rect.centerx + direction * 20,
                self.mario.rect.centery - 10,
                direction,
            )
        self.projectiles.update(self.level)
        self.effects.update()

        # Brick break events -> debris
        broken = self.level.consume_broken_tiles()
        if broken:
            bricks = self.sprite_repo.static.get("bricks")
            if bricks:
                btex, bwh = bricks
                for tx, ty in broken:
                    self.effects.spawn_brick_break(tx, ty, btex, bwh)

        # Camera is computed in *virtual* pixels, independent of window scaling.
        target = -self.mario.rect.centerx + self.VIRTUAL_W * 0.5
        max_scroll = max(self.level.length_tiles * TILE - self.VIRTUAL_W, 0.0)
        self.camera_x = max(-max_scroll, min(0.0, target))

        self._redraw()

    def _compute_view_transform(self):
        w = float(self.width)
        h = float(self.height)
        if w <= 1 or h <= 1:
            self._view_scale = 1.0
            self._view_offset = (0.0, 0.0)
            return
        s = min(w / self.VIRTUAL_W, h / self.VIRTUAL_H)
        ox = (w - self.VIRTUAL_W * s) * 0.5
        oy = (h - self.VIRTUAL_H * s) * 0.5
        self._view_scale = s
        self._view_offset = (ox, oy)

    def _to_virtual(self, x: float, y: float):
        """Map window coords -> virtual framebuffer coords."""
        s = self._view_scale or 1.0
        ox, oy = self._view_offset
        vx = (x - ox) / s
        vy = (y - oy) / s
        return vx, vy

    def _draw_tiled_sky(self, w: float, h: float):
        sky = self.sprite_repo.static.get("sky")
        if not sky:
            Color(0.42, 0.71, 1.0, 1.0)
            Rectangle(pos=(0, 0), size=(w, h))
            return
        tex, (sw, sh) = sky
        Color(1, 1, 1, 1)

        wx0 = math.floor(-self.camera_x / sw) * sw
        ix_span = max(8, int(w / sw) + 8)
        iy_span = max(8, int(h / sh) + 8)

        for iy in range(iy_span):
            for ix in range(-2, ix_span):
                wx = wx0 + ix * sw
                sx = wx + self.camera_x
                screen_y_bottom = iy * sh
                Rectangle(texture=tex, pos=(sx, screen_y_bottom), size=(sw, sh))

    def _draw_cell_tile(self, h: float, tx: int, ty: int, cell):
        sx = tx * TILE + self.camera_x
        y_top = ty * TILE
        # World Y is top-left based. Convert tile's top (y_top) to Kivy's bottom-left.
        # screen_bottom = screen_h - world_top - tile_height
        screen_y_bottom_tile = _world_to_kivy_y(h, y_top, TILE)

        if cell.sprite_key == "sky" and not cell.redraw_sky_below:
            return

        if cell.redraw_sky_below:
            sky = self.sprite_repo.static.get("sky")
            if sky:
                stex, _ = sky
                Color(1, 1, 1, 1)
                Rectangle(
                    texture=stex,
                    pos=(sx, screen_y_bottom_tile),
                    size=(TILE, TILE),
                )

        if cell.sprite_key and cell.sprite_key != "sky":
            tup = self.sprite_repo.static.get(cell.sprite_key)
            if not tup:
                return
            tex, (tw2, th2) = tup
            Color(1, 1, 1, 1)
            y_draw = screen_y_bottom_tile + (TILE - th2)
            Rectangle(texture=tex, pos=(sx + (TILE - tw2) / 2, y_draw), size=(tw2, th2))

    def _redraw_mario(self, h: float):
        big_mario = self.mario.rect.h >= 48
        fname = mario_pick_frame_name(
            self.mario.on_ground,
            abs(self.mario.vel.x),
            self._tick_i,
            big=big_mario,
        )
        tup = self.sprite_repo.get_static(fname, flip_x=(self.mario.heading < 0))
        if not tup:
            Color(1.0, 0.2, 0.2, 1.0)
            mr = self.mario.rect
            Rectangle(
                pos=(mr.x + self.camera_x, _world_to_kivy_y(h, mr.y, mr.h)),
                size=(mr.w, mr.h),
            )
            return

        tex, (tw2, th2) = tup
        mr = self.mario.rect
        px = mr.x + self.camera_x
        py = _world_to_kivy_y(h, mr.y, th2)

        Color(1, 1, 1, 1)
        Rectangle(texture=tex, pos=(px, py), size=(tw2, th2))

    def _redraw_fireballs(self, h: float):
        for fb in self.projectiles.fireballs:
            r = fb.rect
            px = r.x + self.camera_x
            py = _world_to_kivy_y(h, r.y, r.h)
            Color(1.0, 0.55, 0.1, 0.92)
            Ellipse(pos=(px + 2, py + 2), size=(r.w - 4, r.h - 4))
            Color(1.0, 0.92, 0.45, 0.82)
            Ellipse(pos=(px + 5, py + 5), size=(r.w - 10, r.h - 10))

    def _redraw(self):
        self.canvas.clear()
        self._compute_view_transform()
        w = float(self.VIRTUAL_W)
        h = float(self.VIRTUAL_H)

        with self.canvas:
            # Letterbox background (window space)
            Color(0.0, 0.0, 0.0, 1.0)
            Rectangle(pos=(0, 0), size=(self.width, self.height))

            # Apply transform to draw the virtual framebuffer.
            PushMatrix()
            Translate(self._view_offset[0], self._view_offset[1])
            Scale(self._view_scale, self._view_scale, 1.0)

            self._draw_tiled_sky(w, h)

            tx0 = int((-self.camera_x) // TILE) - 2
            tx1 = int(((-self.camera_x) + w) // TILE) + 3

            # Only draw tiles that could intersect the current viewport vertically.
            # Without this, high-DPI window sizes may show far-below "underground" tiles.
            max_visible_ty = int(h // TILE) + 4
            for ty in range(min(len(self.level.tiles), max_visible_ty)):
                for tx in range(max(0, tx0), min(self.level.ncol, tx1)):
                    cell = self.level.tiles[ty][tx]
                    self._draw_cell_tile(h, tx, ty, cell)

            self._redraw_mario(h)
            self._redraw_fireballs(h)
            self.effects.draw(self.camera_x, self.VIRTUAL_H)

            if self.controls.joy.active:
                cx, cy = self.controls.joy.center
                kx, ky = self.controls.joy.knob
                Color(0.0, 0.0, 0.0, 0.18)
                Ellipse(pos=(cx - 48, cy - 48), size=(96, 96))
                Color(1.0, 1.0, 1.0, 0.18)
                Ellipse(pos=(kx - 28, ky - 28), size=(56, 56))

            PopMatrix()
