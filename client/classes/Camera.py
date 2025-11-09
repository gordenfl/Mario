from classes.Maths import Vec2D


class Camera:
    def __init__(self, pos, entity):
        self.pos = Vec2D(pos.x, pos.y)
        self.entity = entity
        self.x = self.pos.x * 32
        self.y = self.pos.y * 32

    def _calculate_offset(self):
        xPosFloat = self.entity.getPosIndexAsFloat().x
        if xPosFloat <= 10:
            return 0
        if xPosFloat >= 50:
            return -40
        return -xPosFloat + 10

    def snap_to_entity(self):
        self.pos.x = self._calculate_offset()
        self.x = self.pos.x * 32
        self.y = self.pos.y * 32

    def move(self):
        self.pos.x = self._calculate_offset()
        self.x = self.pos.x * 32
        self.y = self.pos.y * 32
