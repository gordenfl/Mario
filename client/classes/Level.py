import json
import pygame

from classes.Sprites import Sprites
from classes.Tile import Tile
from entities.Coin import Coin
from entities.CoinBrick import CoinBrick
from entities.Goomba import Goomba
from entities.Mushroom import RedMushroom
from entities.Koopa import Koopa
from entities.CoinBox import CoinBox
from entities.RandomBox import RandomBox
from entities.brick_debris import BrickDebrisEffect


class Level:
    def __init__(self, screen, sound, dashboard):
        self.sprites = Sprites()
        self.dashboard = dashboard
        self.sound = sound
        self.screen = screen
        self.level = None
        self.levelLength = 0
        self.entityList = []
        self.effects = []
        self.broken_tiles = []

    def loadLevel(self, levelname):
        with open("./levels/{}.json".format(levelname)) as jsonData:
            data = json.load(jsonData)
            self.loadLayers(data)
            self.loadObjects(data)
            self.loadEntities(data)
            self.levelLength = data["length"]

    def is_solid_at_pixel(self, x: float, y: float) -> bool:
        if not self.level:
            return False
        tile_x = int(x // 32)
        tile_y = int(y // 32)
        if tile_y < 0 or tile_y >= len(self.level):
            return False
        row = self.level[tile_y]
        if row is None:
            return False
        if tile_x < 0 or tile_x >= len(row):
            return False
        tile = row[tile_x]
        return tile is not None and tile.rect is not None

    def loadEntities(self, data):
        # 当前版本暂时不加载关卡中的敌人或道具
        self.entityList = []

    def loadLayers(self, data):
        layers = []
        for x in range(*data["level"]["layers"]["sky"]["x"]):
            layers.append(
                (
                        [
                            Tile(self.sprites.spriteCollection.get("sky"), None, "sky")
                            for y in range(*data["level"]["layers"]["sky"]["y"])
                        ]
                        + [
                            Tile(
                                self.sprites.spriteCollection.get("ground"),
                                pygame.Rect(x * 32, (y - 1) * 32, 32, 32),
                                "ground",
                            )
                            for y in range(*data["level"]["layers"]["ground"]["y"])
                        ]
                )
            )
        self.level = list(map(list, zip(*layers)))

    def loadObjects(self, data):
        def in_bounds(tile_x, tile_y):
            return (
                self.level
                and 0 <= tile_y < len(self.level)
                and self.level[tile_y] is not None
                and 0 <= tile_x < len(self.level[tile_y])
            )

        for x, y in data["level"]["objects"].get("ground", []):
            if in_bounds(x, y):
                self.level[y][x] = Tile(
                    self.sprites.spriteCollection.get("ground"),
                    pygame.Rect(x * 32, y * 32, 32, 32),
                    "ground",
                )
        for x, y in data["level"]["objects"].get("bricks", []):
            if in_bounds(x, y):
                self.level[y][x] = Tile(
                    self.sprites.spriteCollection.get("bricks"),
                    pygame.Rect(x * 32, y * 32, 32, 32),
                    "bricks",
                )
        for x, y, z in data["level"]["objects"].get("pipe", []):
            self.addPipeSprite(x, y, z)
        for x, y in data["level"]["objects"].get("bush", []):
            self.addBushSprite(x, y)
        for x, y in data["level"]["objects"].get("cloud", []):
            self.addCloudSprite(x, y)
        for x, y in data["level"]["objects"].get("sky", []):
            if not in_bounds(x, y):
                continue
            current = self.level[y][x]
            if current and getattr(current, "tile_type", None) in {"pipe", "block", "coinBrick"}:
                continue
            self.level[y][x] = Tile(self.sprites.spriteCollection.get("sky"), None, "sky")

    def get_tile(self, tile_x: int, tile_y: int):
        if not self.level:
            return None
        if tile_y < 0 or tile_y >= len(self.level):
            return None
        row = self.level[tile_y]
        if row is None or tile_x < 0 or tile_x >= len(row):
            return None
        return row[tile_x]

    def break_tile(self, tile_x: int, tile_y: int, *, play_sound: bool = True, record_event: bool = True) -> bool:
        tile = self.get_tile(tile_x, tile_y)
        if not tile or getattr(tile, "tile_type", None) != "bricks":
            return False
        if play_sound:
            try:
                self.sound.play_sfx(self.sound.brick_bump)
            except AttributeError:
                pass
        self.level[tile_y][tile_x] = Tile(self.sprites.spriteCollection.get("sky"), None, "sky")
        self.spawn_brick_debris(tile_x, tile_y)
        if record_event:
            self.broken_tiles.append((tile_x, tile_y))
        return True

    def handle_tile_hit_from_below(self, tile_x: int, tile_y: int, entity) -> bool:
        tile = self.get_tile(tile_x, tile_y)
        if not tile:
            return False
        tile_type = getattr(tile, "tile_type", None)
        if tile_type == "bricks":
            power = getattr(entity, "powerUpState", 0)
            if power >= 1:
                return self.break_tile(tile_x, tile_y, play_sound=True, record_event=True)
            try:
                self.sound.play_sfx(self.sound.brick_bump)
            except AttributeError:
                pass
        return False

    def consume_broken_tiles(self):
        if not self.broken_tiles:
            return []
        tiles = self.broken_tiles[:]
        self.broken_tiles.clear()
        return tiles

    def spawn_brick_debris(self, tile_x: int, tile_y: int):
        try:
            effect = BrickDebrisEffect(self.sprites.spriteCollection, self.screen, tile_x, tile_y)
        except Exception:
            effect = None
        if effect:
            self.effects.append(effect)

    def updateEffects(self, camera):
        for effect in list(self.effects):
            effect.update(camera)
            if effect.done:
                self.effects.remove(effect)

    def updateEntities(self, cam):
        for entity in self.entityList:
            entity.update(cam)
            if entity.alive is None:
                self.entityList.remove(entity)

    def drawLevel(self, camera):
        if not self.level:
            return
        # Always paint a full-screen sky background so areas beyond map bounds
        # do not appear as black bars on wider aspect ratios.
        sky_sprite = self.sprites.spriteCollection.get("sky")
        if sky_sprite and sky_sprite.image:
            sky_img = sky_sprite.image
            tile_w, tile_h = sky_img.get_width(), sky_img.get_height()
            screen_w, screen_h = self.screen.get_width(), self.screen.get_height()
            # Keep background anchored to world/camera space.
            # This avoids the illusion that only entities moved while background stayed fixed.
            x_offset = int(camera.x) % tile_w
            for sy in range(0, screen_h + tile_h, tile_h):
                for sx in range(-x_offset, screen_w + tile_w, tile_w):
                    self.screen.blit(sky_img, (sx, sy))
        else:
            self.screen.fill((107, 181, 255))

        max_rows = len(self.level)
        visible_rows = max(1, self.screen.get_height() // 32)
        visible_cols = max(1, self.screen.get_width() // 32 + 2)
        for y in range(0, min(visible_rows, max_rows)):
            row = self.level[y]
            if row is None:
                continue
            max_cols = len(row)
            start_x = 0 - int(camera.pos.x + 1)
            end_x = visible_cols - int(camera.pos.x - 1)
            for x in range(start_x, end_x):
                if x < 0 or x >= max_cols:
                    continue
                tile = row[x]
                if tile is None or tile.sprite is None:
                    continue
                if tile.sprite.redrawBackground:
                    self.screen.blit(
                        self.sprites.spriteCollection.get("sky").image,
                        ((x + camera.pos.x) * 32, y * 32),
                    )
                tile.sprite.drawSprite(
                    x + camera.pos.x, y, self.screen
                )
        self.updateEntities(camera)
        self.updateEffects(camera)

    def addCloudSprite(self, x, y):
        try:
            for yOff in range(0, 2):
                for xOff in range(0, 3):
                    self.level[y + yOff][x + xOff] = Tile(
                        self.sprites.spriteCollection.get("cloud{}_{}".format(yOff + 1, xOff + 1)),
                        None,
                        "cloud",
                    )
        except IndexError:
            return

    def addPipeSprite(self, x, y, length=2):
        try:
            # add pipe head
            self.level[y][x] = Tile(
                self.sprites.spriteCollection.get("pipeL"),
                pygame.Rect(x * 32, y * 32, 32, 32),
                "pipe",
            )
            self.level[y][x + 1] = Tile(
                self.sprites.spriteCollection.get("pipeR"),
                pygame.Rect((x + 1) * 32, y * 32, 32, 32),
                "pipe",
            )
            # add pipe body
            for i in range(1, length + 20):
                self.level[y + i][x] = Tile(
                    self.sprites.spriteCollection.get("pipe2L"),
                    pygame.Rect(x * 32, (y + i) * 32, 32, 32),
                    "pipe",
                )
                self.level[y + i][x + 1] = Tile(
                    self.sprites.spriteCollection.get("pipe2R"),
                    pygame.Rect((x + 1) * 32, (y + i) * 32, 32, 32),
                    "pipe",
                )
        except IndexError:
            return

    def addBushSprite(self, x, y):
        try:
            self.level[y][x] = Tile(self.sprites.spriteCollection.get("bush_1"), None, "bush")
            self.level[y][x + 1] = Tile(
                self.sprites.spriteCollection.get("bush_2"), None, "bush"
            )
            self.level[y][x + 2] = Tile(
                self.sprites.spriteCollection.get("bush_3"), None, "bush"
            )
        except IndexError:
            return

    def addCoinBox(self, x, y):
        self.level[y][x] = Tile(None, pygame.Rect(x * 32, y * 32 - 1, 32, 32), "block")
        self.entityList.append(
            CoinBox(
                self.screen,
                self.sprites.spriteCollection,
                x,
                y,
                self.sound,
                self.dashboard,
            )
        )

    def addRandomBox(self, x, y, item):
        self.level[y][x] = Tile(None, pygame.Rect(x * 32, y * 32 - 1, 32, 32), "block")
        self.entityList.append(
            RandomBox(
                self.screen,
                self.sprites.spriteCollection,
                x,
                y,
                item,
                self.sound,
                self.dashboard,
                self
            )
        )

    def addCoin(self, x, y):
        self.entityList.append(Coin(self.screen, self.sprites.spriteCollection, x, y))

    def addCoinBrick(self, x, y):
        self.level[y][x] = Tile(None, pygame.Rect(x * 32, y * 32 - 1, 32, 32), "coinBrick")
        self.entityList.append(
            CoinBrick(
                self.screen,
                self.sprites.spriteCollection,
                x,
                y,
                self.sound,
                self.dashboard
            )
        )

    def addGoomba(self, x, y):
        self.entityList.append(
            Goomba(self.screen, self.sprites.spriteCollection, x, y, self, self.sound)
        )

    def addKoopa(self, x, y):
        self.entityList.append(
            Koopa(self.screen, self.sprites.spriteCollection, x, y, self, self.sound)
        )

    def addRedMushroom(self, x, y):
        self.entityList.append(
            RedMushroom(self.screen, self.sprites.spriteCollection, x, y, self, self.sound)
        )
