from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class JoystickState:
    active: bool = False
    center: Tuple[float, float] = (0.0, 0.0)
    knob: Tuple[float, float] = (0.0, 0.0)
    move_dir: float = 0.0  # [-1..1]
    jump: bool = False     # up direction


class TouchControls:
    """
    Screen split in half:
    - Left half: virtual joystick at bottom-left area.
    - Right half: tap anywhere to fire (momentary).
    """

    def __init__(self) -> None:
        self.joy = JoystickState()
        self._joy_touch_uid: Optional[int] = None
        self.fire_pressed: bool = False

        # Tunables
        self.deadzone = 0.10
        self.joy_radius = 64.0

    def on_touch_down(self, touch, screen_w: float, screen_h: float) -> bool:
        if touch.x < screen_w * 0.5:
            # Start joystick
            self._joy_touch_uid = touch.uid
            cx = min(max(touch.x, 70.0), screen_w * 0.5 - 20.0)
            cy = min(max(touch.y, 70.0), screen_h - 70.0)
            self.joy.active = True
            self.joy.center = (cx, cy)
            self.joy.knob = (cx, cy)
            self._recalc_joy(touch.x, touch.y)
            return True
        else:
            self.fire_pressed = True
            return True

    def on_touch_move(self, touch) -> bool:
        if self._joy_touch_uid is not None and touch.uid == self._joy_touch_uid:
            self._recalc_joy(touch.x, touch.y)
            return True
        return False

    def on_touch_up(self, touch) -> bool:
        if self._joy_touch_uid is not None and touch.uid == self._joy_touch_uid:
            self._joy_touch_uid = None
            self.joy.active = False
            self.joy.move_dir = 0.0
            self.joy.jump = False
            return True
        self.fire_pressed = False
        return False

    def _recalc_joy(self, x: float, y: float) -> None:
        cx, cy = self.joy.center
        dx = x - cx
        dy = y - cy
        r = (dx * dx + dy * dy) ** 0.5
        if r > self.joy_radius and r > 0:
            scale = self.joy_radius / r
            dx *= scale
            dy *= scale
        self.joy.knob = (cx + dx, cy + dy)

        # Horizontal direction
        nx = dx / self.joy_radius if self.joy_radius else 0.0
        if abs(nx) < self.deadzone:
            nx = 0.0
        self.joy.move_dir = max(-1.0, min(1.0, nx))

        # Up=jump (with a little threshold)
        ny = dy / self.joy_radius if self.joy_radius else 0.0
        self.joy.jump = ny > 0.45

