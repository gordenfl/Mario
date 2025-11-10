import pygame


class BrickDebrisEffect:
    def __init__(self, sprite_collection, screen, tile_x: int, tile_y: int):
        self.screen = screen
        self.sprite_collection = sprite_collection
        self.tile_x = tile_x
        self.tile_y = tile_y
        self.pieces = []
        self.gravity = 0.6
        self.lifetime = 45
        self.done = False
        self._build_pieces()

    def _build_pieces(self):
        sprite = self.sprite_collection.get("bricks")
        if sprite:
            source = sprite.image
        else:
            source = None
        base_x = self.tile_x * 32
        base_y = self.tile_y * 32
        offsets = [(-12, -14), (12, -16), (-10, -6), (10, -8)]
        velocities = [(-3.2, -9.5), (3.2, -10), (-2.4, -7), (2.4, -7.5)]
        size = 8
        for idx in range(4):
            if source:
                piece_surface = pygame.Surface((size, size), pygame.SRCALPHA)
                src_rect = pygame.Rect((idx % 2) * size, (idx // 2) * size, size, size)
                piece_surface.blit(source, (0, 0), src_rect)
            else:
                piece_surface = pygame.Surface((size, size), pygame.SRCALPHA)
                piece_surface.fill((237, 140, 57))
            self.pieces.append(
                {
                    "image": piece_surface,
                    "pos": [base_x + offsets[idx][0], base_y + offsets[idx][1]],
                    "vel": list(velocities[idx]),
                }
            )

    def update(self, camera):
        if self.done:
            return
        self.lifetime -= 1
        for piece in self.pieces:
            piece["vel"][1] += self.gravity
            piece["pos"][0] += piece["vel"][0]
            piece["pos"][1] += piece["vel"][1]
            draw_x = piece["pos"][0] + camera.x
            draw_y = piece["pos"][1]
            self.screen.blit(piece["image"], (draw_x, draw_y))
        if self.lifetime <= 0:
            self.done = True

