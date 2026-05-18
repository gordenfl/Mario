from __future__ import annotations

import os
import random
import string
import threading
from functools import partial
from typing import Any, Dict, List, Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from .font_config import text_font_kwargs
from .sky_bg import paint_login_sky
from .view import GameView
from .wall_title import WallFramedTitle


def _import_network():
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from client.network.network_client import NetworkClient, NetworkError

    return NetworkClient, NetworkError


NetworkClient, NetworkError = _import_network()

SERVER_HOST = os.environ.get("MARIO_SERVER_HOST", "192.168.1.75")
SERVER_PORT = int(os.environ.get("MARIO_SERVER_PORT", "8765"))

REFRESH_INTERVAL_MS = 5000
VIRTUAL_W = 852.0
VIRTUAL_H = 480.0


def _pc_color(rgb):
    return tuple(channel / 255.0 for channel in rgb) + (1.0,)


def _pc_rect(x: float, y_top: float, w: float, h: float):
    """Pygame-style top-left rect converted to Kivy's virtual bottom-left space."""
    return x, VIRTUAL_H - y_top - h, w, h


class PcLayout(FloatLayout):
    """Fixed 852x480 coordinate layout matching the pygame client screens."""

    def __init__(self, bg=(24, 24, 32), sky_bg: bool = False, cloud_layout=None, **kw):
        super().__init__(**kw)
        self._virtual_children = []
        self._sky_bg = sky_bg
        self._cloud_layout = cloud_layout
        if not sky_bg:
            with self.canvas.before:
                Color(*_pc_color(bg))
                self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._relayout, size=self._relayout)

    def add_pc_widget(self, widget, rect):
        widget.size_hint = (None, None)
        widget._pc_rect = rect
        self._virtual_children.append(widget)
        self.add_widget(widget)
        self._place(widget)
        return widget

    def _transform(self, rect):
        x, y, w, h = rect
        scale = min(self.width / VIRTUAL_W, self.height / VIRTUAL_H) if self.width and self.height else 1.0
        ox = self.x + (self.width - VIRTUAL_W * scale) * 0.5
        oy = self.y + (self.height - VIRTUAL_H * scale) * 0.5
        return (ox + x * scale, oy + y * scale), (w * scale, h * scale)

    def _place(self, widget):
        pos, size = self._transform(widget._pc_rect)
        widget.pos = pos
        widget.size = size
        if hasattr(widget, "text_size"):
            widget.text_size = size

    def _relayout(self, *_args):
        if self._sky_bg:
            self.canvas.before.clear()
            if self.width > 0 and self.height > 0:
                with self.canvas.before:
                    paint_login_sky(
                        self.x,
                        self.y,
                        self.width,
                        self.height,
                        cloud_positions=self._cloud_layout,
                    )
        else:
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size
        for widget in self._virtual_children:
            self._place(widget)


def _pc_label(text, font_size, color=(255, 255, 255), halign="left"):
    lbl = Label(
        text=text,
        font_size=f"{font_size}sp",
        color=_pc_color(color),
        halign=halign,
        valign="middle",
        **text_font_kwargs(),
    )
    return lbl


def _pc_button(text, font_size=22):
    btn = Button(
        text=text,
        font_size=f"{font_size}sp",
        background_normal="",
        background_down="",
        background_color=_pc_color((66, 135, 245)),
        color=(1, 1, 1, 1),
        **text_font_kwargs(),
    )
    return btn


def _random_username() -> str:
    """Six random uppercase letters (A–Z), default login name."""
    return "".join(random.choices(string.ascii_uppercase, k=6))


class LoginScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.network: Optional[Any] = None
        self._busy = False

        from client.ui.sky_background import generate_login_cloud_layout, login_ui_forbidden_rects

        vw, vh = int(VIRTUAL_W), int(VIRTUAL_H)
        forbidden = login_ui_forbidden_rects(vw, vh)
        cloud_layout = generate_login_cloud_layout(vw, vh, forbidden)
        root = PcLayout(sky_bg=True, cloud_layout=cloud_layout)
        title = WallFramedTitle()
        self.username_input = TextInput(
            text=_random_username(),
            hint_text="Enter username...",
            multiline=False,
            font_size="22sp",
            foreground_color=(1, 1, 1, 1),
            background_normal="",
            background_active="",
            background_color=_pc_color((30, 30, 30)),
            cursor_color=(1, 1, 1, 1),
            hint_text_color=(0.58, 0.58, 0.58, 1),
            padding=[10, 10, 10, 10],
            **text_font_kwargs(),
        )
        self.btn_enter = _pc_button("Enter", font_size=22)
        self.btn_enter.bind(on_press=lambda *_: self._attempt_login())
        self.status = _pc_label(
            text="",
            font_size=18,
            color=(220, 220, 100),
            halign="center",
        )

        root.add_pc_widget(title, _pc_rect(114, 112, 624, 128))
        root.add_pc_widget(self.username_input, _pc_rect(266, 296, 320, 48))
        root.add_pc_widget(self.btn_enter, _pc_rect(366, 376, 120, 48))
        root.add_pc_widget(self.status, _pc_rect(80, 436, 692, 82))
        self.add_widget(root)

    def on_enter(self):
        self.username_input.text = _random_username()
        self._busy = False
        self.btn_enter.disabled = False
        self.status.text = ""

    def _attempt_login(self):
        if self._busy:
            return
        name = (self.username_input.text or "").strip()
        if not name:
            name = _random_username()

        self._busy = True
        self.btn_enter.disabled = True
        self.status.text = "正在连接服务器..."

        def worker():
            try:
                nc = NetworkClient(host=SERVER_HOST, port=SERVER_PORT)
                resp = nc.connect(name)
                username = resp.get("username", name)
                Clock.schedule_once(lambda dt: self._on_ok(nc, username), 0)
            except (NetworkError, OSError) as exc:
                # Python 3 deletes `exc` when leaving `except`; defer with a captured string.
                fail_msg = str(exc)
                Clock.schedule_once(lambda dt: self._on_fail(fail_msg), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _on_ok(self, nc: Any, username: str):
        self._busy = False
        self.btn_enter.disabled = False
        self.network = nc
        lobby = self.manager.get_screen("lobby")
        lobby.attach(nc, username)
        self.manager.current = "lobby"

    def _on_fail(self, msg: str):
        self._busy = False
        self.btn_enter.disabled = False
        low = msg.lower()
        if "refused" in low or "errno 61" in low or "connection refused" in low:
            hint = (
                f"{msg}\n\n请先在本机启动游戏服务器，在项目根目录执行：\n"
                "  python server/server.py\n"
                f"（客户端默认连 {SERVER_HOST}:{SERVER_PORT}，可用环境变量 MARIO_SERVER_HOST / MARIO_SERVER_PORT 修改）"
            )
            self.status.text = hint
            return
        self.status.text = f"连接失败: {msg}"


class LobbyScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.network: Optional[Any] = None
        self.username: str = ""
        self.rooms: List[Dict[str, Any]] = []
        self.message: str = ""
        self.waiting: bool = False
        self.waiting_room_id: Optional[str] = None
        self._poll_ev = None
        self._refresh_ms = 0.0
        self._room_buttons = []

        root = PcLayout(bg=(28, 30, 40))
        self._pc_root = root

        self.title_lbl = _pc_label(
            text="欢迎",
            font_size=30,
            color=(255, 255, 255),
            halign="left",
        )
        self.hint_lbl = _pc_label(
            text="点击房间加入，或创建新房间。",
            font_size=20,
            color=(180, 180, 200),
            halign="left",
        )
        self.msg_lbl = _pc_label(
            text="",
            font_size=20,
            color=(200, 200, 120),
            halign="left",
        )

        self.button_refresh = _pc_button("刷新", font_size=20)
        self.button_create = _pc_button("创建房间", font_size=20)
        self.button_leave = _pc_button("退出登录", font_size=20)
        self.button_refresh.bind(on_press=lambda *_: self.request_rooms())
        self.button_create.bind(on_press=lambda *_: self.create_room())
        self.button_leave.bind(on_press=lambda *_: self.exit_to_login())

        root.add_pc_widget(self.title_lbl, _pc_rect(50, 40, 760, 44))
        root.add_pc_widget(self.hint_lbl, _pc_rect(50, 90, 760, 32))
        root.add_pc_widget(self.msg_lbl, _pc_rect(50, 130, 760, 36))
        root.add_pc_widget(self.button_refresh, _pc_rect(60, 400, 140, 44))
        root.add_pc_widget(self.button_create, _pc_rect(240, 400, 140, 44))
        root.add_pc_widget(self.button_leave, _pc_rect(420, 400, 140, 44))

        for idx in range(6):
            btn = _pc_button("", font_size=19)
            btn.opacity = 0
            btn.disabled = True
            btn.background_color = _pc_color((50, 60, 90))
            btn.color = _pc_color((230, 230, 240))
            btn.bind(on_press=partial(self._on_room_button_press, idx))
            root.add_pc_widget(btn, _pc_rect(60, 180 + idx * 58, VIRTUAL_W - 120, 48))
            self._room_buttons.append(btn)

        # Waiting overlay
        self.overlay = FloatLayout(size_hint=(1, 1), opacity=0)
        with self.overlay.canvas.before:
            Color(0, 0, 0, 0.55)
            self._overlay_rect = Rectangle(pos=(0, 0), size=(100, 100))
        self.overlay.bind(size=self._resize_overlay, pos=self._resize_overlay)

        ov_box = PcLayout(bg=(0, 0, 0))
        ov_box.canvas.before.clear()
        ov_box.size_hint = (1, 1)
        self.overlay_msg = _pc_label(
            text="",
            font_size=22,
            color=(255, 255, 255),
            halign="center",
        )
        self.button_cancel = _pc_button("取消等待", font_size=20)
        self.button_cancel.bind(on_press=lambda *_: self.cancel_waiting())
        ov_box.add_pc_widget(self.overlay_msg, _pc_rect(80, 205, 692, 44))
        ov_box.add_pc_widget(self.button_cancel, _pc_rect(336, 280, 180, 48))
        self.overlay.add_widget(ov_box)

        root.add_widget(self.overlay)
        self.add_widget(root)

    def _resize_overlay(self, *args):
        self._overlay_rect.pos = self.overlay.pos
        self._overlay_rect.size = self.overlay.size

    def attach(self, network: Any, username: str):
        self.network = network
        self.username = username
        self.title_lbl.text = f"欢迎，{username}"
        self.message = "加载房间列表..."
        self.msg_lbl.text = self.message
        self.waiting = False
        self.overlay.opacity = 0
        self._refresh_ms = 0.0
        self.request_rooms()

    def on_enter(self):
        if self._poll_ev is None:
            self._poll_ev = Clock.schedule_interval(self._poll_network, 0.5)
        # Always refetch list data when the lobby is shown (matches server waiting-only snapshot).
        if self.network:
            self.network.request_room_list()
            self._refresh_ms = 0.0

    def on_leave(self):
        if self._poll_ev is not None:
            self._poll_ev.cancel()
            self._poll_ev = None

    def _poll_network(self, dt: float):
        if not self.network:
            return
        self._refresh_ms += dt * 1000.0
        if (
            not self.waiting
            and self._refresh_ms >= REFRESH_INTERVAL_MS
        ):
            self.network.request_room_list()
            self._refresh_ms = 0.0

        for message in self.network.poll():
            self._handle_network(message)

    def _handle_network(self, message: Dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type == "rooms":
            self.rooms = message.get("rooms", [])
            self.message = f"当前可加入房间：{len(self.rooms)} 个"
            self.msg_lbl.text = self.message
            self._refresh_ms = 0.0
            self._rebuild_room_buttons()
        elif msg_type == "room_created":
            self.waiting = True
            self.waiting_room_id = message.get("room_id")
            self.message = f"房间 {self.waiting_room_id} 已创建，等待另一名玩家..."
            self._sync_waiting_ui()
        elif msg_type == "room_joined":
            self.waiting = True
            self.waiting_room_id = message.get("room_id")
            self.message = f"已进入房间 {self.waiting_room_id}，等待另一名玩家..."
            self._sync_waiting_ui()
        elif msg_type == "room_waiting":
            players = ", ".join(message.get("players", []))
            self.message = f"玩家列表：{players}，等待中..."
            self._sync_waiting_ui()
        elif msg_type == "room_ready":
            game = self.manager.get_screen("game")
            game.room_ready_message = message
            self.waiting = False
            self.waiting_room_id = None
            self.overlay.opacity = 0
            # Players keep client.room_id set, so the server does not include them in
            # broadcast_rooms_to_lobby — joiners never get a fresh rooms snapshot here.
            # Clear stale list so the room they joined does not stay visible until next fetch.
            self.rooms = []
            self._rebuild_room_buttons()
            self.message = "对局中…"
            self.msg_lbl.text = self.message
            self.manager.current = "game"
        elif msg_type == "room_peer_left":
            self.waiting = False
            self.waiting_room_id = None
            self.message = "对方离开了房间。"
            self.msg_lbl.text = self.message
            self.overlay.opacity = 0
            if self.network:
                self.network.request_room_list()
        elif msg_type == "error":
            self.message = message.get("message", "发生错误")
            self.msg_lbl.text = self.message
            self.waiting = False
            self.waiting_room_id = None
            self.overlay.opacity = 0
            if self.network:
                self.network.request_room_list()

    def _sync_waiting_ui(self):
        self.msg_lbl.text = self.message
        self.overlay_msg.text = self.message or "等待另一名玩家..."
        self.overlay.opacity = 1 if self.waiting else 0

    def request_rooms(self):
        if self.waiting or not self.network:
            return
        self.message = "刷新房间列表中..."
        self.msg_lbl.text = self.message
        self.network.request_room_list()

    def create_room(self):
        if self.waiting or not self.network:
            return
        self.waiting = True
        self.message = "正在创建房间..."
        self._sync_waiting_ui()
        self.network.request_create_room()

    def cancel_waiting(self):
        if not self.waiting:
            return
        try:
            if self.network:
                self.network.send_message({"type": "leave_room"})
        except Exception:
            pass
        self.waiting = False
        self.waiting_room_id = None
        self.message = "已取消等待"
        self.msg_lbl.text = self.message
        self.overlay.opacity = 0
        if self.network:
            self.network.request_room_list()

    def exit_to_login(self):
        try:
            if self.network:
                self.network.send_message({"type": "leave_room"})
        except Exception:
            pass
        try:
            if self.network:
                self.network.close()
        except Exception:
            pass
        self.network = None
        login = self.manager.get_screen("login")
        login.network = None
        login.status.text = ""
        self.manager.current = "login"

    def _rebuild_room_buttons(self):
        for idx, btn in enumerate(self._room_buttons):
            if idx >= len(self.rooms[:6]):
                btn.text = ""
                btn.opacity = 0
                btn.disabled = True
                continue
            room = self.rooms[idx]
            rid = room.get("room_id", "?")
            players = ", ".join(room.get("players", [])) or "(空)"
            btn.text = f"房间 {rid} | 玩家: {players}"
            btn.opacity = 1
            btn.disabled = False

    def _on_room_button_press(self, idx: int, *_):
        if idx >= len(self.rooms):
            return
        self._on_room_press(str(self.rooms[idx].get("room_id", "")))

    def _on_room_press(self, room_id: str, *_):
        if self.waiting or not self.network:
            return
        self.waiting = True
        self.message = f"正在加入房间 {room_id}..."
        self._sync_waiting_ui()
        self.network.request_join_room(room_id)


class GameScreen(Screen):
    """Game shell: GameView + end-of-round summary overlay."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.room_ready_message: Optional[Dict[str, Any]] = None
        self._game_view: Optional[GameView] = None

        self._root = FloatLayout()
        self.add_widget(self._root)

        self._summary_layer = FloatLayout(size_hint=(1, 1), opacity=0)
        with self._summary_layer.canvas.before:
            Color(0, 0, 0, 0.72)
            self._sum_rect = Rectangle(pos=(0, 0), size=(100, 100))
        self._summary_layer.bind(pos=self._resize_summary_bg, size=self._resize_summary_bg)

        summary_anchor = AnchorLayout()
        box = BoxLayout(
            orientation="vertical",
            spacing=dp(14),
            padding=dp(24),
            size_hint=(0.88, None),
        )
        box.bind(minimum_height=box.setter("height"))

        self._sum_title = Label(
            text="",
            font_size="34sp",
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height=dp(40),
            halign="center",
            **text_font_kwargs(),
        )
        self._sum_winner = Label(
            text="",
            font_size="18sp",
            color=(0.75, 1.0, 0.78, 1),
            size_hint_y=None,
            height=dp(36),
            halign="center",
            text_size=(None, None),
            **text_font_kwargs(),
        )
        self._sum_loser = Label(
            text="",
            font_size="18sp",
            color=(1.0, 0.78, 0.72, 1),
            size_hint_y=None,
            height=dp(36),
            halign="center",
            text_size=(None, None),
            **text_font_kwargs(),
        )
        btn_wait = Button(text="返回大厅", size_hint_y=None, height=dp(48), **text_font_kwargs())
        btn_wait.bind(on_press=self._on_summary_back_to_lobby)

        box.add_widget(self._sum_title)
        box.add_widget(self._sum_winner)
        box.add_widget(self._sum_loser)
        box.add_widget(btn_wait)
        summary_anchor.add_widget(box)
        self._summary_layer.add_widget(summary_anchor)
        self._root.add_widget(self._summary_layer)

    def _resize_summary_bg(self, *_args):
        self._sum_rect.pos = self._summary_layer.pos
        self._sum_rect.size = self._summary_layer.size

    def _on_match_finished(self, payload: Dict[str, Any]) -> None:
        self._show_match_summary(payload)

    def _show_match_summary(self, payload: Dict[str, Any]) -> None:
        lobby = self.manager.get_screen("lobby")
        my_name = (getattr(lobby, "username", None) or "").strip()
        wn = payload.get("winner")
        ls = payload.get("loser")

        winner = wn if isinstance(wn, str) and wn else "玩家"
        if my_name and winner == my_name:
            winner = f"{winner}（你）"
        self._sum_title.text = f"{winner} 获胜！"
        self._sum_winner.text = ""
        self._sum_loser.text = ""
        self._summary_layer.disabled = False
        self._summary_layer.opacity = 1
        # Always stack above GameView (last child draws on top in FloatLayout).
        if self._summary_layer.parent == self._root:
            self._root.remove_widget(self._summary_layer)
            self._root.add_widget(self._summary_layer)

    def _on_summary_back_to_lobby(self, *_args):
        self._summary_layer.opacity = 0
        lobby = self.manager.get_screen("lobby")
        lobby.waiting = False
        lobby.waiting_room_id = None
        lobby.overlay.opacity = 0
        lobby.message = "请选择房间加入，或创建房间等待对手。"
        lobby.msg_lbl.text = lobby.message
        if lobby.network:
            # Leave the match room on the server; otherwise we stay seated and the
            # room can still appear joinable (e.g. 1 player left after opponent left).
            try:
                lobby.network.send_message({"type": "leave_room"})
            except Exception:
                pass
            lobby.network.request_room_list()
        sm = self.manager
        t_prev = sm.transition
        sm.transition = NoTransition()
        sm.current = "lobby"
        sm.transition = t_prev

    def on_enter(self):
        self._summary_layer.opacity = 0
        if self._game_view is None:
            self._game_view = GameView()
            self._root.add_widget(self._game_view, index=0)
        # Bind before configure_online / first tick so death → settlement always has a callback.
        self._game_view.match_end_callback = self._on_match_finished
        lobby = self.manager.get_screen("lobby")
        net = getattr(lobby, "network", None)
        uname = getattr(lobby, "username", "") or ""
        if self.room_ready_message and net:
            self._game_view.configure_online(net, uname, self.room_ready_message)
        else:
            self._game_view._reload_level_from_disk()
            self._game_view.configure_offline()
        self._game_view.set_local_username(uname)
        self._game_view.bind_keyboard()
        self._game_view.start_tick()

    def on_leave(self):
        if self._game_view is not None:
            self._game_view.stop_tick()
            self._game_view.unbind_keyboard()
            self._game_view.configure_offline()



def build_screen_manager() -> ScreenManager:
    sm = ScreenManager()
    sm.add_widget(LoginScreen(name="login"))
    sm.add_widget(LobbyScreen(name="lobby"))
    sm.add_widget(GameScreen(name="game"))
    return sm
