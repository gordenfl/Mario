import random
import string
import sys
import time
import uuid

import pygame

from classes.Dashboard import Dashboard
from classes.Level import Level
from classes.Menu import Menu
from classes.Sound import Sound
from classes.Sprites import Sprites
from entities.Mario import Mario
from entities.fireball import Fireball
from entities.sky_drop import SkyDrop, SkyMushroom
from typing import Optional
from entities.remote_player import RemotePlayer
from network.network_client import NetworkClient, NetworkError
from network.protocol import (
    MSG_PLAYER_STATE,
    MSG_PROJECTILE_STATE,
    MSG_ACTION,
    PROJECTILE_FLAG_SPAWN,
    PROJECTILE_FLAG_UPDATE,
    PROJECTILE_FLAG_DESPAWN,
    ACTION_FIRE,
)
from ui.sky_background import (
    LoginDriftingClouds,
    draw_login_sky,
    draw_ground_tiles,
    draw_sky_ground_background,
    draw_sky_tiles,
    ground_band_rect,
)
from ui.login_frame_mushrooms import LoginFrameMushrooms
from ui.login_wall_mario import LoginWallMario
from ui.wall_title import (
    build_title_letter_colors,
    draw_login_title_text,
    draw_wall_frame_bricks,
)
from ui.lobby_decor import LobbyDecor
from ui.lobby_icons import build_lobby_icons
from ui.widgets import Button, IconButton, TextInput, get_font
from viewport import compute_virtual_framebuffer, default_window_size


windowSize = default_window_size()

LOBBY_LEFT_MARGIN = 40
LOBBY_ROOM_PANEL_WIDTH = 340
LOBBY_ROOM_PANEL_MARGIN = 14
LOBBY_ROOM_PANEL_PADDING = 14
LOBBY_ROOM_ROW_HEIGHT = 48
LOBBY_ROOM_ROW_GAP = 8
LOBBY_NAME_COLOR = (0, 0, 0)
LOBBY_ICON_BTN_SIZE = 52
LOBBY_ICON_BTN_GAP = 16
LOBBY_ROOM_HEADER_BTN_SIZE = 44
LOBBY_ROOM_HEADER_BTN_GAP = 6
LOBBY_UI_GAP_ABOVE_GROUND = 8

# Debug: draw the active game camera position in screen space (viewport center).
DEBUG_DRAW_GAME_CAMERA_POSITION = True


class _GameBgmToggle:
    """Top-right in-run toggle for background music (pygame mixer channel 0)."""

    def __init__(self, sound: Sound, screen_width: int):
        self.sound = sound
        self.on = bool(pygame.mixer.Channel(0).get_busy())
        bw, bh = 104, 30
        self.button = Button(
            (screen_width - bw - 8, 8, bw, bh),
            "Music Off" if self.on else "Music On",
            self._toggle,
            font=get_font(20),
        )

    def _toggle(self):
        if self.on:
            self.sound.music_channel.stop()
            self.on = False
            self.button.text = "Music On"
        else:
            self.sound.music_channel.play(self.sound.soundtrack, loops=-1)
            self.on = True
            self.button.text = "Music Off"

    def mark_stopped_externally(self):
        """Game over / leave: channel was stopped outside this control."""
        self.on = False
        self.button.text = "Music On"

    def handle_event(self, event):
        self.button.handle_event(event)

    def draw(self, surface):
        self.button.update(pygame.mouse.get_pos())
        self.button.draw(surface)


def _draw_dashed_line(surface, color, start, end, width=1, dash=8, gap=4):
    x0, y0 = start
    x1, y1 = end
    dx = x1 - x0
    dy = y1 - y0
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0:
        return
    ux, uy = dx / length, dy / length
    traveled = 0.0
    while traveled < length:
        seg_start = traveled
        seg_end = min(traveled + dash, length)
        p0 = (int(x0 + ux * seg_start), int(y0 + uy * seg_start))
        p1 = (int(x0 + ux * seg_end), int(y0 + uy * seg_end))
        pygame.draw.line(surface, color, p0, p1, width)
        traveled += dash + gap


def draw_game_camera_position_debug(screen):
    if not DEBUG_DRAW_GAME_CAMERA_POSITION:
        return
    w, h = windowSize
    cx, cy = w // 2, h // 2
    half = 10
    color = (0, 255, 200)
    width = 2
    dash, gap = 6, 4
    left = cx - half
    right = cx + half
    top = cy - half
    bottom = cy + half
    _draw_dashed_line(screen, color, (left, top), (right, top), width=width, dash=dash, gap=gap)
    _draw_dashed_line(screen, color, (right, top), (right, bottom), width=width, dash=dash, gap=gap)
    _draw_dashed_line(screen, color, (right, bottom), (left, bottom), width=width, dash=dash, gap=gap)
    _draw_dashed_line(screen, color, (left, bottom), (left, top), width=width, dash=dash, gap=gap)


class Scene:
    def __init__(self, screen, network: NetworkClient):
        self.screen = screen
        self.network = network
        self.next_scene = None
        self.payload = None

    def handle_events(self, events):
        raise NotImplementedError

    def handle_network(self, messages):
        pass

    def update(self, dt_ms):
        pass

    def draw(self):
        raise NotImplementedError


