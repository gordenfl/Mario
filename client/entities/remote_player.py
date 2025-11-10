import pygame
from pygame.transform import flip

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
        self.current_animation = self.small_animation
        self.heading = 1
        self.color = color
        self.rect = pygame.Rect(0, 0, 32, 48)
        self.visible = False
        self.is_dying = False
        self.death_timer = 0
        self.prev_position = [0, 0]
        self.hurt_timer = 0
        self.state = {
            "position": [0, 0],
            "velocity": [0, 0],
            "hp": 30,
            "power": 0,
            "score": 0,
        }

    def update_from_state(self, state: dict):
        old_hp = self.state.get("hp", 30)
        position = state.get("position", self.state["position"])
        self.state.update(state)
        self.rect.x = int(position[0])
        self.rect.y = int(position[1])
        new_hp = self.state.get("hp", old_hp)
        if new_hp < old_hp and new_hp > 0:
            self.trigger_hurt()
        prev_pos = self.prev_position if hasattr(self, "prev_position") else [position[0], position[1]]
        dx = position[0] - prev_pos[0]
        dy = position[1] - prev_pos[1]
        dying = state.get("dying", False)
        death_timer = state.get("death_timer", 0)
        if dying:
            if not self.is_dying:
                self.current_animation = self.small_animation
                self.current_animation.inAir()
            self.is_dying = True
            self.death_timer = death_timer
            self.heading = 0
            self.rect.height = 48
        else:
            self.is_dying = False
            self.death_timer = 0

        power = self.state.get("power", 0)
        if not self.is_dying:
            if power >= 1:
                if self.current_animation is not self.big_animation:
                    self.current_animation = self.big_animation
                self.rect.height = 64
            else:
                if self.current_animation is not self.small_animation:
                    self.current_animation = self.small_animation
                self.rect.height = 48
        else:
            self.current_animation.inAir()

        if not self.is_dying:
            if dx > 0.5:
                self.heading = 1
                self.current_animation.update()
            elif dx < -0.5:
                self.heading = -1
                self.current_animation.update()
            else:
                self.current_animation.idle()
            if abs(dy) > 1.0:
                self.current_animation.inAir()
        else:
            self.current_animation.inAir()

        self.prev_position = list(position)
        self.visible = True

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
        timer_value = self.hurt_timer
        if self.hurt_timer > 0:
            self.hurt_timer -= 1
        skip_frame = hurt_active and ((timer_value // 2) % 2 == 1)
        if not skip_frame:
            surface.blit(image, draw_rect)
        font = get_font(18)
        label_color = (255, 200, 200) if hurt_active else (255, 255, 255)
        label = font.render(self.username, True, label_color)
        label_rect = label.get_rect(midbottom=(draw_rect.centerx, draw_rect.y - 2))
        surface.blit(label, label_rect)

    def trigger_hurt(self):
        self.hurt_timer = max(self.hurt_timer, 30)
