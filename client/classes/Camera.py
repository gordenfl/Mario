from classes.Maths import Vec2D


class Camera:
    def __init__(self, pos, entity):
        self.pos = Vec2D(pos.x, pos.y)
        self.entity = entity
        self.x = self.pos.x * 32
        self.y = self.pos.y * 32

    def _calculate_offset(self):
        xPosFloat = self.entity.getPosIndexAsFloat().x
        tile_size = 32.0
        screen_width = float(getattr(getattr(self.entity, "screen", None), "get_width", lambda: 640)())
        visible_tiles = max(1.0, screen_width / tile_size)
        # Keep Mario slightly left-of-center (similar feel to previous fixed value 10 on 20-tile viewport).
        anchor_tiles = visible_tiles * 0.5

        level_length = float(getattr(getattr(self.entity, "levelObj", None), "levelLength", 0) or 0)
        max_scroll_tiles = max(level_length - visible_tiles, 0.0)

        if xPosFloat <= anchor_tiles:
            return 0.0
        if xPosFloat >= anchor_tiles + max_scroll_tiles:
            return -max_scroll_tiles
        return -xPosFloat + anchor_tiles

    def snap_to_entity(self):
        self.pos.x = self._calculate_offset()
        self.x = self.pos.x * 32
        self.y = self.pos.y * 32

    def move(self):
        self.pos.x = self._calculate_offset()
        self.x = self.pos.x * 32
        self.y = self.pos.y * 32
