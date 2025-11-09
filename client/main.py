import random
import sys

import pygame

from classes.Dashboard import Dashboard
from classes.Level import Level
from classes.Menu import Menu
from classes.Sound import Sound
from entities.Mario import Mario
from entities.remote_player import RemotePlayer
from network.network_client import NetworkClient, NetworkError
from ui.widgets import Button, TextInput, get_font


windowSize = 640, 480


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


class LoginScene(Scene):
    def __init__(self, screen, network: NetworkClient):
        super().__init__(screen, network)
        self.font_title = get_font(48)
        self.font_body = get_font(28)
        self.message = ""
        input_width = 320
        input_height = 48
        center_x = windowSize[0] // 2
        self.input_username = TextInput(
            rect=(center_x - input_width // 2, 220, input_width, input_height),
            placeholder="输入用户名...",
            max_length=16,
        )
        self.button_login = Button(
            rect=(center_x - 80, 300, 160, 48),
            text="进入大厅",
            callback=self.attempt_login,
        )
        self.in_progress = False

    def attempt_login(self):
        if self.in_progress:
            return
        username = self.input_username.get_value()
        if not username:
            username = f"player-{random.randint(1000, 9999)}"
        try:
            self.in_progress = True
            self.message = "正在连接服务器..."
            login_response = self.network.connect(username)
            self.message = "登录成功，正在进入大厅..."
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
        self.input_username.update(dt_ms)
        self.button_login.update(pygame.mouse.get_pos())

    def draw(self):
        self.screen.fill((24, 24, 32))
        title = self.font_title.render("超级马里奥 - 联机版", True, (255, 255, 255))
        subtitle = self.font_body.render("请输入用户名登录游戏", True, (180, 180, 200))
        self.screen.blit(title, title.get_rect(center=(windowSize[0] // 2, 140)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(windowSize[0] // 2, 190)))
        self.input_username.draw(self.screen)
        self.button_login.draw(self.screen)
        if self.message:
            message_surf = self.font_body.render(self.message, True, (220, 220, 100))
            self.screen.blit(
                message_surf, message_surf.get_rect(center=(windowSize[0] // 2, 370))
            )


class LobbyScene(Scene):
    def __init__(self, screen, network: NetworkClient, username: str):
        super().__init__(screen, network)
        self.username = username
        self.font_title = get_font(44)
        self.font_body = get_font(26)
        self.font_room = get_font(24)
        self.rooms = []
        self.message = "刷新房间列表中..."
        self.waiting = False
        self.waiting_room_id = None
        self.pending_join = None
        self.last_refresh_time = 0
        self.refresh_interval_ms = 5000

        self.button_refresh = Button(
            rect=(60, 400, 140, 44),
            text="刷新",
            callback=self.request_rooms,
        )
        self.button_create = Button(
            rect=(240, 400, 140, 44),
            text="创建房间",
            callback=self.create_room,
        )
        self.button_leave = Button(
            rect=(420, 400, 140, 44),
            text="退出登录",
            callback=self.exit_to_login,
        )
        self.overlay_font = get_font(32)
        self.network.request_room_list()

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
        self.message = "刷新房间列表中..."

    def create_room(self):
        if self.waiting:
            return
        self.waiting = True
        self.message = "正在创建房间..."
        self.network.request_create_room()

    def handle_events(self, events):
        for event in events:
            self.button_refresh.handle_event(event)
            self.button_create.handle_event(event)
            self.button_leave.handle_event(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self.waiting:
                    clicked_room = self._get_room_at_pos(event.pos)
                    if clicked_room:
                        self.pending_join = clicked_room
                        self.waiting = True
                        self.message = f"正在加入房间 {clicked_room}..."
                        self.network.request_join_room(clicked_room)

    def update(self, dt_ms):
        mouse_pos = pygame.mouse.get_pos()
        self.button_refresh.update(mouse_pos)
        self.button_create.update(mouse_pos)
        self.button_leave.update(mouse_pos)
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
                self.message = f"当前可加入房间：{len(self.rooms)} 个"
                self.last_refresh_time = 0
            elif msg_type == "room_created":
                self.waiting = True
                self.waiting_room_id = message.get("room_id")
                self.message = f"房间 {self.waiting_room_id} 已创建，等待另一名玩家..."
            elif msg_type == "room_joined":
                self.waiting = True
                self.waiting_room_id = message.get("room_id")
                self.message = f"已进入房间 {self.waiting_room_id}，等待另一名玩家..."
            elif msg_type == "room_waiting":
                players = ", ".join(message.get("players", []))
                self.message = f"玩家列表：{players}，等待中..."
            elif msg_type == "room_ready":
                self.next_scene = "game"
                self.payload = {
                    "username": self.username,
                    "room_ready": message,
                }
            elif msg_type == "room_peer_left":
                self.waiting = False
                self.waiting_room_id = None
                self.message = "对方离开了房间，您已退出等待状态。"
            elif msg_type == "error":
                self.message = message.get("message", "发生错误")
                self.waiting = False
                self.waiting_room_id = None
            elif msg_type == "hp_update":
                # ignore in lobby
                pass

    def draw(self):
        self.screen.fill((28, 30, 40))
        title = self.font_title.render(
            f"欢迎，{self.username}", True, (255, 255, 255)
        )
        self.screen.blit(title, (50, 40))
        info = self.font_body.render(
            "点击房间加入，或创建新房间。", True, (180, 180, 200)
        )
        self.screen.blit(info, (50, 90))
        message = self.font_body.render(self.message, True, (200, 200, 120))
        self.screen.blit(message, (50, 130))

        self.button_refresh.draw(self.screen)
        self.button_create.draw(self.screen)
        self.button_leave.draw(self.screen)

        list_top = 180
        list_left = 60
        item_height = 48
        item_width = windowSize[0] - 120
        for idx, room in enumerate(self.rooms[:6]):
            rect = pygame.Rect(
                list_left, list_top + idx * (item_height + 10), item_width, item_height
            )
            pygame.draw.rect(
                self.screen, (50, 60, 90), rect, border_radius=6
            )
            pygame.draw.rect(
                self.screen, (70, 80, 110), rect, width=2, border_radius=6
            )
            room_id = room.get("room_id", "???")
            players = ", ".join(room.get("players", [])) or "(空)"
            label = self.font_room.render(
                f"房间 {room_id} | 玩家: {players}", True, (230, 230, 240)
            )
            self.screen.blit(label, (rect.x + 16, rect.y + 12))
            room["__rect"] = rect

        if self.waiting:
            overlay = pygame.Surface(windowSize, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            text = self.overlay_font.render(
                self.message or "等待另一名玩家加入...", True, (255, 255, 255)
            )
            self.screen.blit(
                text, text.get_rect(center=(windowSize[0] // 2, windowSize[1] // 2))
            )

    def _get_room_at_pos(self, pos):
        for room in self.rooms:
            rect = room.get("__rect")
            if rect and rect.collidepoint(pos):
                return room.get("room_id")
        return None


def compute_spawn_position(spawn: str, level: Level) -> tuple[int, int]:
    base_y = 32 * 11
    if spawn == "right":
        if level.levelLength:
            spawn_x = max((level.levelLength - 3) * 32, windowSize[0] - 96)
        else:
            spawn_x = windowSize[0] - 96
    else:
        spawn_x = 48
    return spawn_x, base_y


def build_remote_players(room_msg: dict, local_username: str, level: Level) -> dict:
    remote = {}
    for player in room_msg.get("players", []):
        username = player.get("username")
        if username and username != local_username:
            spawn = player.get("spawn", "right")
            rp = RemotePlayer(username)
            spawn_x, spawn_y = compute_spawn_position(spawn, level)
            rp.rect.x = spawn_x
            rp.rect.y = spawn_y
            rp.state["position"] = [spawn_x, spawn_y]
            rp.visible = True
            remote[username] = rp
    return remote


def collect_local_state(mario: Mario, dashboard: Dashboard) -> dict:
    vel_x = getattr(mario.vel, "x", 0)
    vel_y = getattr(mario.vel, "y", 0)
    return {
        "position": [mario.rect.x, mario.rect.y],
        "velocity": [vel_x, vel_y],
        "hp": getattr(mario, "hp", 30),
        "power": getattr(mario, "powerUpState", 0),
        "score": dashboard.points,
    }


def run_game(screen, network: NetworkClient, username: str, room_ready_msg: dict):
    pygame.mixer.pre_init(44100, -16, 2, 4096)
    pygame.display.set_caption("Super Mario Multiplayer")
    max_frame_rate = 60
    clock = pygame.time.Clock()
    dashboard = Dashboard("./img/font.png", 8, screen)
    sound = Sound()
    level = Level(screen, sound, dashboard)
    level.loadLevel("Level1-1")
    menu = Menu(screen, dashboard, level, sound)
    menu.start = True

    mario = Mario(0, 0, level, screen, dashboard, sound)
    spawn = room_ready_msg.get("your_spawn", "left")
    spawn_x, spawn_y = compute_spawn_position(spawn, level)
    mario.setPos(spawn_x, spawn_y)
    mario.camera.snap_to_entity()
    mario.camera.move()
    remote_players = build_remote_players(room_ready_msg, username, level)
    fall_reported = False
    fall_threshold = 440

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

            if mario.pause:
                mario.pauseObj.update()
            else:
                level.drawLevel(mario.camera)
                dashboard.update()
                mario.update()

                messages = network.poll()
                game_over_info = None
                for message in messages:
                    msg_type = message.get("type")
                    if msg_type == "state_update":
                        username_msg = message.get("username")
                        if username_msg and username_msg != username:
                            remote = remote_players.get(username_msg)
                            if not remote:
                                remote = RemotePlayer(username_msg)
                                remote_players[username_msg] = remote
                            remote.update_from_state(message.get("state", {}))
                            camera_world_x = mario.rect.x - (10 * 32)
                            screen_x = remote.rect.x - camera_world_x
                    elif msg_type == "hp_update":
                        mario.hp = message.get("hp", mario.hp)
                    elif msg_type == "player_hit":
                        pass
                    elif msg_type == "game_over":
                        game_over_info = message
                        break

                raw_camera_x = mario.rect.x - (10 * 32)
                max_camera_world_x = max(level.levelLength * 32 - windowSize[0], 0)
                camera_world_x = max(0, min(raw_camera_x, max_camera_world_x))
                camera_world_y = 0
                for remote in remote_players.values():
                    remote.draw(screen, camera_world_x, camera_world_y)

                network.send_state(collect_local_state(mario, dashboard))
                if not fall_reported and mario.rect.bottom > fall_threshold:
                    fall_reported = True
                    print(f"[client] {username} fell off the map, reporting to server")
                    network.send_message({
                        "type": "player_fall",
                        "loser": username,
                    })

                if not game_over_info:
                    extra_msgs = network.poll()
                    for message in extra_msgs:
                        if message.get("type") == "game_over":
                            game_over_info = message
                            break

                if game_over_info:
                    overlay = pygame.Surface(windowSize, pygame.SRCALPHA)
                    overlay.fill((0, 0, 0, 180))
                    screen.blit(overlay, (0, 0))
                    font = get_font(42)
                    winner = game_over_info.get("winner", "玩家")
                    text = f"{winner} 获胜！"
                    label = font.render(text, True, (255, 255, 255))
                    screen.blit(label, label.get_rect(center=(windowSize[0] // 2, windowSize[1] // 2)))
                    pygame.display.update()
                    pygame.time.delay(2000)
                    break

            pygame.display.update()
            clock.tick(max_frame_rate)
    finally:
        try:
            network.send_message({"type": "leave_room"})
        except Exception:
            pass


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
            network = NetworkClient()
            current_scene = LoginScene(screen, network)
        elif current_scene.next_scene == "lobby":
            username = current_scene.payload["username"]
            current_scene = LobbyScene(screen, network, username)
            network.request_room_list()
        elif current_scene.next_scene == "game":
            payload = current_scene.payload
            run_game(screen, network, payload["username"], payload["room_ready"])
            network.close()
            # 回到大厅，保持登录会话
            network = NetworkClient()
            try:
                network.connect(payload["username"])
            except (NetworkError, OSError) as exc:
                print(f"[client] 重新连接服务器失败: {exc}")
                current_scene = LoginScene(screen, network)
                continue
            current_scene = LobbyScene(screen, network, payload["username"])
            network.request_room_list()


if __name__ == "__main__":
    exitmessage = "restart"
    while exitmessage == "restart":
        exitmessage = main()
