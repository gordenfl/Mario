import pygame
from pygame.transform import flip
from typing import Optional
import time

from classes.Animation import Animation
from classes.Sprites import Sprites
from ui.widgets import get_font


class RemotePlayer:
    """Simplified representation of another player in the room."""

    def __init__(self, username: str, color=(0, 120, 255)):
        self.username = username
        sprite_collection = Sprites().spriteCollection
        self.small_animation = Animation(
            [
                sprite_collection["mario_run1"].image,
                sprite_collection["mario_run2"].image,
                sprite_collection["mario_run3"].image,
            ],
            sprite_collection["mario_idle"].image,
            sprite_collection["mario_jump"].image,
        )
        self.big_animation = Animation(
            [
                sprite_collection["mario_big_run1"].image,
                sprite_collection["mario_big_run2"].image,
                sprite_collection["mario_big_run3"].image,
            ],
            sprite_collection["mario_big_idle"].image,
            sprite_collection["mario_big_jump"].image,
        )
        self.current_animation = self.big_animation
        self.heading = 1
        self.color = color
        self.rect = pygame.Rect(0, 0, 32, 64)
        self.visible = False
        self.is_dying = False
        self.death_timer = 0
        self.prev_position = [0, 0]
        self.hurt_timer = 0
        self.last_udp_timestamp = 0
        self.last_udp_monotonic = 0.0
        self.force_big_mario = True
        self.idle_position_epsilon = 0.8
        self.idle_velocity_epsilon = 0.08
        self.moving_frames = 0
        self.still_frames = 0
        self.is_moving_state = False
        self.state = {
            "position": [0, 0],
            "velocity": [0, 0],
            "hp": 30,
            "power": 0,
            "score": 0,
        }

    def update_from_state(self, state: dict):
        # If UDP updates are active, ignore low-frequency TCP state updates
        # for a short window to prevent position jitter/flicker.
        now = time.monotonic()
        if self.last_udp_monotonic and (now - self.last_udp_monotonic) < 0.45:
            return
        old_hp = self.state.get("hp", 30)
        position = state.get("position", self.state["position"])
        self.state.update(state)
        new_hp = self.state.get("hp", old_hp)
        if new_hp < old_hp and new_hp > 0:
            self.trigger_hurt()
        dying = state.get("dying", False)
        death_timer = state.get("death_timer", 0)
        if dying:
            if not self.is_dying:
                self.current_animation = self.big_animation if self.force_big_mario else self.small_animation
                self.current_animation.inAir()
            self.is_dying = True
            self.death_timer = death_timer
            self.heading = 0
            self.rect.height = 64 if self.force_big_mario else 48
        else:
            self.is_dying = False
            self.death_timer = 0

        power = self.state.get("power", 0)
        if not self.is_dying:
            if self.force_big_mario:
                if self.current_animation is not self.big_animation:
                    self.current_animation = self.big_animation
                self.rect.height = 64
            elif power >= 1:
                if self.current_animation is not self.big_animation:
                    self.current_animation = self.big_animation
                self.rect.height = 64
            else:
                if self.current_animation is not self.small_animation:
                    self.current_animation = self.small_animation
                self.rect.height = 48
        else:
            self.current_animation.inAir()

        velocity = state.get("velocity", self.state.get("velocity", [0, 0]))
        flags = state.get("flags")
        heading = state.get("heading")
        on_ground = bool(flags & 0b0001) if isinstance(flags, int) else None
        if isinstance(flags, int):
            self.state["flags"] = flags
        vx = velocity[0] if isinstance(velocity, (list, tuple)) and len(velocity) > 0 else 0.0
        vy = velocity[1] if isinstance(velocity, (list, tuple)) and len(velocity) > 1 else 0.0
        timestamp = state.get("timestamp")
        if isinstance(timestamp, int) and self.last_udp_timestamp and timestamp < self.last_udp_timestamp:
            return
        self._apply_motion(position[0], position[1], vx, vy, heading, on_ground, timestamp)
        self.state["velocity"] = [vx, vy]
        self.state["position"] = [position[0], position[1]]

    def draw(self, surface: pygame.Surface, camera_world_x: float, camera_world_y: float):
        if not self.visible:
            return
        draw_rect = self.rect.copy()
        draw_rect.x -= int(camera_world_x)
        draw_rect.y -= int(camera_world_y)
        image = self.current_animation.image
        if self.heading == -1:
            image = flip(image, True, False)
        hurt_active = self.hurt_timer > 0
        if self.hurt_timer > 0:
            self.hurt_timer -= 1
        # Keep remote player continuously visible; use label tint for hurt feedback
        # instead of frame skipping to avoid perceived flicker on wider-sync updates.
        surface.blit(image, draw_rect)
        font = get_font(18)
        label_color = (255, 200, 200) if hurt_active else (255, 255, 255)
        label = font.render(self.username, True, label_color)
        label_rect = label.get_rect(midbottom=(draw_rect.centerx, draw_rect.y - 2))
        surface.blit(label, label_rect)

    def trigger_hurt(self):
        self.hurt_timer = max(self.hurt_timer, 30)

    def apply_udp_state(self, state: dict, timestamp: Optional[int] = None):
        if isinstance(timestamp, int) and self.last_udp_timestamp and timestamp < self.last_udp_timestamp:
            return
        x = state.get("x", self.rect.x)
        y = state.get("y", self.rect.y)
        vx = state.get("vx", 0.0)
        vy = state.get("vy", 0.0)
        flags = state.get("flags", 0)
        heading = state.get("heading", self.heading)
        self.state["flags"] = flags
        on_ground = bool(flags & 0b0001)
        self._apply_motion(x, y, vx, vy, heading, on_ground, timestamp)
        self.last_udp_monotonic = time.monotonic()

    def apply_snapshot(self, snapshot: dict):
        timestamp = snapshot.get("timestamp")
        if isinstance(timestamp, int) and self.last_udp_timestamp and timestamp < self.last_udp_timestamp:
            return
        if self.last_udp_monotonic and (time.monotonic() - self.last_udp_monotonic) < 0.35:
            return
        position = snapshot.get("position", [self.rect.x, self.rect.y])
        velocity = snapshot.get("velocity", [0.0, 0.0])
        heading = snapshot.get("heading", self.heading)
        flags = snapshot.get("flags")
        on_ground = bool(flags & 0b0001) if isinstance(flags, int) else None
        if isinstance(flags, int):
            self.state["flags"] = flags
        self._apply_motion(
            position[0],
            position[1],
            velocity[0] if len(velocity) > 0 else 0.0,
            velocity[1] if len(velocity) > 1 else 0.0,
            heading,
            on_ground,
            timestamp,
        )

    def _apply_motion(self, x: float, y: float, vx: float, vy: float, heading: Optional[int], on_ground: Optional[bool], timestamp: Optional[int]):
        prev_pos = self.prev_position if hasattr(self, "prev_position") else [self.rect.x, self.rect.y]
        dx = x - prev_pos[0]
        dy = y - prev_pos[1]
        move_signal = abs(vx) > self.idle_velocity_epsilon or abs(dx) > self.idle_position_epsilon

        # Suppress tiny network jitter while idle to prevent texture flicker.
        if not move_signal and abs(dy) < self.idle_position_epsilon:
            x = prev_pos[0]
            y = prev_pos[1]
            dx = 0.0
            dy = 0.0

        # Hysteresis: avoid toggling run/idle on one-frame jitter.
        if move_signal:
            self.moving_frames += 1
            self.still_frames = 0
        else:
            self.still_frames += 1
            self.moving_frames = 0
        if not self.is_moving_state and self.moving_frames >= 2:
            self.is_moving_state = True
        elif self.is_moving_state and self.still_frames >= 4:
            self.is_moving_state = False

        if heading is None:
            if dx > 0.5:
                heading = 1
            elif dx < -0.5:
                heading = -1
            else:
                heading = self.heading
        # Keep facing stable when idle; only turn when movement is meaningful.
        if self.is_moving_state and heading is not None:
            self.heading = heading
        if on_ground is None:
            on_ground = abs(vy) < 0.8 and abs(dy) < 1.5
        if self.is_dying:
            self.current_animation.inAir()
        else:
            if not on_ground:
                self.current_animation.inAir()
            else:
                if self.is_moving_state:
                    self.current_animation.update()
                else:
                    self.current_animation.idle()
        self.rect.x = int(x)
        self.rect.y = int(y)
        self.prev_position = [x, y]
        self.visible = True
        if timestamp is not None:
            self.last_udp_timestamp = timestamp
        self.state["position"] = [x, y]
        self.state["velocity"] = [vx, vy]
