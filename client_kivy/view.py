from __future__ import annotations

from pathlib import Path

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Rectangle
from kivy.uix.widget import Widget

from .input import TouchControls
from .level import Level, TILE
from .mario import Mario
from .projectiles import ProjectileSystem


def _world_to_kivy_y(screen_h: float, y_top: float, height: float) -> float:
    # World origin is top-left; Kivy origin is bottom-left.
    return screen_h - y_top - height


class GameView(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.controls = TouchControls()
        self.level = Level.from_json(Path(__file__).resolve().parents[1] / "client" / "levels" / "Level1-1.json")
        self.mario = Mario(2, 10, self.level)
        self.projectiles = ProjectileSystem()
        self.camera_x = 0.0
        self._dt = 1.0 / 60.0

        Clock.schedule_interval(self._tick, self._dt)

    def on_touch_down(self, touch):
        return self.controls.on_touch_down(touch, self.width, self.height) or super().on_touch_down(touch)

    def on_touch_move(self, touch):
        return self.controls.on_touch_move(touch) or super().on_touch_move(touch)

    def on_touch_up(self, touch):
        return self.controls.on_touch_up(touch) or super().on_touch_up(touch)

    def _tick(self, _dt):
        # Controls -> mario
        joy = self.controls.joy
        self.mario.apply_controls(move_dir=joy.move_dir, jump=joy.jump, fire=self.controls.fire_pressed)
        self.mario.update()

        if self.mario.consume_fire():
            direction = self.mario.heading or 1
            self.projectiles.spawn_fireball(self.mario.rect.centerx + direction * 20, self.mario.rect.centery - 10, direction)
        self.projectiles.update(self.level)

        # Camera center on mario
        target = -self.mario.rect.centerx + self.width * 0.5
        max_scroll = max(self.level.length_tiles * TILE - self.width, 0.0)
        self.camera_x = max(-max_scroll, min(0.0, target))

        self._redraw()

    def _redraw(self):
        self.canvas.clear()
        w = float(self.width)
        h = float(self.height)

        with self.canvas:
            # Background sky
            Color(0.42, 0.71, 1.0, 1.0)
            Rectangle(pos=(0, 0), size=(w, h))

            # Solid tiles
            Color(0.35, 0.25, 0.15, 1.0)
            for tx, ty in self.level.iter_visible_tiles(self.camera_x, w, h):
                x = tx * TILE + self.camera_x
                y_top = ty * TILE
                Rectangle(pos=(x, _world_to_kivy_y(h, y_top, TILE)), size=(TILE, TILE))

            # Mario
            Color(1.0, 0.2, 0.2, 1.0)
            mr = self.mario.rect
            Rectangle(
                pos=(mr.x + self.camera_x, _world_to_kivy_y(h, mr.y, mr.h)),
                size=(mr.w, mr.h),
            )

            # Fireballs
            Color(1.0, 0.65, 0.15, 1.0)
            for fb in self.projectiles.fireballs:
                r = fb.rect
                Ellipse(
                    pos=(r.x + self.camera_x, _world_to_kivy_y(h, r.y, r.h)),
                    size=(r.w, r.h),
                )

            # Joystick visuals (semi-transparent)
            if self.controls.joy.active:
                cx, cy = self.controls.joy.center
                kx, ky = self.controls.joy.knob
                Color(0.0, 0.0, 0.0, 0.18)
                Ellipse(pos=(cx - 48, cy - 48), size=(96, 96))
                Color(1.0, 1.0, 1.0, 0.18)
                Ellipse(pos=(kx - 28, ky - 28), size=(56, 56))