def _random_username() -> str:
    """Six random uppercase letters (A–Z), default login name."""
    return "".join(random.choices(string.ascii_uppercase, k=6))


class LoginScene(Scene):
    def __init__(self, screen, network: NetworkClient):
        super().__init__(screen, network)
        self._sprites = Sprites()
        self._drifting_clouds = LoginDriftingClouds(
            windowSize[0], windowSize[1]
        )
        title_center = (windowSize[0] // 2, 160)
        self._title_center = title_center
        self._title_colors = build_title_letter_colors(self._sprites.spriteCollection)
        self._wall_mario = LoginWallMario(
            self._sprites.spriteCollection, title_center
        )
        self._frame_mushrooms = LoginFrameMushrooms(
            self._sprites.spriteCollection, title_center
        )
        self.font_body = get_font(28)
        self.message = ""
        input_width = 320
        input_height = 48
        center_x = windowSize[0] // 2
        self.input_username = TextInput(
            rect=(center_x - input_width // 2, 296, input_width, input_height),
            placeholder="Enter username...",
            max_length=16,
        )
        self.input_username.text = _random_username()
        self.button_login = Button(
            rect=(center_x - 60, 376, 120, 48),
            text="Enter",
            callback=self.attempt_login,
        )
        self.in_progress = False

    def attempt_login(self):
        if self.in_progress:
            return
        username = self.input_username.get_value()
        if not username:
            username = _random_username()
        try:
            self.in_progress = True
            self.message = "正在连接服务器..."
            login_response = self.network.connect(username)
            self.message = "Login successful, entering lobby..."
            self.next_scene = "lobby"
            self.payload = {"username": login_response["username"]}
        except (NetworkError, OSError) as exc:
            self.message = f"连接失败: {exc}"
        finally:
            self.in_progress = False

    def handle_events(self, events):
        for event in events:
            self.input_username.handle_event(event)
            self.button_login.handle_event(event)

    def update(self, dt_ms):
        self._drifting_clouds.update(dt_ms)
        self._wall_mario.update(dt_ms)
        self._frame_mushrooms.update(dt_ms)
        self.input_username.update(dt_ms)
        self.button_login.update(pygame.mouse.get_pos())

    def draw(self):
        draw_login_sky(
            self.screen,
            self._sprites.spriteCollection,
            drifting_clouds=self._drifting_clouds,
        )
        draw_wall_frame_bricks(
            self.screen, self._sprites.spriteCollection, self._title_center
        )
        self._frame_mushrooms.draw(self.screen)
        draw_login_title_text(
            self.screen, self._title_center, self._title_colors
        )
        self._wall_mario.draw(self.screen)
        self.input_username.draw(self.screen)
        self.button_login.draw(self.screen)
        if self.message:
            message_surf = self.font_body.render(self.message, True, (220, 220, 100))
            self.screen.blit(
                message_surf, message_surf.get_rect(center=(windowSize[0] // 2, 446))
            )


class LobbyScene(Scene):
    def __init__(self, screen, network: NetworkClient, username: str):
        super().__init__(screen, network)
        self.username = username
        self._sprites = Sprites()
        sw, sh = windowSize
        sprites = self._sprites.spriteCollection
        ground = ground_band_rect(sw, sh, sprites)
        self._ground_rect = ground
        sky_floor = ground.top - LOBBY_UI_GAP_ABOVE_GROUND
        m = LOBBY_ROOM_PANEL_MARGIN
        self._room_panel_rect = pygame.Rect(
            sw - LOBBY_ROOM_PANEL_WIDTH - m,
            m,
            LOBBY_ROOM_PANEL_WIDTH,
            max(72, sky_floor - m),
        )
        self.font_body = get_font(26)
        self.font_welcome = get_font(36)
        self.font_room = get_font(22)
        self.font_panel_title = get_font(26, bold=True)
        self.font_subtitle = get_font(28)
        self.font_empty = get_font(20)
        self._hovered_room_idx: int | None = None
        self._decor = LobbyDecor(
            sw,
            sh,
            sprites,
            ground_top=ground.top,
            panel_left=self._room_panel_rect.left,
        )
        self.rooms = []
        self.message = ""
        self.waiting = False
        self.waiting_room_id = None
        self.pending_join = None
        self.last_refresh_time = 0
        self.refresh_interval_ms = 5000

        icons = build_lobby_icons()
        sz = LOBBY_ICON_BTN_SIZE
        header_btn_kw = {"show_border": False}
        self.button_refresh = IconButton(
            rect=(0, 0, LOBBY_ROOM_HEADER_BTN_SIZE, LOBBY_ROOM_HEADER_BTN_SIZE),
            icon=icons["refresh"],
            callback=self.request_rooms,
            tooltip="Refresh",
            **header_btn_kw,
        )
        self.button_create = IconButton(
            rect=(0, 0, LOBBY_ROOM_HEADER_BTN_SIZE, LOBBY_ROOM_HEADER_BTN_SIZE),
            icon=icons["create"],
            callback=self.create_room,
            tooltip="Create Room",
            **header_btn_kw,
        )
        self._layout_panel_header_buttons()
        self.button_leave = IconButton(
            rect=(0, 0, sz, sz),
            icon=icons["logout"],
            callback=self.exit_to_login,
            tooltip="Log Out",
            show_border=False,
        )
        self._layout_logout_button()
        self.button_cancel = Button(
            rect=(windowSize[0] // 2 - 90, windowSize[1] // 2 + 60, 180, 48),
            text="Cancel",
            callback=self.cancel_waiting,
        )
        self.overlay_font = get_font(32)
        self.network.request_room_list()

    def _room_panel_inner(self) -> pygame.Rect:
        return self._room_panel_rect.inflate(
            -LOBBY_ROOM_PANEL_PADDING * 2, -LOBBY_ROOM_PANEL_PADDING * 2
        )

    def _header_row_metrics(self) -> tuple[pygame.Rect, int, int]:
        inner = self._room_panel_inner()
        header = self.font_panel_title.render("Rooms", True, LOBBY_NAME_COLOR)
        row_h = max(header.get_height(), LOBBY_ROOM_HEADER_BTN_SIZE) + 4
        row_cy = inner.y + row_h // 2
        return inner, row_h, row_cy

    def _layout_logout_button(self) -> None:
        panel = self._room_panel_rect
        _, _, row_cy = self._header_row_metrics()
        sz = LOBBY_ICON_BTN_SIZE
        gap = 8
        self.button_leave.rect = pygame.Rect(0, 0, sz, sz)
        self.button_leave.rect.centery = row_cy
        self.button_leave.rect.right = panel.left - gap

    def _layout_panel_header_buttons(self) -> None:
        inner, row_h, row_cy = self._header_row_metrics()
        btn = LOBBY_ROOM_HEADER_BTN_SIZE
        gap = LOBBY_ROOM_HEADER_BTN_GAP
        y = row_cy - btn // 2
        self.button_refresh.rect = pygame.Rect(inner.right - btn, y, btn, btn)
        self.button_create.rect = pygame.Rect(
            inner.right - btn * 2 - gap, y, btn, btn
        )

    def exit_to_login(self):
        try:
            self.network.send_message({"type": "leave_room"})
        except Exception:
            pass
        self.network.close()
        self.next_scene = "login"

    def request_rooms(self):
        if self.waiting:
            return
        self.network.request_room_list()
        self.message = ""

    def create_room(self):
        if self.waiting:
            return
        self.waiting = True
        self.message = "Creating room..."
        self.network.request_create_room()

    def cancel_waiting(self):
        if not self.waiting:
            return
        try:
            self.network.send_message({"type": "leave_room"})
        except Exception:
            pass
        self.waiting = False
        self.waiting_room_id = None
        self.message = "Wait cancelled, refreshing room list..."
        self.network.request_room_list()

    def handle_events(self, events):
        for event in events:
            self.button_refresh.handle_event(event)
            self.button_create.handle_event(event)
            self.button_leave.handle_event(event)
            if self.waiting:
                self.button_cancel.handle_event(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self.waiting:
                    clicked_room = self._get_room_at_pos(event.pos)
                    if clicked_room:
                        self.pending_join = clicked_room
                        self.waiting = True
                        self.message = f"Joining room {clicked_room}..."
                        self.network.request_join_room(clicked_room)

    def update(self, dt_ms):
        mouse_pos = pygame.mouse.get_pos()
        self.button_refresh.update(mouse_pos)
        self.button_create.update(mouse_pos)
        self.button_leave.update(mouse_pos)
        if self.waiting:
            self.button_cancel.update(mouse_pos)
        self._decor.update(dt_ms)
        self._hovered_room_idx = None
        if not self.waiting:
            for idx, room in enumerate(self.rooms[:12]):
                rect = room.get("__rect")
                if rect and rect.collidepoint(mouse_pos):
                    self._hovered_room_idx = idx
                    break
        self.last_refresh_time += dt_ms
        if (
            not self.waiting
            and self.last_refresh_time >= self.refresh_interval_ms
        ):
            self.network.request_room_list()
            self.last_refresh_time = 0

    def handle_network(self, messages):
        for message in messages:
            msg_type = message.get("type")
            if msg_type == "rooms":
                self.rooms = message.get("rooms", [])
                self.message = ""
                self.last_refresh_time = 0
            elif msg_type == "room_created":
                self.waiting = True
                self.waiting_room_id = message.get("room_id")
                self.message = f"Room {self.waiting_room_id} created, waiting for another player..."
            elif msg_type == "room_joined":
                self.waiting = True
                self.waiting_room_id = message.get("room_id")
                self.message = f"Joined room {self.waiting_room_id}, waiting for another player..."
            elif msg_type == "room_waiting":
                players = ", ".join(message.get("players", []))
                self.message = f"Players: {players}, waiting..."
            elif msg_type == "room_ready":
                self.next_scene = "game"
                self.payload = {
                    "username": self.username,
                    "room_ready": message,
                }
            elif msg_type == "room_peer_left":
                self.waiting = False
                self.waiting_room_id = None
                self.message = "Opponent left the room; wait cancelled."
                self.network.request_room_list()
            elif msg_type == "error":
                self.message = message.get("message", "An error occurred")
                self.waiting = False
                self.waiting_room_id = None
                self.network.request_room_list()
            elif msg_type == "hp_update":
                # ignore in lobby
                pass

    def _draw_room_panel(self) -> None:
        panel = self._room_panel_rect
        pygame.draw.rect(self.screen, (30, 30, 30), panel, width=3, border_radius=4)

        inner = self._room_panel_inner()
        header = self.font_panel_title.render("Rooms", True, LOBBY_NAME_COLOR)
        row_h = max(header.get_height(), LOBBY_ROOM_HEADER_BTN_SIZE) + 4
        self.screen.blit(
            header,
            (inner.x + 10, inner.y + (row_h - header.get_height()) // 2),
        )
        self._layout_panel_header_buttons()
        self.button_create.draw(self.screen)
        self.button_refresh.draw(self.screen)

        list_top = inner.y + row_h + 10
        list_bottom = inner.bottom
        row_step = LOBBY_ROOM_ROW_HEIGHT + LOBBY_ROOM_ROW_GAP
        max_rows = max(0, (list_bottom - list_top) // row_step)

        if max_rows == 0 and not self.rooms:
            empty = self.font_empty.render(
                "No rooms yet — tap + to create one", True, (50, 50, 50)
            )
            self.screen.blit(
                empty,
                empty.get_rect(center=(inner.centerx, (list_top + inner.bottom) // 2)),
            )

        for idx, room in enumerate(self.rooms[:max_rows]):
            rect = pygame.Rect(
                inner.x,
                list_top + idx * row_step,
                inner.width,
                LOBBY_ROOM_ROW_HEIGHT,
            )
            if idx == self._hovered_room_idx:
                hover = pygame.Surface(rect.size, pygame.SRCALPHA)
                hover.fill((120, 180, 255, 70))
                self.screen.blit(hover, rect.topleft)
            pygame.draw.rect(self.screen, (90, 90, 90), rect, width=1, border_radius=4)
            self._blit_room_row(rect, room)
            room["__rect"] = rect

        for room in self.rooms[max_rows:]:
            room.pop("__rect", None)

    def _blit_room_row(self, rect: pygame.Rect, room: dict) -> None:
        pad = 10
        room_id = room.get("room_id", "???")
        room_surf = self.font_room.render(f"Room {room_id}", True, (70, 70, 70))
        players = room.get("players", [])
        if players:
            names_text = ", ".join(players)
        else:
            names_text = "(empty)"
        names_surf = self.font_room.render(names_text, True, LOBBY_NAME_COLOR)
        y = rect.y + (rect.height - room_surf.get_height()) // 2
        self.screen.blit(room_surf, (rect.x + pad, y))
        names_rect = names_surf.get_rect(right=rect.right - pad, centery=rect.centery)
        self.screen.blit(names_surf, names_rect)

    def draw(self):
        sprites = self._sprites.spriteCollection
        draw_sky_tiles(self.screen, sprites)
        self._decor.draw_clouds(self.screen)
        draw_ground_tiles(self.screen, sprites)
        self._decor.draw_foreground(self.screen)

        welcome = f"Welcome, {self.username}"
        tx, ty = LOBBY_LEFT_MARGIN, 40
        title = self.font_welcome.render(welcome, True, LOBBY_NAME_COLOR)
        self.screen.blit(title, (tx, ty))
        subtitle = self.font_subtitle.render("Multiplayer Lobby", True, (30, 90, 140))
        self.screen.blit(subtitle, (tx, ty + title.get_height() + 4))

        self._draw_room_panel()
        self.button_leave.draw(self.screen)

        if self.waiting:
            overlay = pygame.Surface(windowSize, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            text = self.overlay_font.render(
                self.message or "Waiting for another player...", True, (255, 255, 255)
            )
            self.screen.blit(
                text, text.get_rect(center=(windowSize[0] // 2, windowSize[1] // 2))
            )
            self.button_cancel.rect.centerx = windowSize[0] // 2
            self.button_cancel.rect.top = windowSize[1] // 2 + 40
            self.button_cancel.draw(self.screen)

    def _get_room_at_pos(self, pos):
        for room in self.rooms:
            rect = room.get("__rect")
            if rect and rect.collidepoint(pos):
                return room.get("room_id")
        return None


def compute_spawn_position(
    spawn: str, level: Level, viewport_w: float | None = None
) -> tuple[int, int]:
    base_y = 32 * 11
    vw = float(viewport_w if viewport_w is not None else windowSize[0])
    if spawn == "right":
        if level.levelLength:
            spawn_x = max((level.levelLength - 3) * 32, int(vw) - 96)
        else:
            spawn_x = int(vw) - 96
    else:
        spawn_x = 48
    return spawn_x, base_y


def build_remote_players(
    room_msg: dict,
    local_username: str,
    level: Level,
    viewport_w: float | None = None,
):
    remote: dict[str, RemotePlayer] = {}
    udp_mapping: dict[int, str] = {}
    for player in room_msg.get("players", []):
        username = player.get("username")
        client_id = player.get("client_id")
        if isinstance(client_id, int) and username:
            udp_mapping[client_id] = username
        if username and username != local_username:
            spawn = player.get("spawn", "right")
            rp = RemotePlayer(username)
            spawn_x, spawn_y = compute_spawn_position(spawn, level, viewport_w)
            rp.rect.x = spawn_x
            rp.rect.y = spawn_y
            rp.state["position"] = [spawn_x, spawn_y]
            rp.prev_position = [spawn_x, spawn_y]
            rp.visible = True
            remote[username] = rp
    return remote, udp_mapping


def collect_local_state(mario: Mario, dashboard: Dashboard) -> dict:
    vel_x = getattr(mario.vel, "x", 0)
    vel_y = getattr(mario.vel, "y", 0)
    return {
        "position": [mario.rect.x, mario.rect.y],
        "velocity": [vel_x, vel_y],
        "hp": getattr(mario, "hp", 30),
        "power": getattr(mario, "powerUpState", 0),
        "score": dashboard.points,
        "dying": getattr(mario, "is_dying", False),
        "death_timer": getattr(mario, "death_timer", 0),
    }


def collect_udp_state(mario: Mario) -> dict:
    flags = 0
    if getattr(mario, "onGround", False):
        flags |= 0b0001
    if getattr(mario, "inJump", False):
        flags |= 0b0010
    if getattr(mario, "is_dying", False):
        flags |= 0b0100
    heading = 0
    go_trait = getattr(mario, "traits", {}).get("goTrait") if hasattr(mario, "traits") else None
    if go_trait:
        heading = getattr(go_trait, "heading", heading)
    return {
        "x": mario.rect.x,
        "y": mario.rect.y,
        "vx": getattr(mario.vel, "x", 0.0),
        "vy": getattr(mario.vel, "y", 0.0),
        "flags": flags,
        "heading": heading,
    }


def run_game(screen, network: NetworkClient, username: str, room_ready_msg: dict):
    pygame.mixer.pre_init(44100, -16, 2, 4096)
    # Re-apply the target game resolution every time a match starts.
    # This avoids stale window sizes when clients reconnect/join from older sessions.
    screen = pygame.display.set_mode(windowSize)
    pygame.display.set_caption("Super Mario Multiplayer")
    max_frame_rate = 60
    clock = pygame.time.Clock()
    dashboard = Dashboard("./img/font.png", 8, screen)
    sound = Sound()
    level = Level(screen, sound, dashboard)
    level.loadLevel("Level1-1")
    menu = Menu(screen, dashboard, level, sound)
    menu.start = True
    bgm_toggle = _GameBgmToggle(sound, windowSize[0])

    mario = Mario(0, 0, level, screen, dashboard, sound)
    spawn = room_ready_msg.get("your_spawn", "left")
    viewport_w, _ = compute_virtual_framebuffer(*screen.get_size())
    spawn_x, spawn_y = compute_spawn_position(spawn, level, viewport_w)
    mario.setPos(spawn_x, spawn_y)
    mario.camera.snap_to_entity()
    mario.camera.move()
    dashboard.set_player_health(mario.hp, mario.hp)
    remote_players, udp_id_map = build_remote_players(
        room_ready_msg, username, level, viewport_w
    )
    players_info = room_ready_msg.get("players", [])
    local_udp_id = None
    for player in players_info:
        if player.get("username") == username:
            local_udp_id = player.get("client_id")
            if isinstance(local_udp_id, int):
                udp_id_map[local_udp_id] = username
            break
    udp_info = room_ready_msg.get("udp")
    if isinstance(udp_info, dict):
        token = udp_info.get("token", "")
        udp_client_id = udp_info.get("client_id", 0)
        udp_port = udp_info.get("port")
        udp_host = udp_info.get("host")
        if network.enable_udp(
            token=token,
            client_id=udp_client_id,
            port=udp_port,
            host=udp_host,
        ):
            print(f"[debug] UDP enabled with token={token} client_id={udp_client_id} port={udp_port} host={udp_host}")
        else:
            print("[debug] UDP enable failed", token, udp_client_id, udp_port, udp_host)
        if local_udp_id is None:
            client_id = udp_info.get("client_id")
            if isinstance(client_id, int):
                local_udp_id = client_id
    projectiles: dict[str, Fireball] = {}
    projectile_owner_map: dict[str, str] = {}
    projectile_id_by_key: dict[str, int] = {}
    fall_reported = False
    fall_threshold = 440
    game_over_info = None
    death_wait_frames = None
    overlay_frames = None
    active_drop_entities = {}
    reported_drop_ids = set()
    pending_drop_collision_requests = set()
    last_tcp_state_sync = 0.0
    game_music_stopped = False

    def stop_game_music():
        nonlocal game_music_stopped
        if game_music_stopped:
            return
        try:
            sound.music_channel.stop()
        finally:
            game_music_stopped = True
        bgm_toggle.mark_stopped_externally()

    def handle_game_message(message, current_game_over):
        msg_type = message.get("type")
        if msg_type == "state_update":
            username_msg = message.get("username")
            if username_msg and username_msg != username:
                remote = remote_players.get(username_msg)
                state_payload = message.get("state", {}) or {}
                if not remote:
                    remote = RemotePlayer(username_msg)
                    remote_players[username_msg] = remote
                    initial_pos = state_payload.get("position", [remote.rect.x, remote.rect.y])
                    remote.prev_position = list(initial_pos)
                    remote.state["position"] = list(initial_pos)
                remote.update_from_state(state_payload)
        elif msg_type == "hp_update":
            mario.hp = message.get("hp", mario.hp)
            if mario.hp <= 0 and not mario.is_dying:
                mario.begin_death()
        elif msg_type == "player_hit":
            pass
        elif msg_type == "bullet_event":
            event = message.get("event")
            bullet_id = message.get("bullet_id")
            owner = message.get("owner")
            if event == "spawn" and bullet_id:
                if bullet_id not in projectiles:
                    position = message.get("position", [0, 0])
                    direction = message.get("direction", 1)
                    speed = message.get("speed", 8)
                    projectiles[bullet_id] = Fireball(bullet_id, owner, position, direction, speed, level)
                    projectile_owner_map[bullet_id] = owner
            elif event == "despawn" and bullet_id:
                projectile_owner_map.pop(bullet_id, None)
                projectile_id_by_key.pop(bullet_id, None)
                projectiles.pop(bullet_id, None)
        elif msg_type == "spawn_drop":
            spawn_drop_from_event(message)
        elif msg_type == "drop_collected":
            drop_id = message.get("drop_id")
            if drop_id:
                reported_drop_ids.add(drop_id)
                remove_drop_by_id(level, drop_id, active_drop_entities)
                pending_drop_collision_requests.discard(drop_id)
        elif msg_type == "drop_direction":
            drop_id = message.get("drop_id")
            direction = message.get("direction")
            if drop_id is not None:
                set_drop_direction(drop_id, direction)
                pending_drop_collision_requests.discard(drop_id)
        elif msg_type == "tile_break":
            tile_x = message.get("x")
            tile_y = message.get("y")
            if isinstance(tile_x, int) and isinstance(tile_y, int):
                level.break_tile(tile_x, tile_y, play_sound=True, record_event=False)
        elif msg_type == "state_snapshot":
            for player in message.get("players", []):
                username_msg = player.get("username")
                if not username_msg or username_msg == username:
                    continue
                remote = remote_players.get(username_msg)
                if not remote:
                    continue
                client_id = player.get("client_id")
                if isinstance(client_id, int):
                    udp_id_map[client_id] = username_msg
                snapshot_state = {
                    "position": [player.get("x", remote.rect.x), player.get("y", remote.rect.y)],
                    "velocity": [player.get("vx", 0.0), player.get("vy", 0.0)],
                    "flags": player.get("flags", 0),
                    "heading": player.get("heading", remote.heading),
                    "timestamp": player.get("timestamp", message.get("timestamp")),
                    "dying": player.get("flags", 0) & 0b0100,
                }
                remote.state["hp"] = player.get("hp", remote.state.get("hp", 30))
                remote.apply_snapshot(snapshot_state)
        elif msg_type == "game_over":
            return message
        return current_game_over

    def compute_death_wait_frames(game_over_message):
        loser = game_over_message.get("loser")
        if loser == username:
            return max(mario.death_timer, 0)
        remote = remote_players.get(loser)
        if remote and remote.is_dying:
            return max(remote.death_timer, 0)
        return 60

    def spawn_drop_from_event(event: dict):
        drop_id = event.get("drop_id")
        if drop_id and drop_id in active_drop_entities:
            return
        drop_type = event.get("drop_type", "coin")
        spawn_x = event.get("x", 48)
        direction = event.get("direction")
        try:
            spawn_x = float(spawn_x)
        except (TypeError, ValueError):
            return
        drop_viewport_w, _ = compute_virtual_framebuffer(*screen.get_size())
        if level.levelLength:
            right_bound = max(96, level.levelLength * 32 - 48)
        else:
            right_bound = max(96, int(drop_viewport_w) - 48)
        spawn_x = max(48, min(spawn_x, right_bound))
        sky_drop = SkyDrop(drop_type, spawn_x, screen, level, level.sprites.spriteCollection, sound)
        if drop_type == "mushroom" and direction in (-1, 1):
            sky_drop.initial_direction = direction
        if drop_id:
            sky_drop.direction_callback = lambda did, side: handle_local_mushroom_event(did, side)
        level.entityList.append(sky_drop)
        if drop_id:
            active_drop_entities[drop_id] = sky_drop
            sky_drop.drop_id = drop_id

    def handle_local_mushroom_event(drop_id: str, side: Optional[str]):
        if side is None:
            pending_drop_collision_requests.discard(drop_id)
            return
        if drop_id in pending_drop_collision_requests:
            return
        pending_drop_collision_requests.add(drop_id)
        network.send_drop_collision(drop_id, side)

    def set_drop_direction(drop_id: str, direction):
        entity = find_drop_entity(drop_id)
        if not entity:
            return
        if isinstance(entity, SkyDrop):
            entity.initial_direction = direction
            return
        target = entity
        replacement = getattr(entity, "spawned_entity", None)
        if replacement is not None:
            target = replacement
            active_drop_entities[drop_id] = replacement
        if isinstance(target, SkyMushroom):
            target.apply_direction(direction)
            target.clear_collision_request()

    def find_drop_entity(drop_id: str):
        entity = active_drop_entities.get(drop_id)
        if entity is None:
            for ent in level.entityList:
                if getattr(ent, "drop_id", None) == drop_id:
                    entity = ent
                    active_drop_entities[drop_id] = ent
                    break
        return entity

    try:
        while not mario.restart:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    try:
                        network.send_message({"type": "leave_room"})
                    except Exception:
                        pass
                    network.close()
                    pygame.quit()
                    sys.exit(0)
                bgm_toggle.handle_event(event)

            udp_events = network.poll_udp()
            for msg_type, event in udp_events:
                if msg_type == MSG_PLAYER_STATE:
                    sender_id = event.get("client_id")
                    if sender_id is None or sender_id == local_udp_id:
                        continue
                    username_msg = udp_id_map.get(sender_id)
                    if not username_msg:
                        continue
                    remote = remote_players.get(username_msg)
                    if not remote:
                        continue
                    player_state = event.get("player_state")
                    if player_state is None:
                        continue
                    remote.apply_udp_state(player_state, event.get("timestamp"))
                elif msg_type == MSG_PROJECTILE_STATE:
                    state = event.get("projectile_state")
                    if state is None:
                        print("[udp] projectile state missing payload")
                        continue
                    sender_id = event.get("client_id")
                    owner_name = udp_id_map.get(sender_id)
                    if owner_name is None:
                        print(f"[udp] projectile owner missing for sender={sender_id}")
                        continue
                    proj_id = state.get("projectile_id")
                    if proj_id is None:
                        continue
                    proj_key = f"udp_{proj_id}"
                    flags = state.get("flags", 0)
                    if flags & PROJECTILE_FLAG_DESPAWN:
                        projectile_owner_map.pop(proj_key, None)
                        projectile_id_by_key.pop(proj_key, None)
                        projectiles.pop(proj_key, None)
                        continue
                    if proj_key not in projectiles:
                        spawn_position = (state.get("x", 0), state.get("y", 0))
                        bullet = Fireball(proj_key, owner_name, spawn_position, 1 if state.get("vx", 0) >= 0 else -1, 8, level)
                        projectiles[proj_key] = bullet
                        print(f"[debug] projectile spawn {proj_key} owner={owner_name} pos={spawn_position}")
                    projectile_owner_map[proj_key] = owner_name
                    projectile_id_by_key[proj_key] = proj_id
                    projectile = projectiles.get(proj_key)
                    if projectile:
                        projectile.set_state(state)

            if mario.pause:
                mario.pauseObj.update()
                bgm_toggle.draw(screen)
                pygame.display.update()
            else:
                level.drawLevel(mario.camera)
                dashboard.set_player_health(mario.hp)
                dashboard.update()
                mario.update()
                udp_state_payload = collect_udp_state(mario)
                network.send_udp_player_state(udp_state_payload)
                for tile_x, tile_y in level.consume_broken_tiles():
                    network.send_tile_break(tile_x, tile_y)
                for drop_id, entity in list(active_drop_entities.items()):
                    replacement = getattr(entity, "spawned_entity", None)
                    if replacement is not None:
                        replacement.drop_id = drop_id
                        active_drop_entities[drop_id] = replacement
                        entity.spawned_entity = None
                        entity = replacement
                    if entity not in level.entityList or getattr(entity, "alive", True) is None:
                        active_drop_entities.pop(drop_id, None)
                        pending_drop_collision_requests.discard(drop_id)
                        if drop_id not in reported_drop_ids:
                            network.send_drop_collected(drop_id)
                            reported_drop_ids.add(drop_id)
                        continue
                    mushroom = entity
                    if isinstance(entity, SkyDrop):
                        mushroom = getattr(entity, "spawned_entity", None)
                    if isinstance(mushroom, SkyMushroom):
                        if mushroom.pending_collision and drop_id not in pending_drop_collision_requests:
                            handle_local_mushroom_event(drop_id, mushroom.pending_collision)

                spawned_projectiles = mario.consume_spawned_projectiles()
                for data in spawned_projectiles:
                    direction = data.get("direction", 1)
                    network.send_udp_action(ACTION_FIRE, param=1 if direction >= 0 else 0, client_id=local_udp_id)

                messages = network.poll()
                for message in messages:
                    game_over_info = handle_game_message(message, game_over_info)
                    if game_over_info:
                        stop_game_music()
                        break

                # Keep entity/projectile drawing on the exact same camera transform
                # used by level rendering (mario.camera).
                camera_world_x = max(0, -int(mario.camera.x))
                camera_world_y = 0
                game_viewport_w, _ = compute_virtual_framebuffer(*screen.get_size())
                level_width = max(level.levelLength * 32, int(game_viewport_w))
                for bullet_key, bullet in list(projectiles.items()):
                    owner_name = projectile_owner_map.get(bullet_key, bullet.owner)
                    if owner_name == username:
                        bullet.update()
                        proj_id = projectile_id_by_key.get(bullet_key)
                        hit_target = None
                        for remote in remote_players.values():
                            if remote.visible and bullet.rect.colliderect(remote.rect):
                                hit_target = remote.username
                                break
                        should_despawn = False
                        if hit_target:
                            network.send_player_hit(hit_target, damage=5)
                            should_despawn = True
                        elif bullet.should_despawn(level_width):
                            should_despawn = True
                        flags = PROJECTILE_FLAG_UPDATE
                        if should_despawn:
                            flags |= PROJECTILE_FLAG_DESPAWN
                        if proj_id is not None:
                            network.send_udp_projectile(proj_id, bullet.x, bullet.y, bullet.vx, bullet.vy, flags, client_id=local_udp_id)
                        if should_despawn:
                            projectile_owner_map.pop(bullet_key, None)
                            projectile_id_by_key.pop(bullet_key, None)
                            projectiles.pop(bullet_key, None)
                            continue
                    else:
                        projectile_owner_map[bullet_key] = owner_name
                        if not mario.is_dying and bullet.rect.colliderect(mario.rect):
                            projectiles.pop(bullet_key, None)
                            projectile_id_by_key.pop(bullet_key, None)
                            continue

                for remote in remote_players.values():
                    remote.draw(screen, camera_world_x, camera_world_y)
                for bullet in projectiles.values():
                    bullet.draw(screen, camera_world_x, camera_world_y)

                now_monotonic = time.monotonic()
                if now_monotonic - last_tcp_state_sync > 0.5:
                    network.send_state(collect_local_state(mario, dashboard))
                    last_tcp_state_sync = now_monotonic
                if not fall_reported and not mario.is_dying and mario.rect.bottom > fall_threshold:
                    fall_reported = True
                    print(f"[client] {username} fell off the map, reporting to server")
                    network.send_message({
                        "type": "player_fall",
                        "loser": username,
                    })

                if not game_over_info:
                    extra_msgs = network.poll()
                    for message in extra_msgs:
                        game_over_info = handle_game_message(message, game_over_info)
                        if game_over_info:
                            stop_game_music()
                            break

                if game_over_info:
                    if death_wait_frames is None:
                        death_wait_frames = compute_death_wait_frames(game_over_info)
                        overlay_frames = 180
                    if death_wait_frames > 0:
                        death_wait_frames -= 1
                        draw_game_camera_position_debug(screen)
                        bgm_toggle.draw(screen)
                        pygame.display.update()
                        clock.tick(max_frame_rate)
                        continue
                    overlay = pygame.Surface(windowSize, pygame.SRCALPHA)
                    overlay.fill((0, 0, 0, 180))
                    screen.blit(overlay, (0, 0))
                    font = get_font(42)
                    winner = game_over_info.get("winner", "Player")
                    text = f"{winner} wins!"
                    label = font.render(text, True, (255, 255, 255))
                    screen.blit(label, label.get_rect(center=(windowSize[0] // 2, windowSize[1] // 2)))
                    draw_game_camera_position_debug(screen)
                    bgm_toggle.draw(screen)
                    pygame.display.update()
                    overlay_frames -= 1
                    if overlay_frames > 0:
                        clock.tick(max_frame_rate)
                        continue
                    break

            draw_game_camera_position_debug(screen)
            bgm_toggle.draw(screen)
            pygame.display.update()
            clock.tick(max_frame_rate)
    finally:
        stop_game_music()
        try:
            network.send_message({"type": "leave_room"})
        except Exception:
            pass


def remove_drop_by_id(level: Level, drop_id: str, active_map: dict):
    entity = active_map.pop(drop_id, None)
    origin = entity
    candidate = entity
    if entity and getattr(entity, "spawned_entity", None):
        candidate = entity.spawned_entity
    if not candidate:
        for ent in list(level.entityList):
            if getattr(ent, "drop_id", None) == drop_id:
                candidate = ent
                break
    drop = candidate
    if origin and origin is not drop and origin in level.entityList:
        level.entityList.remove(origin)
        origin.alive = None
    if drop and drop in level.entityList:
        level.entityList.remove(drop)
    if drop:
        drop.alive = None


def main():
    pygame.init()
    screen = pygame.display.set_mode(windowSize)
    clock = pygame.time.Clock()
    network = NetworkClient()
    current_scene: Scene = LoginScene(screen, network)

    while True:
        dt_ms = clock.tick(60)
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                try:
                    network.send_message({"type": "leave_room"})
                except Exception:
                    pass
                network.close()
                pygame.quit()
                sys.exit(0)

        messages = network.poll()
        current_scene.handle_events(events)
        current_scene.handle_network(messages)
        current_scene.update(dt_ms)
        current_scene.draw()

        pygame.display.flip()

        if current_scene.next_scene == "login":
            screen = pygame.display.set_mode(windowSize)
            network = NetworkClient()
            current_scene = LoginScene(screen, network)
        elif current_scene.next_scene == "lobby":
            screen = pygame.display.set_mode(windowSize)
            username = current_scene.payload["username"]
            current_scene = LobbyScene(screen, network, username)
            network.request_room_list()
        elif current_scene.next_scene == "game":
            payload = current_scene.payload
            run_game(screen, network, payload["username"], payload["room_ready"])
            # Keep scene surface in sync with the actual display surface after game mode resets.
            screen = pygame.display.get_surface() or pygame.display.set_mode(windowSize)
            network.close()
            # 回到大厅，保持登录会话
            screen = pygame.display.set_mode(windowSize)
            network = NetworkClient()
            try:
                network.connect(payload["username"])
            except (NetworkError, OSError) as exc:
                print(f"[client] Failed to reconnect to server: {exc}")
                current_scene = LoginScene(screen, network)
                continue
            current_scene = LobbyScene(screen, network, payload["username"])
            network.request_room_list()


if __name__ == "__main__":
    exitmessage = "restart"
    while exitmessage == "restart":
        exitmessage = main()
