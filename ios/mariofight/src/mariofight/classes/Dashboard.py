import pygame

from classes.Font import Font


class Dashboard(Font):
    def __init__(self, filePath, size, screen):
        Font.__init__(self, filePath, size)
        self.state = "menu"
        self.screen = screen
        self.levelName = ""
        self.points = 0
        self.coins = 0
        self.ticks = 0
        self.time = 0
        self.player_hp = None
        self.player_max_hp = None

    def update(self):
        self.drawText("MARIO", 50, 20, 15)
        self.drawText(self.pointString(), 50, 37, 15)

        self.drawText("@x{}".format(self.coinString()), 225, 37, 15)

        self.drawText("WORLD", 380, 20, 15)
        self.drawText(str(self.levelName), 395, 37, 15)

        self.drawText("TIME", 520, 20, 15)
        if self.state != "menu":
            self.drawText(self.timeString(), 535, 37, 15)

        if self.player_hp is not None and self.player_max_hp:
            self.draw_health_bar(48, 62, 200, 14)

        # update Time
        self.ticks += 1
        if self.ticks == 60:
            self.ticks = 0
            self.time += 1

    def set_player_health(self, hp, max_hp=None):
        if max_hp is not None:
            self.player_max_hp = max_hp
        if self.player_max_hp is None and max_hp is None:
            self.player_max_hp = hp
        self.player_hp = max(0, hp)

    def draw_health_bar(self, x, y, width, height):
        pygame.draw.rect(self.screen, (40, 40, 40), pygame.Rect(x, y, width, height), border_radius=4)
        inner_rect = pygame.Rect(x + 2, y + 2, width - 4, height - 4)
        pygame.draw.rect(self.screen, (10, 10, 10), inner_rect, border_radius=4)
        if self.player_max_hp and self.player_max_hp > 0:
            ratio = min(1.0, max(0.0, self.player_hp / float(self.player_max_hp)))
            fill_width = int((width - 4) * ratio)
            if fill_width > 0:
                fill_rect = pygame.Rect(x + 2, y + 2, fill_width, height - 4)
                pygame.draw.rect(self.screen, (220, 50, 40), fill_rect, border_radius=3)
        self.drawText("HP", x, y - 18, 14)
        if self.player_max_hp:
            hp_text = f"{int(self.player_hp):02d}/{int(self.player_max_hp):02d}"
            self.drawText(hp_text, x + width + 12, y - 2, 12)

    def drawText(self, text, x, y, size):
        for char in text:
            charSprite = pygame.transform.scale(self.charSprites[char], (size, size))
            self.screen.blit(charSprite, (x, y))
            if char == " ":
                x += size//2
            else:
                x += size

    def coinString(self):
        return "{:02d}".format(self.coins)

    def pointString(self):
        return "{:06d}".format(self.points)

    def timeString(self):
        return "{:03d}".format(self.time)
