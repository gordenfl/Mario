import random

from classes.Collider import Collider


class LeftRightWalkTrait:
    def __init__(self, entity, level):
        self.direction = random.choice([-1, 1])
        self.entity = entity
        self.collDetection = Collider(self.entity, level)
        self.speed = 1
        self.entity.vel.x = self.speed * self.direction

    def on_wall_collision(self, side: int) -> None:
        """Turn around after hitting a wall. side: 1 = blocked moving right, -1 = blocked moving left."""
        if side > 0:
            self.direction = -1
        else:
            self.direction = 1

    def update(self):
        self.entity.vel.x = self.speed * self.direction
        self.moveEntity()

    def moveEntity(self):
        self.entity.rect.y += self.entity.vel.y
        self.collDetection.checkY()
        self.entity.rect.x += self.entity.vel.x
        self.collDetection.checkX()
