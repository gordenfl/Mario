class Collider:
    def __init__(self, entity, level):
        self.entity = entity
        self.level = level.level
        self.levelObj = level
        self.result = []

    def checkX(self):
        if self.leftLevelBorderReached() or self.rightLevelBorderReached():
            return
        try:
            rows = [
                self.level[self.entity.getPosIndex().y],
                self.level[self.entity.getPosIndex().y + 1],
                self.level[self.entity.getPosIndex().y + 2],
            ]
        except Exception:
            return
        base_index = self.entity.getPosIndex()
        for row in rows:
            tiles = row[base_index.x : base_index.x + 2]
            for tile in tiles:
                if tile is not None and tile.rect is not None:
                    if self.entity.rect.colliderect(tile.rect):
                        if self.entity.vel.x > 0:
                            self.entity.rect.right = tile.rect.left
                            self.entity.vel.x = 0
                        if self.entity.vel.x < 0:
                            self.entity.rect.left = tile.rect.right
                            self.entity.vel.x = 0

    def checkY(self):
        self.entity.onGround = False
        base_index = self.entity.getPosIndex()

        try:
            rows = [
                (base_index.y, self.level[base_index.y]),
                (base_index.y + 1, self.level[base_index.y + 1]),
                (base_index.y + 2, self.level[base_index.y + 2]),
            ]
        except Exception:
            try:
                self.entity.gameOver()
            except Exception:
                self.entity.alive = None
            return
        base_x = base_index.x
        for row_y, row in rows:
            if row is None:
                continue
            for x_offset in range(0, 2):
                tile_x = base_x + x_offset
                if tile_x < 0 or tile_x >= len(row):
                    continue
                tile = row[tile_x]
                if tile is None or tile.rect is None:
                    continue
                if not self.entity.rect.colliderect(tile.rect):
                    continue
                if self.entity.vel.y > 0:
                    self.entity.onGround = True
                    self.entity.rect.bottom = tile.rect.top
                    self.entity.vel.y = 0
                    if self.entity.traits is not None:
                        if "JumpTrait" in self.entity.traits:
                            self.entity.traits["JumpTrait"].reset()
                        if "bounceTrait" in self.entity.traits:
                            self.entity.traits["bounceTrait"].reset()
                elif self.entity.vel.y < 0:
                    self.levelObj.handle_tile_hit_from_below(tile_x, row_y, self.entity)
                    self.entity.rect.top = tile.rect.bottom
                    self.entity.vel.y = 0

    def rightLevelBorderReached(self):
        if self.entity.getPosIndexAsFloat().x > self.levelObj.levelLength - 1:
            self.entity.rect.x = (self.levelObj.levelLength - 1) * 32
            self.entity.vel.x = 0
            return True

    def leftLevelBorderReached(self):
        if self.entity.rect.x < 0:
            self.entity.rect.x = 0
            self.entity.vel.x = 0
            return True
