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
        self.prev_position = [0, 0]
        self.state = {
            "position": [0, 0],
            "velocity": [0, 0],
            "hp": 30,
            "power": 0,
            "score": 0,
        }

    def update_from_state(self, state: dict):
        position = state.get("position", self.state["position"])
        self.state.update(state)
        self.rect.x = int(position[0])
        self.rect.y = int(position[1])
        dx = position[0] - self.prev_position[0]
        dy = position[1] - self.prev_position[1]
        power = self.state.get("power", 0)
        if power >= 1:
            if self.current_animation is not self.big_animation:
                self.current_animation = self.big_animation
            self.rect.height = 64
        else:
            if self.current_animation is not self.small_animation:
                self.current_animation = self.small_animation
            self.rect.height = 48
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
        surface.blit(image, draw_rect)
        font = get_font(18)
        label = font.render(self.username, True, (255, 255, 255))
        surface.blit(label, (draw_rect.x, draw_rect.y - 16))
