from classes.Maths import Vec2D
from viewport import compute_virtual_framebuffer


class Camera:
    def __init__(self, pos, entity):
        self.pos = Vec2D(pos.x, pos.y)
        self.entity = entity
        self.x = self.pos.x * 32
        self.y = self.pos.y * 32

    def _calculate_offset(self):
        # Use horizontal center so the viewport centers on Mario (sprite anchor is top-left in world).
        xPosFloat = self.entity.rect.centerx / 32.0
        tile_size = 32.0
        screen = getattr(self.entity, "screen", None)
        if screen is not None:
            sw, sh = screen.get_size()
            screen_width, _ = compute_virtual_framebuffer(sw, sh)
        else:
            screen_width = 852.0
        visible_tiles = max(1.0, screen_width / tile_size)
        # Lock horizontal framing: entity center stays at viewport center in X.
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
