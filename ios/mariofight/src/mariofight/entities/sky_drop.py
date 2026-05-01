import random
from copy import copy

import pygame

from entities.EntityBase import EntityBase


class SkyDrop(EntityBase):
    def __init__(
        self,
        drop_type: str,
        spawn_x: float,
        screen,
        level,
        sprite_collection,
        sound,
        gravity: float = 0.55,
    ):
        super().__init__(0, 0, gravity)
        self.drop_type = drop_type
        self.is_sky_drop = True
        self.screen = screen
        self.level = level
        self.sprite_collection = sprite_collection
        self.sound = sound
        self.rect = pygame.Rect(0, 0, 28, 28)
        self.rect.centerx = int(spawn_x)
        self.rect.y = -self.rect.height
        self.pos_x = float(self.rect.x)
        self.pos_y = float(self.rect.y)
        self.type = "Drop"
        self.drop_id = None
        self.spawned_entity = None
        self.initial_direction = None
        self.direction_callback = None
        if drop_type == "coin":
            self.animation = copy(self.sprite_collection.get("coin").animation)
        else:
            self.animation = None
            self.image = self.sprite_collection.get("mushroom").image

    def update(self, camera):
        if not self.alive:
            return
        self.vel.y += self.gravity
        self.pos_y += self.vel.y
        self.rect.y = int(self.pos_y)
        level_height = len(self.level.level or []) * 32 if self.level.level else self.screen.get_height()
        if self.rect.top > level_height + 64:
            self.alive = None
            return
        if self.level.is_solid_at_pixel(self.rect.centerx, self.rect.bottom + 1):
            landing_tile = int((self.rect.bottom + 1) // 32)
            landing_y = landing_tile * 32
            spawn_x = self.rect.centerx
            if self.drop_type == "coin":
                coin = SkyCoin(spawn_x, landing_y, self.screen, self.level, self.sprite_collection)
                coin.drop_id = self.drop_id
                self.level.entityList.append(coin)
                self.spawned_entity = coin
            else:
                direction = self.initial_direction
                mushroom = SkyMushroom(
                    spawn_x,
                    landing_y,
                    self.screen,
                    self.level,
                    self.sprite_collection,
                    initial_direction=direction,
                )
                mushroom.drop_id = self.drop_id
                mushroom.direction_callback = self.direction_callback
                if direction in (-1, 1):
                    mushroom.apply_direction(direction)
                self.level.entityList.append(mushroom)
                self.spawned_entity = mushroom
            self.alive = None
            return

        draw_x = self.rect.x + camera.x
        draw_pos = (draw_x, self.rect.y)
        if self.drop_type == "coin" and self.animation:
            self.animation.update()
            self.screen.blit(self.animation.image, draw_pos)
        else:
            self.screen.blit(self.image, draw_pos)


class SkyCoin(EntityBase):
    def __init__(self, spawn_x: float, landing_y: int, screen, level, sprite_collection):
        super().__init__(0, 0, 0)
        self.drop_type = "coin"
        self.type = "Item"
        self.screen = screen
        self.level = level
        self.animation = copy(sprite_collection.get("coin").animation)
        self.rect = pygame.Rect(0, 0, 24, 24)
        self.rect.centerx = int(spawn_x)
        self.rect.bottom = landing_y
        self.drop_id = None

    def update(self, camera):
        if not self.alive:
            return
        level_height = len(self.level.level or []) * 32 if self.level.level else self.screen.get_height()
        if self.rect.top > level_height + 32:
            self.alive = None
            return
        self.animation.update()
        self.screen.blit(self.animation.image, (self.rect.x + camera.x, self.rect.y))


class SkyMushroom(EntityBase):
    def __init__(
        self,
        spawn_x: float,
        landing_y: int,
        screen,
        level,
        sprite_collection,
        gravity: float = 0.6,
        initial_direction=None,
    ):
        super().__init__(0, 0, gravity)
        self.drop_type = "mushroom"
        self.type = "Item"
        self.screen = screen
        self.level = level
        self.image = sprite_collection.get("mushroom").image
        self.rect = pygame.Rect(0, 0, 28, 28)
        self.rect.centerx = int(spawn_x)
        self.rect.bottom = landing_y
        self.pos_x = float(self.rect.x)
        self.pos_y = float(self.rect.y)
        self.speed = 1.2
        direction = initial_direction if initial_direction in (-1, 1) else random.choice([-1, 1])
        self.direction = direction
        self.vel.x = self.speed * self.direction
        self.vel.y = 0
        self.just_landed = False
        self.landing_cooldown = 0
        self.was_on_ground = False
        self.drop_id = None
        self.waiting_direction = False
        self.pending_collision = None
        self.last_prev_x = self.pos_x
        self.direction_callback = None

    def update(self, camera):
        if not self.alive:
            return
        self.vel.y += self.gravity
        self.pos_y += self.vel.y
        self.rect.y = int(self.pos_y)

        below = self.rect.bottom + 1
        on_ground = self.level.is_solid_at_pixel(self.rect.centerx, below)
        if on_ground:
            landing_tile = int(below // 32)
            landing_y = landing_tile * 32
            self.rect.bottom = landing_y
            self.pos_y = float(self.rect.y)
            self.vel.y = 0
            if not self.was_on_ground:
                self.landing_cooldown = 2
            self.was_on_ground = True
            self.just_landed = True
        else:
            self.just_landed = False
            if self.waiting_direction:
                self.waiting_direction = False
                self.pending_collision = None
            self.was_on_ground = False

        prev_x = self.pos_x
        if not self.waiting_direction:
            self.vel.x = self.speed * self.direction
            self.pos_x += self.vel.x
        else:
            self.vel.x = 0
        self.rect.x = int(self.pos_x)

        if on_ground:
            left_block = self.level.is_solid_at_pixel(self.rect.left - 1, self.rect.bottom - 4)
            right_block = self.level.is_solid_at_pixel(self.rect.right + 1, self.rect.bottom - 4)
            if self.landing_cooldown > 0:
                self.landing_cooldown -= 1
            elif left_block or right_block:
                self.pos_x = prev_x
                self.rect.x = int(self.pos_x)
                if not self.waiting_direction:
                    self.pending_collision = "left" if left_block else "right"
                    self.waiting_direction = True
                    if self.direction_callback and self.drop_id:
                        self.direction_callback(self.drop_id, self.pending_collision)
                self.just_landed = False
        elif self.just_landed:
            self.just_landed = False

        level_height = len(self.level.level or []) * 32 if self.level.level else self.screen.get_height()
        if self.rect.top > level_height + 64:
            self.alive = None
            return

        self.screen.blit(self.image, (self.rect.x + camera.x, self.rect.y))

    def apply_direction(self, direction: float):
        if direction not in (-1, 1, 0):
            return
        if direction == 0:
            self.direction = 0
            self.waiting_direction = True
            self.vel.x = 0
        else:
            self.direction = 1 if direction > 0 else -1
            self.waiting_direction = False
            self.pending_collision = None
            self.vel.x = self.speed * self.direction
            self.landing_cooldown = max(self.landing_cooldown, 1)

    def clear_collision_request(self):
        self.pending_collision = None
        self.waiting_direction = False
        if self.direction_callback and self.drop_id:
            self.direction_callback(self.drop_id, None)
