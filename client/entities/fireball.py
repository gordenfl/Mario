import math
import pygame


class Fireball:
    def __init__(
        self,
        bullet_id: str,
        owner: str,
        position,
        direction: int,
        speed: float,
        level,
        gravity: float = 0.45,
        bounce_factor: float = 1.0,
    ):
        self.id = bullet_id
        self.owner = owner
        self.direction = 1 if direction >= 0 else -1
        self.base_speed = max(0.1, speed)
        self.level = level
        self.gravity = gravity
        self.bounce_factor = bounce_factor
        self.x = float(position[0])
        self.y = float(position[1])
        diag_speed = self.base_speed / math.sqrt(2)
        self.vx = diag_speed * self.direction
        self.vy = diag_speed
        self.bounce_vertical_speed = diag_speed * abs(self.bounce_factor)
        self.rect = pygame.Rect(0, 0, 16, 16)
        self.rect.center = (int(self.x), int(self.y))
        self.lifetime_frames = 0
        self.max_lifetime_frames = 360
        self.bounces = 0
        self.hit_wall = False

    def update(self):
        self.vy += self.gravity
        self.x += self.vx
        self.y += self.vy
        self.rect.center = (int(self.x), int(self.y))
        self._resolve_ground_collision()
        self.lifetime_frames += 1

    def _resolve_ground_collision(self):
        if not self.level:
            return
        # If moving downward, check the tile directly beneath the fireball
        if self.vy >= 0:
            bottom_x = self.rect.centerx
            bottom_y = self.rect.bottom + 1
            if self.level.is_solid_at_pixel(bottom_x, bottom_y):
                tile_y = int(bottom_y // 32)
                tile_top = tile_y * 32
                self.y = tile_top - self.rect.height / 2 - 1
                self.rect.centery = int(self.y)
                self.vy = -self.bounce_vertical_speed
                self.bounces += 1
        # Small horizontal nudge if embedded into wall
        left_x = self.rect.left - 1
        right_x = self.rect.right + 1
        mid_y = self.rect.centery
        if self.level.is_solid_at_pixel(left_x, mid_y):
            self.hit_wall = True
            return
        elif self.level.is_solid_at_pixel(right_x, mid_y):
            self.hit_wall = True
            return

    def should_despawn(self, level_width: int) -> bool:
        if self.rect.right < 0 or self.rect.left > level_width:
            return True
        if self.lifetime_frames > self.max_lifetime_frames:
            return True
        return self.hit_wall

    def draw(self, surface: pygame.Surface, camera_world_x: float, camera_world_y: float):
        draw_rect = self.rect.copy()
        draw_rect.x -= int(camera_world_x)
        draw_rect.y -= int(camera_world_y)
        center = draw_rect.center
        pygame.draw.circle(surface, (255, 140, 32), center, 6)
        pygame.draw.circle(surface, (255, 230, 160), center, 3)
