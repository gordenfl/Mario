from __future__ import annotations

import random
from typing import Callable, Dict, Optional, Tuple

from .level import TILE, Level
from .rect import Rect

# Match pygame `client/entities/sky_drop.py`.
SKY_DROP_SIZE = 28
SKY_COIN_SIZE = 24
SKY_MUSHROOM_SIZE = 28
GRAVITY_FALL = 0.55
GRAVITY_WALK = 0.6
MUSHROOM_SPEED = 1.2
LANDING_COOLDOWN_FRAMES = 2


class _SkyDropBase:
    __slots__ = ("drop_id", "drop_type", "rect", "alive")

    def __init__(self, drop_type: str) -> None:
        self.drop_id: Optional[str] = None
        self.drop_type = drop_type
        self.rect = Rect(0.0, 0.0, float(SKY_DROP_SIZE), float(SKY_DROP_SIZE))
        self.alive = True


class SkyDropEntity(_SkyDropBase):
    """Falls from the sky; spawns a landed coin or mushroom on solid ground."""

    __slots__ = (
        "gravity",
        "vel_y",
        "pos_y",
        "spawned_entity",
        "initial_direction",
        "direction_callback",
    )

    def __init__(self, drop_type: str, spawn_x: float) -> None:
        super().__init__(drop_type)
        self.gravity = GRAVITY_FALL
        self.vel_y = 0.0
        self.rect.centerx = spawn_x
        self.rect.top = -float(SKY_DROP_SIZE)
        self.pos_y = float(self.rect.y)
        self.spawned_entity: Optional[_LandedDropBase] = None
        self.initial_direction: Optional[int] = None
        self.direction_callback: Optional[Callable[[str, Optional[str]], None]] = None

    def update(self, level: Level) -> Optional[_LandedDropBase]:
        if not self.alive:
            return self.spawned_entity
        # Match pygame SkyDrop: vel.y += gravity; pos_y += vel.y
        self.vel_y += self.gravity
        self.pos_y += self.vel_y
        self.rect.y = int(self.pos_y)
        level_h = len(level.tiles) * TILE if level.tiles else 480
        if self.rect.top > level_h + 64:
            self.alive = False
            return None
        if level.is_solid_at_pixel(self.rect.centerx, float(self.rect.bottom + 1)):
            landing_y = int((self.rect.bottom + 1) // TILE) * TILE
            spawn_x = self.rect.centerx
            if self.drop_type == "coin":
                landed = SkyCoinEntity(spawn_x, landing_y)
            else:
                landed = SkyMushroomEntity(
                    spawn_x,
                    landing_y,
                    initial_direction=self.initial_direction,
                )
                landed.direction_callback = self.direction_callback
                if self.initial_direction in (-1, 1):
                    landed.apply_direction(self.initial_direction)
            landed.drop_id = self.drop_id
            self.spawned_entity = landed
            self.alive = False
            return landed
        return None


class _LandedDropBase(_SkyDropBase):
    __slots__ = ()


class SkyCoinEntity(_LandedDropBase):
    __slots__ = ("anim_tick",)

    def __init__(self, spawn_x: float, landing_y: int) -> None:
        super().__init__("coin")
        self.rect = Rect(0.0, 0.0, float(SKY_COIN_SIZE), float(SKY_COIN_SIZE))
        self.rect.centerx = spawn_x
        self.rect.bottom = float(landing_y)
        self.anim_tick = 0

    def update(self, level: Level, tick_i: int) -> bool:
        if not self.alive:
            return False
        self.anim_tick = tick_i
        level_h = len(level.tiles) * TILE if level.tiles else 480
        if self.rect.top > level_h + 32:
            self.alive = False
            return False
        return True


class SkyMushroomEntity(_LandedDropBase):
    __slots__ = (
        "gravity",
        "pos_x",
        "pos_y",
        "direction",
        "vel_y",
        "landing_cooldown",
        "was_on_ground",
        "just_landed",
        "waiting_direction",
        "pending_collision",
        "direction_callback",
    )

    def __init__(
        self,
        spawn_x: float,
        landing_y: int,
        *,
        initial_direction: Optional[int] = None,
    ) -> None:
        super().__init__("mushroom")
        self.gravity = GRAVITY_WALK
        self.rect = Rect(0.0, 0.0, float(SKY_MUSHROOM_SIZE), float(SKY_MUSHROOM_SIZE))
        self.rect.centerx = spawn_x
        self.rect.bottom = float(landing_y)
        self.pos_x = float(self.rect.x)
        self.pos_y = float(self.rect.y)
        if initial_direction in (-1, 1):
            direction = int(initial_direction)
        else:
            direction = random.choice([-1, 1])
        self.direction = direction
        self.vel_y = 0.0
        self.landing_cooldown = 0
        self.was_on_ground = False
        self.just_landed = False
        self.waiting_direction = False
        self.pending_collision: Optional[str] = None
        self.direction_callback: Optional[Callable[[str, Optional[str]], None]] = None

    def update(self, level: Level, world_width_px: float) -> bool:
        if not self.alive:
            return False
        self.vel_y += self.gravity
        self.pos_y += self.vel_y
        self.rect.y = int(self.pos_y)

        below = float(self.rect.bottom + 1)
        on_ground = level.is_solid_at_pixel(self.rect.centerx, below)
        if on_ground:
            landing_y = int(below // TILE) * TILE
            self.rect.bottom = float(landing_y)
            self.pos_y = float(self.rect.y)
            self.vel_y = 0.0
            if not self.was_on_ground:
                self.landing_cooldown = LANDING_COOLDOWN_FRAMES
            self.was_on_ground = True
            self.just_landed = True
        else:
            self.just_landed = False
            if self.waiting_direction:
                self.waiting_direction = False
                self.pending_collision = None
            self.was_on_ground = False

        prev_x = self.pos_x
        if self.direction != 0:
            self.pos_x += MUSHROOM_SPEED * float(self.direction)
        self.rect.x = int(self.pos_x)

        if on_ground:
            foot = float(self.rect.bottom - 4)
            left_block = level.is_solid_at_pixel(float(self.rect.left - 1), foot)
            right_block = level.is_solid_at_pixel(float(self.rect.right + 1), foot)
            if self.landing_cooldown > 0:
                self.landing_cooldown -= 1
            elif left_block or right_block:
                self.pos_x = prev_x
                self.rect.x = int(self.pos_x)
                if left_block:
                    self.direction = 1
                else:
                    self.direction = -1
                self.landing_cooldown = max(self.landing_cooldown, 1)
                side = "left" if left_block else "right"
                if self.direction_callback and self.drop_id:
                    if self.pending_collision != side:
                        self.pending_collision = side
                        self.direction_callback(self.drop_id, side)
                self.just_landed = False
        elif self.just_landed:
            self.just_landed = False

        self._clamp_x(world_width_px)
        level_h = len(level.tiles) * TILE if level.tiles else 480
        if self.rect.top > level_h + 64:
            self.alive = False
            return False
        return True

    def apply_direction(self, direction: float) -> None:
        if direction not in (-1, 1, 0):
            return
        if direction == 0:
            self.direction = 0
            self.waiting_direction = True
        else:
            self.direction = 1 if direction > 0 else -1
            self.waiting_direction = False
            self.pending_collision = None
            self.landing_cooldown = max(self.landing_cooldown, 1)

    def clear_collision_request(self) -> None:
        self.pending_collision = None
        self.waiting_direction = False
        if self.direction_callback and self.drop_id:
            self.direction_callback(self.drop_id, None)

    def _clamp_x(self, world_width_px: float) -> None:
        if self.rect.left < 0.0:
            self.rect.left = 0.0
            self.pos_x = float(self.rect.x)
        elif self.rect.right > world_width_px:
            self.rect.right = float(world_width_px)
            self.pos_x = float(self.rect.x)


class DropSystem:
    """Server-driven sky drops (coins / mushrooms), matching pygame `client/main.py`."""

    def __init__(self) -> None:
        self.active: Dict[str, _SkyDropBase] = {}
        self._reported_drop_ids: set[str] = set()
        self._pending_collision_requests: set[str] = set()
        self._collision_callback: Optional[Callable[[str, str], None]] = None

    def clear(self) -> None:
        self.active.clear()
        self._reported_drop_ids.clear()
        self._pending_collision_requests.clear()

    def set_collision_callback(self, cb: Optional[Callable[[str, str], None]]) -> None:
        self._collision_callback = cb

    def spawn_from_event(self, event: dict, level: Level) -> None:
        drop_id = event.get("drop_id")
        if drop_id and drop_id in self.active:
            return
        drop_type = event.get("drop_type", "coin")
        spawn_x = event.get("x", 48)
        direction = event.get("direction")
        try:
            spawn_x = float(spawn_x)
        except (TypeError, ValueError):
            return
        level_w = max(96.0, float(level.length_tiles * TILE - 48))
        spawn_x = max(48.0, min(spawn_x, level_w))
        entity: _SkyDropBase = SkyDropEntity(str(drop_type), spawn_x)
        if drop_type == "mushroom" and direction in (-1, 1):
            assert isinstance(entity, SkyDropEntity)
            entity.initial_direction = int(direction)
        if drop_id:
            entity.drop_id = str(drop_id)
            if isinstance(entity, SkyDropEntity):
                entity.direction_callback = self._handle_mushroom_collision_request
            self.active[str(drop_id)] = entity

    def remove_by_id(self, drop_id: str) -> None:
        entity = self.active.pop(drop_id, None)
        if entity is None:
            return
        replacement = getattr(entity, "spawned_entity", None)
        if replacement is not None:
            replacement.alive = False
        entity.alive = False
        self._pending_collision_requests.discard(drop_id)

    def set_direction(self, drop_id: str, direction: float) -> None:
        entity = self.active.get(drop_id)
        if entity is None:
            return
        if isinstance(entity, SkyDropEntity):
            if direction in (-1, 1):
                entity.initial_direction = int(direction)
            spawned = entity.spawned_entity
            if spawned is None:
                return
            entity = spawned
            self.active[drop_id] = spawned
        if isinstance(entity, SkyMushroomEntity):
            entity.apply_direction(direction)
            entity.clear_collision_request()
        self._pending_collision_requests.discard(drop_id)

    def on_remote_collected(self, drop_id: str) -> None:
        self._reported_drop_ids.add(drop_id)
        self.remove_by_id(drop_id)

    def step(
        self,
        level: Level,
        mario_rect: Rect,
        tick_i: int,
        *,
        net: Optional[object] = None,
    ) -> Tuple[int, int]:
        """Advance drops; return (coins_collected, mushrooms_collected) this tick."""
        world_w = max(1.0, float(level.length_tiles * TILE))
        coins = 0
        mushrooms = 0

        for drop_id, entity in list(self.active.items()):
            if isinstance(entity, SkyDropEntity):
                landed = entity.update(level)
                if landed is not None:
                    self.active[drop_id] = landed
                    entity = landed
                elif not entity.alive:
                    self._despawn_drop(drop_id, net)
                    continue
                else:
                    continue

            if isinstance(entity, SkyCoinEntity):
                if not entity.update(level, tick_i):
                    self._despawn_drop(drop_id, net)
                    continue
            elif isinstance(entity, SkyMushroomEntity):
                if not entity.update(level, world_w):
                    self._despawn_drop(drop_id, net)
                    continue
                if (
                    entity.pending_collision
                    and drop_id not in self._pending_collision_requests
                ):
                    self._handle_mushroom_collision_request(drop_id, entity.pending_collision)

            if entity.rect.colliderect(mario_rect):
                if entity.drop_type == "mushroom":
                    mushrooms += 1
                else:
                    coins += 1
                self._despawn_drop(drop_id, net, collected=True)

        return coins, mushrooms

    def iter_visible(self):
        for entity in self.active.values():
            yield entity
            spawned = getattr(entity, "spawned_entity", None)
            if spawned is not None and spawned.alive:
                yield spawned

    def _handle_mushroom_collision_request(self, drop_id: str, side: Optional[str]) -> None:
        if side is None:
            self._pending_collision_requests.discard(drop_id)
            return
        if drop_id in self._pending_collision_requests:
            return
        self._pending_collision_requests.add(drop_id)
        if self._collision_callback:
            self._collision_callback(drop_id, side)

    def _despawn_drop(
        self,
        drop_id: str,
        net: Optional[object],
        *,
        collected: bool = False,
    ) -> None:
        self.remove_by_id(drop_id)
        self._pending_collision_requests.discard(drop_id)
        if drop_id in self._reported_drop_ids:
            return
        if net is not None and hasattr(net, "send_drop_collected"):
            net.send_drop_collected(drop_id)
        self._reported_drop_ids.add(drop_id)
