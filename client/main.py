import random
import sys
import time
import uuid

import pygame

from classes.Dashboard import Dashboard
from classes.Level import Level
from classes.Menu import Menu
from classes.Sound import Sound
from entities.Mario import Mario
from entities.fireball import Fireball
from entities.sky_drop import SkyDrop, SkyMushroom
from typing import Optional
from entities.remote_player import RemotePlayer
from network.network_client import NetworkClient, NetworkError
from network.protocol import MSG_PLAYER_STATE
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
        self.button_cancel = Button(
            rect=(windowSize[0] // 2 - 90, windowSize[1] // 2 + 60, 180, 48),
            text="取消等待",
            callback=self.cancel_waiting,
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

    def cancel_waiting(self):
        if not self.waiting:
            return
        try:
            self.network.send_message({"type": "leave_room"})
        except Exception:
            pass
        self.waiting = False
        self.waiting_room_id = None
        self.message = "已取消等待，刷新房间列表中..."
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
                        self.message = f"正在加入房间 {clicked_room}..."
                        self.network.request_join_room(clicked_room)

    def update(self, dt_ms):
        mouse_pos = pygame.mouse.get_pos()
        self.button_refresh.update(mouse_pos)
        self.button_create.update(mouse_pos)
        self.button_leave.update(mouse_pos)
        if self.waiting:
            self.button_cancel.update(mouse_pos)
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
                self.network.request_room_list()
            elif msg_type == "error":
                self.message = message.get("message", "发生错误")
                self.waiting = False
                self.waiting_room_id = None
                self.network.request_room_list()
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
            self.button_cancel.rect.centerx = windowSize[0] // 2
            self.button_cancel.rect.top = windowSize[1] // 2 + 40
            self.button_cancel.draw(self.screen)

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


def build_remote_players(room_msg: dict, local_username: str, level: Level):
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
            spawn_x, spawn_y = compute_spawn_position(spawn, level)
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
    dashboard.set_player_health(mario.hp, mario.hp)
    remote_players, udp_id_map = build_remote_players(room_ready_msg, username, level)
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
        network.enable_udp(
            token=udp_info.get("token", ""),
            client_id=udp_info.get("client_id", 0),
            port=udp_info.get("port"),
            host=udp_info.get("host"),
        )
        if local_udp_id is None:
            client_id = udp_info.get("client_id")
            if isinstance(client_id, int):
                local_udp_id = client_id
    projectiles: dict[str, Fireball] = {}
    fall_reported = False
    fall_threshold = 440
    game_over_info = None
    death_wait_frames = None
    overlay_frames = None
    active_drop_entities = {}
    reported_drop_ids = set()
    pending_drop_collision_requests = set()
    last_tcp_state_sync = 0.0

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
                if bullet_id not in projectiles and owner != username:
                    position = message.get("position", [0, 0])
                    direction = message.get("direction", 1)
                    speed = message.get("speed", 8)
                    projectiles[bullet_id] = Fireball(bullet_id, owner, position, direction, speed, level)
            elif event == "despawn" and bullet_id:
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
        if level.levelLength:
            right_bound = max(96, level.levelLength * 32 - 48)
        else:
            right_bound = max(96, windowSize[0] - 48)
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

            if mario.pause:
                mario.pauseObj.update()
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
                    bullet_id = uuid.uuid4().hex
                    direction = data.get("direction", 1)
                    position = data.get("position", [mario.rect.centerx, mario.rect.centery])
                    speed = data.get("speed", 8)
                    projectiles[bullet_id] = Fireball(bullet_id, username, position, direction, speed, level)
                    network.send_bullet_event({
                        "event": "spawn",
                        "bullet_id": bullet_id,
                        "owner": username,
                        "position": position,
                        "direction": direction,
                        "speed": speed,
                    })

                messages = network.poll()
                for message in messages:
                    game_over_info = handle_game_message(message, game_over_info)
                    if game_over_info:
                        break

                raw_camera_x = mario.rect.x - (10 * 32)
                max_camera_world_x = max(level.levelLength * 32 - windowSize[0], 0)
                camera_world_x = max(0, min(raw_camera_x, max_camera_world_x))
                camera_world_y = 0
                level_width = max(level.levelLength * 32, windowSize[0])
                for bullet_id, bullet in list(projectiles.items()):
                    bullet.update()
                    if bullet.owner == username:
                        hit_target = None
                        for remote in remote_players.values():
                            if remote.visible and bullet.rect.colliderect(remote.rect):
                                hit_target = remote.username
                                break
                        if hit_target:
                            network.send_player_hit(hit_target, damage=5)
                            network.send_bullet_event({
                                "event": "despawn",
                                "bullet_id": bullet_id,
                                "owner": username,
                            })
                            projectiles.pop(bullet_id, None)
                            continue
                        if bullet.should_despawn(level_width):
                            network.send_bullet_event({
                                "event": "despawn",
                                "bullet_id": bullet_id,
                                "owner": username,
                            })
                            projectiles.pop(bullet_id, None)
                            continue
                    else:
                        if not mario.is_dying and bullet.rect.colliderect(mario.rect):
                            projectiles.pop(bullet_id, None)
                            continue
                        if bullet.should_despawn(level_width):
                            projectiles.pop(bullet_id, None)
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
                            break

                if game_over_info:
                    if death_wait_frames is None:
                        death_wait_frames = compute_death_wait_frames(game_over_info)
                        overlay_frames = 180
                    if death_wait_frames > 0:
                        death_wait_frames -= 1
                        pygame.display.update()
                        clock.tick(max_frame_rate)
                        continue
                    overlay = pygame.Surface(windowSize, pygame.SRCALPHA)
                    overlay.fill((0, 0, 0, 180))
                    screen.blit(overlay, (0, 0))
                    font = get_font(42)
                    winner = game_over_info.get("winner", "玩家")
                    text = f"{winner} 获胜！"
                    label = font.render(text, True, (255, 255, 255))
                    screen.blit(label, label.get_rect(center=(windowSize[0] // 2, windowSize[1] // 2)))
                    pygame.display.update()
                    overlay_frames -= 1
                    if overlay_frames > 0:
                        clock.tick(max_frame_rate)
                        continue
                    break

            pygame.display.update()
            clock.tick(max_frame_rate)
    finally:
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
