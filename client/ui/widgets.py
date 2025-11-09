import os
from functools import lru_cache

import pygame


def _font_path():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "..", "fonts", "Regular.ttf")
    return os.path.normpath(path)


@lru_cache(maxsize=32)
def get_font(size: int):
    path = _font_path()
    if os.path.exists(path):
        try:
            return pygame.font.Font(path, size)
        except Exception:
            pass
    return pygame.font.Font(None, size)


class Button:
    def __init__(self, rect, text, callback, font=None, base_color=(66, 135, 245), hover_color=(45, 110, 210), text_color=(255, 255, 255)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.callback = callback
        self.base_color = base_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.font = font or get_font(28)
        self.hovered = False
        self.disabled = False

    def handle_event(self, event):
        if self.disabled:
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.callback()

    def update(self, mouse_pos):
        if self.disabled:
            self.hovered = False
        else:
            self.hovered = self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        color = self.hover_color if self.hovered and not self.disabled else self.base_color
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        pygame.draw.rect(surface, (20, 20, 20), self.rect, width=2, border_radius=6)
        label = self.font.render(self.text, True, self.text_color)
        label_rect = label.get_rect(center=self.rect.center)
        surface.blit(label, label_rect)


class Label:
    def __init__(self, rect, text, font=None, color=(255, 255, 255)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font or get_font(24)
        self.color = color

    def draw(self, surface):
        label = self.font.render(self.text, True, self.color)
        surface.blit(label, self.rect)


class TextInput:
    def __init__(self, rect, font=None, placeholder="", max_length=20, text_color=(255, 255, 255), bg_color=(30, 30, 30), border_color=(80, 80, 80)):
        self.rect = pygame.Rect(rect)
        self.font = font or get_font(28)
        self.placeholder = placeholder
        self.text = ""
        self.max_length = max_length
        self.text_color = text_color
        self.bg_color = bg_color
        self.border_color = border_color
        self.active = False
        self.cursor_visible = True
        self._cursor_timer = 0
        self._cursor_interval = 400  # milliseconds

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        if not self.active:
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                return
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                if len(self.text) < self.max_length and event.unicode and event.unicode.isprintable():
                    self.text += event.unicode

    def update(self, dt_ms):
        self._cursor_timer += dt_ms
        if self._cursor_timer >= self._cursor_interval:
            self.cursor_visible = not self.cursor_visible
            self._cursor_timer = 0

    def draw(self, surface):
        pygame.draw.rect(surface, self.bg_color, self.rect, border_radius=6)
        pygame.draw.rect(surface, self.border_color if not self.active else (120, 180, 250), self.rect, width=2, border_radius=6)
        display_text = self.text if self.text else self.placeholder
        color = self.text_color if self.text else (150, 150, 150)
        text_surf = self.font.render(display_text, True, color)
        surface.blit(text_surf, (self.rect.x + 10, self.rect.y + (self.rect.height - text_surf.get_height()) // 2))
        if self.active and self.cursor_visible:
            cursor_x = self.rect.x + 10 + text_surf.get_width()
            cursor_y = self.rect.y + 10
            cursor_height = self.rect.height - 20
            pygame.draw.rect(surface, self.text_color, (cursor_x, cursor_y, 2, cursor_height))

    def get_value(self):
        return self.text.strip()