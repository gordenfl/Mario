import pygame


class RemotePlayer:
    """Simplified representation of another player in the room."""

    def __init__(self, username: str, color=(0, 120, 255)):
        self.username = username
        self.color = color
        self.rect = pygame.Rect(0, 0, 32, 48)
        self.visible = False
        self.state = {
            "position": [0, 0],
            "velocity": [0, 0],
            "hp": 30,
            "power": 0,
            "score": 0,
        }

    def update_from_state(self, state: dict):
        position = state.get("position", self.state["position"])
        self.state.update(state)
        self.rect.x = int(position[0])
        self.rect.y = int(position[1])
        self.visible = True

    def draw(self, surface: pygame.Surface, camera_offset_x: float, camera_offset_y: float):
        if not self.visible:
            return
        draw_rect = self.rect.copy()
        draw_rect.x -= int(camera_offset_x)
        draw_rect.y -= int(camera_offset_y)
        pygame.draw.rect(surface, self.color, draw_rect)
        font = pygame.font.Font(None, 18)
        label = font.render(self.username, True, (255, 255, 255))
        surface.blit(label, (draw_rect.x, draw_rect.y - 16))
