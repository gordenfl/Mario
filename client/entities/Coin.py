from copy import copy

from entities.EntityBase import EntityBase


class Coin(EntityBase):
    def __init__(self, screen, spriteCollection, x, y, gravity=0):
        super(Coin, self).__init__(x, y, gravity)
        self.screen = screen
        self.spriteCollection = spriteCollection
        self.animation = copy(self.spriteCollection.get("coin").animation)
        self.type = "Item"
        width = 24
        height = 24
        try:
            frame = self.animation.image
            if frame:
                rect = frame.get_rect()
                width, height = rect.width, rect.height
        except AttributeError:
            pass
        tile_left = x * 32
        tile_bottom = (y + 1) * 32
        self.rect.width = width
        self.rect.height = height
        self.rect.centerx = tile_left + 16
        self.rect.bottom = tile_bottom

    def update(self, cam):
        if self.alive:
            self.animation.update()
            draw_x = self.rect.x + cam.x
            self.screen.blit(self.animation.image, (draw_x, self.rect.y))
