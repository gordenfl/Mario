from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple


Point = Tuple[float, float]


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def left(self) -> float:
        return self.x

    @left.setter
    def left(self, v: float) -> None:
        self.x = v

    @property
    def right(self) -> float:
        return self.x + self.w

    @right.setter
    def right(self, v: float) -> None:
        self.x = v - self.w

    @property
    def top(self) -> float:
        return self.y

    @top.setter
    def top(self, v: float) -> None:
        self.y = v

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @bottom.setter
    def bottom(self, v: float) -> None:
        self.y = v - self.h

    @property
    def centerx(self) -> float:
        return self.x + self.w * 0.5

    @centerx.setter
    def centerx(self, v: float) -> None:
        self.x = v - self.w * 0.5

    @property
    def centery(self) -> float:
        return self.y + self.h * 0.5

    @centery.setter
    def centery(self, v: float) -> None:
        self.y = v - self.h * 0.5

    @property
    def center(self) -> Point:
        return (self.centerx, self.centery)

    @property
    def midbottom(self) -> Point:
        return (self.centerx, self.bottom)

    @midbottom.setter
    def midbottom(self, p: Point) -> None:
        cx, by = p
        self.x = cx - self.w * 0.5
        self.y = by - self.h

    @property
    def midtop(self) -> Point:
        return (self.centerx, self.top)

    @property
    def bottomleft(self) -> Point:
        return (self.left, self.bottom)

    @property
    def bottomright(self) -> Point:
        return (self.right, self.bottom)

    def colliderect(self, other: "Rect") -> bool:
        return not (
            self.right <= other.left
            or self.left >= other.right
            or self.bottom <= other.top
            or self.top >= other.bottom
        )

    def collidepoint(self, p: Point) -> bool:
        px, py = p
        return self.left <= px <= self.right and self.top <= py <= self.bottom

    def move_ip(self, dx: float, dy: float) -> None:
        self.x += dx
        self.y += dy

    def inflate(self, dw: float, dh: float) -> "Rect":
        return Rect(self.x - dw * 0.5, self.y - dh * 0.5, self.w + dw, self.h + dh)

    def as_int(self) -> Tuple[int, int, int, int]:
        return (int(self.x), int(self.y), int(self.w), int(self.h))


def rects_intersect_any(r: Rect, rects: Iterable[Rect]) -> bool:
    for other in rects:
        if r.colliderect(other):
            return True
    return False

