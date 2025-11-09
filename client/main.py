import random
import sys
import time

import pygame

from classes.Dashboard import Dashboard
from classes.Level import Level
from classes.Menu import Menu
from classes.Sound import Sound
from entities.Mario import Mario
from entities.remote_player import RemotePlayer
from network.network_client import NetworkClient, NetworkError


windowSize = 640, 480


def prompt_username() -> str:
    username = input("请输入用户名 (留空自动生成): ").strip()
    if not username:
        username = f"player-{random.randint(1000, 9999)}"
    return username


def run_lobby(network: NetworkClient, username: str) -> dict:
    print("\n=== 大厅 ===")
    print("输入 C 创建房间 / J 加入房间 / R 刷新房间列表")
    rooms = network.list_rooms()
    print_rooms(rooms)

    while True:
        choice = input("请选择操作 (C/J/R): ").strip().lower()
        if choice == "c":
            room_id = network.create_room()
            print(f"已创建房间 {room_id}，等待另一位玩家加入...")
            ready_msg = network.wait_for_room_ready()
            print("玩家到齐，开始游戏！")
            return ready_msg
        if choice == "j":
            target_room = input("输入要加入的房间号: ").strip()
            if not target_room:
                print("房间号不能为空。")
                continue
            try:
                if network.join_room(target_room):
                    print("已加入房间，等待另一位玩家...")
                    ready_msg = network.wait_for_room_ready()
                    print("玩家到齐，开始游戏！")
                    return ready_msg
            except NetworkError as exc:
                print(f"加入房间失败: {exc}")
        if choice == "r":
            rooms = network.list_rooms()
            print_rooms(rooms)
        else:
            print("无效的选项，请重新输入。")


def print_rooms(rooms):
    if not rooms:
        print("当前没有可加入的房间。")
        return
    print("当前可加入的房间：")
    for room in rooms:
        players = ", ".join(room.get("players", [])) or "(空)"
        print(f"  - {room['room_id']} | 玩家: {players}")


def build_remote_players(room_msg: dict, local_username: str) -> dict:
    remote = {}
    for player in room_msg.get("players", []):
        username = player.get("username")
        if username and username != local_username:
            remote[username] = RemotePlayer(username)
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


def main():
    username = prompt_username()
    network = NetworkClient()
    room_ready_msg = None
    try:
        login_response = network.connect(username)
        print(f"登录成功，欢迎 {login_response['username']}!")
        room_ready_msg = run_lobby(network, username)
    except (NetworkError, OSError) as exc:
        print(f"网络错误: {exc}")
        network.close()
        time.sleep(1)
        return "exit"

    pygame.mixer.pre_init(44100, -16, 2, 4096)
    pygame.init()
    screen = pygame.display.set_mode(windowSize)
    max_frame_rate = 60
    dashboard = Dashboard("./img/font.png", 8, screen)
    sound = Sound()
    level = Level(screen, sound, dashboard)
    menu = Menu(screen, dashboard, level, sound)

    # 在进入游戏前跳过原有菜单等待流程
    menu.start = True

    mario = Mario(0, 0, level, screen, dashboard, sound)
    remote_players = build_remote_players(room_ready_msg, username)
    clock = pygame.time.Clock()

    try:
        while not mario.restart:
            pygame.display.set_caption(
                "Super Mario running with {:d} FPS".format(int(clock.get_fps()))
            )
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    network.send_message({"type": "leave_room"})
                    network.close()
                    sys.exit(0)

            if mario.pause:
                mario.pauseObj.update()
            else:
                level.drawLevel(mario.camera)
                dashboard.update()
                mario.update()

                # 处理网络消息
                for message in network.poll():
                    msg_type = message.get("type")
                    if msg_type == "state_update":
                        username_msg = message.get("username")
                        if username_msg and username_msg != username:
                            remote = remote_players.get(username_msg)
                            if remote:
                                remote.update_from_state(message.get("state", {}))
                    elif msg_type == "hp_update":
                        # TODO: 根据服务器的HP更新进行对应处理
                        pass
                    elif msg_type == "player_hit":
                        # TODO: 播放音效或展示提示
                        pass

                # 绘制远程玩家
                for remote in remote_players.values():
                    remote.draw(screen, mario.camera.x, mario.camera.y)

                # 同步本地状态到服务器
                network.send_state(collect_local_state(mario, dashboard))

            pygame.display.update()
            clock.tick(max_frame_rate)
    finally:
        network.send_message({"type": "leave_room"})
        network.close()

    return "restart"


if __name__ == "__main__":
    exitmessage = "restart"
    while exitmessage == "restart":
        exitmessage = main()
