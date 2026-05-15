from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from kivy.clock import Clock
from kivy.core.window import Keyboard, Window
from kivy.graphics import Color, Ellipse, Line, PopMatrix, PushMatrix, Rectangle, Scale, Translate
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from .font_config import get_ui_font_name, text_font_kwargs
from .input import TouchControls
from .level import TILE, Level
from .mario import Mario
from .sky_drops import DropSystem
from .multiplayer import (
    build_remote_peers,
    build_udp_username_map,
    collect_tcp_state_kivy,
    collect_udp_state_kivy,
    compute_spawn_xy,
)
from .projectiles import ProjectileSystem
from .remote_peer import RemotePeer
from .sprites_loader import SpriteRepository, animated_frame_for, mario_pick_frame_name
from .effects import BrickDebrisSystem

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from client.viewport import (  # noqa: E402
    VIRTUAL_H as _GAME_VIRTUAL_H,
    VIRTUAL_W as _GAME_VIRTUAL_W,
    compute_virtual_framebuffer,
)
from client.network.protocol import (
    ACTION_FIRE,
    MSG_PLAYER_STATE,
    MSG_PROJECTILE_STATE,
)


def _world_to_kivy_y(screen_h: float, y_top: float, tex_h: float) -> float:
    return screen_h - y_top - tex_h


class _PassthroughLabel(Label):
    """HUD label that does not steal touches from the virtual joystick / controls."""

    def on_touch_down(self, touch):
        return False

    def on_touch_move(self, touch):
        return False

    def on_touch_up(self, touch):
        return False


class GameView(Widget):
    CLIENT_ROOT = Path(__file__).resolve().parents[1] / "client"
    VIRTUAL_W = _GAME_VIRTUAL_W
    VIRTUAL_H = _GAME_VIRTUAL_H
    # Pygame client uses clock.tick(60); physics must advance at 60 Hz even when
    # the device renders at 30/120 Hz (otherwise Mario, drops, mushrooms feel slow).
    PHYSICS_DT = 1.0 / 60.0
    MAX_PHYSICS_STEPS = 8
    VIRTUAL_MIN_ASPECT = VIRTUAL_W / VIRTUAL_H
    # Pit / fall-off death: match pygame `client/main.py` (`fall_threshold`, rect.bottom).
    # Do not compare rect.y (sprite top) — that mis-detects vertical position vs “fell through bottom”.
    FALL_DEATH_BOTTOM_PX = 440.0
    DEATH_POSE_SECONDS = 1.0
    DEATH_FALL_SPEED = 280.0  # world px/sec downward
    DEATH_FALL_STOP_Y = 720.0  # world y below visible — slide off screen

    HUD_BAR_H = 34.0
    HUD_PAD_X = 12.0
    MARIO_MAX_HP = 30
    HUD_HP_BAR_W = 120.0
    HUD_HP_BAR_H = 16.0
    HUD_HP_GAP_AFTER = 16.0
    HUD_HP_TAG_GAP = 6.0
    # Horizontal spacing between coin and mushroom icon columns (virtual px).
    HUD_COIN_MUSH_ICON_GAP = 130.0
    # Text drawn to the right of each icon column (see `_draw_hud_strip`).
    HUD_COUNT_TEXT_AFTER_ICON = 28.0
    # Larger = slower coin spin (game ticks per sprite frame at ~60Hz).
    COIN_ANIM_TICK_STRIDE = 10
    DEBUG_DRAW_GAME_CAMERA_POSITION = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.controls = TouchControls()
        self.sprite_repo = SpriteRepository(self.CLIENT_ROOT)
        self.sprite_repo.load_all()

        self._level_path = self.CLIENT_ROOT / "levels" / "Level1-1.json"
        self.level = Level.from_json(self._level_path)
        self.mario = Mario(2, 10, self.level)
        self.projectiles = ProjectileSystem()
        self.effects = BrickDebrisSystem()
        self.drops = DropSystem()
        self.camera_x = 0.0
        self._physics_accum = 0.0
        self._tick_i = 0
        self._virtual_w = float(self.VIRTUAL_W)
        self._view_scale = 1.0
        self._view_offset = (0.0, 0.0)

        self._online = False
        self._net: Optional[Any] = None
        self._username = ""
        self._remotes: Dict[str, RemotePeer] = {}
        self._udp_username_map: Dict[int, str] = {}
        self._local_udp_id: Optional[int] = None
        self._last_tcp_sync = 0.0

        self._fall_reported = False
        self._game_over_payload: Optional[Dict[str, Any]] = None
        self._overlay_lbl: Optional[Label] = None

        self.match_end_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._death_phase: Optional[str] = None  # "pose" | "fall"
        self._death_pose_remaining = 0.0
        self._frozen_camera_x: Optional[float] = None
        self._match_end_fired = False

        self._coord_lbl = _PassthroughLabel(
            text="",
            font_size="13sp",
            color=(1.0, 0.95, 0.35, 1.0),
            size_hint=(None, None),
            halign="center",
            valign="bottom",
            shorten=False,
            **text_font_kwargs(),
        )
        self._coord_lbl.opacity = 0.0
        self.add_widget(self._coord_lbl)

        self._name_lbl = _PassthroughLabel(
            text="",
            font_size="14sp",
            color=(1.0, 1.0, 1.0, 1.0),
            size_hint=(None, None),
            halign="center",
            valign="bottom",
            shorten=False,
            **text_font_kwargs(),
        )
        self.add_widget(self._name_lbl)

        self._pos_corner_lbl = _PassthroughLabel(
            text="",
            font_size="14sp",
            color=(0.0, 0.0, 0.0, 1.0),
            size_hint=(None, None),
            halign="left",
            valign="middle",
            shorten=False,
            **text_font_kwargs(),
        )
        self.add_widget(self._pos_corner_lbl)
        self._pos_corner_lbl.opacity = 0.0

        self._remote_name_lbls: Dict[str, _PassthroughLabel] = {}

        # Desktop keyboard (Window.bind from GameScreen.on_enter / on_leave).
        self._keyboard_bound = False
        self._kb_left = False
        self._kb_right = False
        self._kb_jump = False
        self._kb_fire = False

        self.bind(size=self._on_size)
        # interval=0: callback every frame; real dt is fed into a 60 Hz fixed timestep.
        Clock.schedule_interval(self._tick, 0)

    def on_touch_down(self, touch):
        vx, vy = self._to_virtual(touch.x, touch.y)
        # Create a lightweight touch-like object with virtual coords for controls.
        touch_v = type("TouchV", (), {})()
        touch_v.x = vx
        touch_v.y = vy
        touch_v.uid = touch.uid
        return self.controls.on_touch_down(touch_v, self._virtual_w, self.VIRTUAL_H) or super().on_touch_down(touch)

    def on_touch_move(self, touch):
        vx, vy = self._to_virtual(touch.x, touch.y)
        touch_v = type("TouchV", (), {})()
        touch_v.x = vx
        touch_v.y = vy
        touch_v.uid = touch.uid
        return self.controls.on_touch_move(touch_v) or super().on_touch_move(touch)

    def on_touch_up(self, touch):
        vx, vy = self._to_virtual(touch.x, touch.y)
        touch_v = type("TouchV", (), {})()
        touch_v.x = vx
        touch_v.y = vy
        touch_v.uid = touch.uid
        return self.controls.on_touch_up(touch_v) or super().on_touch_up(touch)

    def bind_keyboard(self) -> None:
        """Attach global key handlers (GameScreen.on_enter — avoids stealing keys from login)."""
        if self._keyboard_bound:
            return
        Window.bind(on_key_down=self._on_window_key_down, on_key_up=self._on_window_key_up)
        self._keyboard_bound = True

    def unbind_keyboard(self) -> None:
        """Detach global key handlers (GameScreen.on_leave)."""
        if not self._keyboard_bound:
            return
        Window.unbind(on_key_down=self._on_window_key_down, on_key_up=self._on_window_key_up)
        self._keyboard_bound = False
        self._kb_left = False
        self._kb_right = False
        self._kb_jump = False
        self._kb_fire = False

    @staticmethod
    def _keyboard_action(key: int, codepoint: str) -> Optional[str]:
        """Map key to control; None = ignore."""
        if codepoint:
            if codepoint == " ":
                return "fire"
            ch = codepoint.lower()
            if ch == "a":
                return "left"
            if ch == "d":
                return "right"
            if ch == "w":
                return "jump"
            if ch == "s":
                return "down"
            if ch in ("j", "k", "z", "x"):
                return "fire"
        try:
            kc = Keyboard.keycodes
            if key == kc["left"]:
                return "left"
            if key == kc["right"]:
                return "right"
            if key == kc["up"]:
                return "jump"
            if key == kc["down"]:
                return "down"
            for letter, act in (
                ("a", "left"),
                ("d", "right"),
                ("w", "jump"),
                ("s", "down"),
                ("j", "fire"),
                ("k", "fire"),
                ("z", "fire"),
                ("x", "fire"),
            ):
                lk = kc.get(letter)
                if lk is not None and key == lk:
                    return act
        except KeyError:
            pass
        if key == 32:
            return "fire"
        return None

    def _set_kb_control(self, action: str, down: bool) -> None:
        if action == "left":
            self._kb_left = down
        elif action == "right":
            self._kb_right = down
        elif action == "jump":
            self._kb_jump = down
        elif action == "fire":
            self._kb_fire = down

    def _on_window_key_down(self, window, key: int, scancode: int, codepoint: str, modifiers):
        act = self._keyboard_action(key, codepoint or "")
        if act:
            self._set_kb_control(act, True)

    def _on_window_key_up(self, window, key: int, scancode: int):
        # SDL2 dispatches on_key_up with (key, scancode) only — no codepoint/modifiers.
        act = self._keyboard_action(key, "")
        if act:
            self._set_kb_control(act, False)

    def _reload_level_from_disk(self) -> None:
        """Fresh map each match (pygame `run_game` calls `loadLevel` on a new Level)."""
        self.level = Level.from_json(self._level_path)
        self.mario.level = self.level

    def configure_online(self, network: Any, username: str, room_ready: dict) -> None:
        """Spawn position, remotes, UDP map, enable UDP (matches pygame client flow)."""
        self._reload_level_from_disk()
        self.configure_offline()
        self._net = network
        self._username = (username or "").strip()
        self._remotes = build_remote_peers(
            room_ready, self._username, self.level.length_tiles, self._virtual_w
        )
        self._udp_username_map, self._local_udp_id = build_udp_username_map(room_ready, self._username)
        if self._local_udp_id is not None:
            self._udp_username_map[self._local_udp_id] = self._username

        spawn = room_ready.get("your_spawn", "left")
        sx, sy = compute_spawn_xy(str(spawn), self.level.length_tiles, self._virtual_w)
        self.mario.rect.x = sx
        self.mario.rect.y = sy
        self.mario.vel.x = 0.0
        self.mario.vel.y = 0.0

        udp_info = room_ready.get("udp")
        if isinstance(udp_info, dict) and self._net:
            token = str(udp_info.get("token", "") or "")
            cid = int(udp_info.get("client_id", 0) or 0)
            self._net.enable_udp(
                token=token,
                client_id=cid,
                port=udp_info.get("port"),
                host=udp_info.get("host"),
            )
        self._online = True
        self._last_tcp_sync = time.monotonic()
        self.drops.set_collision_callback(self._send_drop_collision)
        self._reset_round_state()
        self._ensure_remote_name_labels()

    def configure_offline(self) -> None:
        self._online = False
        self._net = None
        self.drops.set_collision_callback(None)
        self._remotes.clear()
        self._udp_username_map.clear()
        self._local_udp_id = None
        self._clear_remote_name_labels()
        self._reset_round_state()

    def set_local_username(self, name: str) -> None:
        """Login name shown above the local player (call when entering game from lobby)."""
        self._username = (name or "").strip()

    def _clear_remote_name_labels(self) -> None:
        for lbl in self._remote_name_lbls.values():
            self.remove_widget(lbl)
        self._remote_name_lbls.clear()

    def _ensure_remote_name_labels(self) -> None:
        self._clear_remote_name_labels()
        if not self._online:
            self._raise_corner_label_to_front()
            return
        for un in self._remotes:
            lbl = _PassthroughLabel(
                text=un,
                font_size="14sp",
                color=(0.82, 0.93, 1.0, 1.0),
                size_hint=(None, None),
                halign="center",
                valign="bottom",
                shorten=False,
                **text_font_kwargs(),
            )
            self._remote_name_lbls[un] = lbl
            self.add_widget(lbl)
        self._raise_corner_label_to_front()

    def _raise_corner_label_to_front(self) -> None:
        lbl = getattr(self, "_pos_corner_lbl", None)
        if lbl is None or lbl.parent != self:
            return
        self.remove_widget(lbl)
        self.add_widget(lbl)

    def _reset_round_state(self) -> None:
        self.mario.dead = False
        self.mario.hp = 30
        self.mario.coins = 0
        self.mario.mushrooms_eaten = 0
        self.drops.clear()
        self.projectiles.clear()
        self.effects.clear()
        self._physics_accum = 0.0
        self._fall_reported = False
        self._game_over_payload = None
        self._death_phase = None
        self._death_pose_remaining = 0.0
        self._frozen_camera_x = None
        self._match_end_fired = False
        self._match_cb_misses = 0
        self._sync_game_over_overlay()

    def _on_size(self, *_args):
        self._refit_overlay_text()
        self._layout_name_tags()
        self._layout_corner_position()
        self._raise_corner_label_to_front()

    def _layout_corner_position(self) -> None:
        """World (x, y) bottom-left of the game view (letterboxed), black text."""
        if self._pos_corner_lbl is None:
            return
        self._pos_corner_lbl.opacity = 0.0
        return
        self._compute_view_transform()
        mr = self.mario.rect
        self._pos_corner_lbl.text = f"({mr.x:.0f}, {mr.y:.0f})"
        tw, th = self._pos_corner_lbl.texture_size
        self._pos_corner_lbl.size = (max(tw, 1), max(th, 1))
        pad_x = 12.0
        pad_y = 12.0
        ox, oy = self._view_offset
        s = self._view_scale or 1.0
        self._pos_corner_lbl.pos = (ox + pad_x * s, oy + pad_y * s)

    def _local_mario_sprite_top_virtual(self, h: float) -> tuple[float, float]:
        """Sprite top for HUD; uses death sprite while dead."""
        mr = self.mario.rect
        if self.mario.dead:
            tup = self.sprite_repo.get_static("mario_dead", flip_x=(self.mario.heading < 0))
            th2 = mr.h
            if tup:
                th2 = tup[1][1]
            py = _world_to_kivy_y(h, mr.y, th2)
            top = py + th2
            cx = mr.centerx + self.camera_x
            return cx, top
        return self._sprite_top_virtual(
            h,
            mr.x,
            mr.y,
            mr.w,
            mr.h,
            self.mario.on_ground,
            self.mario.vel.x,
            self._tick_i,
            self.mario.heading,
        )

    def _begin_local_death_sequence(self) -> None:
        if self._death_phase is not None or self._match_end_fired:
            return
        self.mario.dead = True
        self.mario.hp = 0
        self.mario.vel.x = 0.0
        self.mario.vel.y = 0.0
        self._death_phase = "pose"
        self._death_pose_remaining = self.DEATH_POSE_SECONDS
        self._frozen_camera_x = self.camera_x

    def _update_death_animation(self, dt: float) -> None:
        if self._death_phase == "pose":
            self._death_pose_remaining -= dt
            if self._death_pose_remaining <= 0.0:
                self._death_phase = "fall"
        elif self._death_phase == "fall":
            if self.mario.rect.y >= self.DEATH_FALL_STOP_Y:
                self._finalize_local_death_sequence()
                return
            self.mario.rect.y += self.DEATH_FALL_SPEED * dt
            if self.mario.rect.y >= self.DEATH_FALL_STOP_Y:
                self._finalize_local_death_sequence()

    def _finalize_local_death_sequence(self) -> None:
        self._death_phase = None
        self._frozen_camera_x = None
        if not self._online:
            self._game_over_payload = {
                "winner": None,
                "loser": self._username or "player",
            }
        payload = dict(self._game_over_payload or {})
        if payload.get("winner") is None and self._online and self._username:
            for un in self._remotes:
                payload.setdefault("winner", un)
            payload.setdefault("loser", self._username)
        self._invoke_match_end(payload)

    def _invoke_match_end(self, payload: Optional[Dict[str, Any]] = None) -> None:
        """Show settlement UI via GameScreen; only sets _match_end_fired after callback exists."""
        if self._match_end_fired:
            return
        data = dict(payload or self._game_over_payload or {})
        cb = self.match_end_callback
        if cb is None:
            misses = getattr(self, "_match_cb_misses", 0) + 1
            self._match_cb_misses = misses
            if misses > 300:
                self._match_end_fired = True
                return
            Clock.schedule_once(lambda _dt: self._invoke_match_end(data), 0)
            return
        self._match_cb_misses = 0
        self._match_end_fired = True
        Clock.schedule_once(lambda _dt: cb(data), 0)

    def _sprite_top_virtual(
        self,
        h: float,
        rect_x: float,
        rect_y: float,
        rect_w: float,
        rect_h: float,
        on_ground: bool,
        vel_x: float,
        anim_tick: int,
        heading: int,
    ) -> tuple[float, float]:
        """(center_x, top_y) in virtual framebuffer coords; top_y is top edge of sprite in Kivy space."""
        big = rect_h >= 48
        fname = mario_pick_frame_name(on_ground, abs(vel_x), anim_tick, big=big)
        tup = self.sprite_repo.get_static(fname, flip_x=(heading < 0))
        th2 = rect_h
        if tup:
            th2 = tup[1][1]
        py = _world_to_kivy_y(h, rect_y, th2)
        top = py + th2
        cx = rect_x + rect_w * 0.5 + self.camera_x
        return cx, top

    def _layout_name_tags(self) -> None:
        """Local login name + remote login names above character sprites."""
        h = float(self.VIRTUAL_H)
        s = self._view_scale or 1.0
        ox, oy = self._view_offset
        gap = 6.0

        cx, top = self._local_mario_sprite_top_virtual(h)
        win_cx = ox + cx * s
        stack_v = top + gap

        display = (self._username or "").strip()
        self._name_lbl.text = display
        self._name_lbl.opacity = 0.0
        nw, nh = self._name_lbl.texture_size
        self._name_lbl.size = (max(nw, 1), max(nh, 1))
        win_y_name = oy + stack_v * s
        self._name_lbl.pos = (win_cx - nw * 0.5, win_y_name)

        for un, rp in self._remotes.items():
            lbl = self._remote_name_lbls.get(un)
            if lbl is None:
                continue
            if not rp.visible:
                lbl.opacity = 0.0
                continue
            lbl.opacity = 1.0
            rcx, rtop = self._sprite_top_virtual(
                h,
                rp.x,
                rp.y,
                rp.w,
                rp.h,
                rp.on_ground,
                rp.vx,
                rp.anim_tick,
                rp.heading,
            )
            rw, rh = lbl.texture_size
            lbl.size = (max(rw, 1), max(rh, 1))
            lbl.pos = (
                ox + rcx * s - rw * 0.5,
                oy + (rtop + gap) * s,
            )

    def _overlay_text(self) -> str:
        # Match result is shown on GameScreen summary panel instead.
        return ""

    def _refit_overlay_text(self) -> None:
        if self._overlay_lbl is None:
            return
        self._overlay_lbl.text_size = (max(1.0, self.width * 0.85), None)

    def _sync_game_over_overlay(self) -> None:
        text = self._overlay_text()
        if not text:
            if self._overlay_lbl is not None:
                self.remove_widget(self._overlay_lbl)
                self._overlay_lbl = None
            return
        if self._overlay_lbl is None:
            self._overlay_lbl = Label(
                text=text,
                font_size="32sp",
                color=(1, 1, 1, 1),
                halign="center",
                valign="middle",
                size_hint=(1, 1),
                **text_font_kwargs(),
            )
            self.add_widget(self._overlay_lbl)
        else:
            self._overlay_lbl.text = text
        self._refit_overlay_text()

    def _trigger_local_death(self, *, reason: str) -> None:
        if self._death_phase is not None or self._match_end_fired:
            return
        if self.mario.dead:
            return
        if reason == "fall" and self._online and self._net and not self._fall_reported:
            self._fall_reported = True
            self._net.send_message({"type": "player_fall", "loser": self._username})
        self._begin_local_death_sequence()

    def _send_drop_collision(self, drop_id: str, side: str) -> None:
        if self._net:
            self._net.send_drop_collision(drop_id, side)

    def _poll_tcp_messages(self) -> None:
        if not self._net:
            return
        for message in self._net.poll():
            self._handle_tcp_game_message(message)

    def _receive_udp(self) -> None:
        if not self._net:
            return
        for msg_type, event in self._net.poll_udp():
            if msg_type == MSG_PLAYER_STATE:
                sender_id = event.get("client_id")
                if sender_id is None or sender_id == self._local_udp_id:
                    continue
                uname = self._udp_username_map.get(int(sender_id))
                if not uname:
                    continue
                remote = self._remotes.get(uname)
                if not remote:
                    continue
                ps = event.get("player_state")
                if ps is None:
                    continue
                remote.apply_udp(ps, event.get("timestamp"))
            elif msg_type == MSG_PROJECTILE_STATE:
                state = event.get("projectile_state")
                if state is None:
                    continue
                sender_id = event.get("client_id")
                if sender_id is None:
                    continue
                owner_name = self._udp_username_map.get(int(sender_id))
                if owner_name is None:
                    continue
                proj_id = state.get("projectile_id")
                if proj_id is None:
                    continue
                proj_key = f"udp_{proj_id}"
                self.projectiles.upsert_from_udp(proj_key, owner_name, state, self.level)

    def _flush_udp_outbound(self) -> None:
        if not self._net:
            return
        self._net.send_udp_player_state(collect_udp_state_kivy(self.mario))
        now = time.monotonic()
        if now - self._last_tcp_sync >= 0.5:
            self._net.send_state(collect_tcp_state_kivy(self.mario))
            self._last_tcp_sync = now

    def _handle_tcp_game_message(self, message: dict) -> None:
        t = message.get("type")
        if t == "state_update":
            un = message.get("username")
            if not un or un == self._username:
                return
            rp = self._remotes.get(un)
            if rp:
                rp.apply_tcp_state(message.get("state") or {})
        elif t == "state_snapshot":
            for player in message.get("players", []) or []:
                un = player.get("username")
                if not un or un == self._username:
                    continue
                rp = self._remotes.get(un)
                if not rp:
                    continue
                cid = player.get("client_id")
                if isinstance(cid, int):
                    self._udp_username_map[cid] = un
                rp.apply_snapshot_player(player)
        elif t == "spawn_drop":
            self.drops.spawn_from_event(message, self.level)
        elif t == "drop_collected":
            drop_id = message.get("drop_id")
            if drop_id:
                self.drops.on_remote_collected(str(drop_id))
        elif t == "drop_direction":
            drop_id = message.get("drop_id")
            direction = message.get("direction")
            if drop_id is not None:
                self.drops.set_direction(str(drop_id), direction)
        elif t == "tile_break":
            tx, ty = message.get("x"), message.get("y")
            if isinstance(tx, int) and isinstance(ty, int):
                if self.level.break_tile(tx, ty, record_break=False):
                    bricks = self.sprite_repo.static.get("bricks")
                    if bricks:
                        btex, bwh = bricks
                        self.effects.spawn_brick_break(tx, ty, btex, bwh)
        elif t == "hp_update":
            hp = message.get("hp")
            if isinstance(hp, int):
                self.mario.hp = hp
                if hp <= 0:
                    self._trigger_local_death(reason="hp")
        elif t == "game_over":
            wn_raw = message.get("winner")
            ls_raw = message.get("loser")
            wn = (wn_raw or "").strip() if isinstance(wn_raw, str) else wn_raw
            ls = (ls_raw or "").strip() if isinstance(ls_raw, str) else ls_raw
            self._game_over_payload = {"winner": wn, "loser": ls}
            un = self._username
            if un and wn == un:
                self._invoke_match_end(dict(self._game_over_payload))
                return
            if un and ls == un:
                if self._death_phase is None and not self._match_end_fired:
                    self._begin_local_death_sequence()

    def _tick(self, dt: float) -> None:
        if self._online and self._net:
            self._poll_tcp_messages()

        if self._match_end_fired and self._death_phase is None:
            self._redraw()
            return

        if self._death_phase is not None:
            self._update_death_animation(dt)
            self._tick_i += 1
            if self._frozen_camera_x is not None:
                self.camera_x = self._frozen_camera_x
            self._redraw()
            return

        if self._online and self._net:
            self._receive_udp()

        joy = self.controls.joy
        move_dir = joy.move_dir
        if self._kb_left and not self._kb_right:
            move_dir = -1.0
        elif self._kb_right and not self._kb_left:
            move_dir = 1.0
        elif self._kb_left and self._kb_right:
            move_dir = 0.0
        jump = joy.jump or self._kb_jump
        fire = self.controls.fire_pressed or self._kb_fire
        self.mario.apply_controls(move_dir=move_dir, jump=jump, fire=fire)

        frame_dt = max(0.0, min(float(dt or self.PHYSICS_DT), 0.25))
        self._physics_accum = min(self._physics_accum + frame_dt, self.PHYSICS_DT * self.MAX_PHYSICS_STEPS)
        steps = 0
        while self._physics_accum >= self.PHYSICS_DT and steps < self.MAX_PHYSICS_STEPS:
            self._physics_accum -= self.PHYSICS_DT
            steps += 1
            self._physics_step()

        if self._death_phase is not None:
            self._redraw()
            return

        if self._online and self._net:
            self._flush_udp_outbound()

        target = -self.mario.rect.centerx + self._virtual_w * 0.5
        max_scroll = max(self.level.length_tiles * TILE - self._virtual_w, 0.0)
        self.camera_x = max(-max_scroll, min(0.0, target))

        self._redraw()

    def _physics_step(self) -> None:
        """One simulation tick at 60 Hz (matches pygame `clock.tick(60)`)."""
        self.mario.update()
        self._tick_i += 1

        n_coins, n_mush = self.drops.step(
            self.level,
            self.mario.rect,
            self._tick_i,
            net=self._net if self._online else None,
        )
        if n_coins:
            self.mario.coins += n_coins
            self.mario.hp = min(self.MARIO_MAX_HP, self.mario.hp + n_coins)
        if n_mush:
            self.mario.mushrooms_eaten += n_mush
            self.mario.hp = min(self.MARIO_MAX_HP, self.mario.hp + 5 * n_mush)

        if int(round(self.mario.rect.bottom)) > int(self.FALL_DEATH_BOTTOM_PX):
            self._trigger_local_death(reason="fall")
        elif self.mario.hp <= 0:
            self._trigger_local_death(reason="hp")
        if self._death_phase is not None:
            return

        if self.mario.consume_fire():
            direction = self.mario.heading or 1
            if self._online and self._net and self._local_udp_id is not None:
                self._net.send_udp_action(
                    ACTION_FIRE,
                    param=1 if direction >= 0 else 0,
                    client_id=self._local_udp_id,
                )
            else:
                self.projectiles.spawn_offline(
                    self.mario.rect.centerx + direction * 20,
                    self.mario.rect.centery - 10,
                    direction,
                    self.level,
                )

        level_w = max(float(self.level.length_tiles * TILE), self._virtual_w)
        projectile_sends = self.projectiles.step(
            self.level,
            level_w,
            online=bool(self._online),
            local_username=self._username,
            remotes=self._remotes,
        )
        if self._online and self._net and self._local_udp_id is not None:
            for pid, x, y, vx, vy, flags, hit_target in projectile_sends:
                self._net.send_udp_projectile(pid, x, y, vx, vy, flags, client_id=self._local_udp_id)
                if hit_target:
                    self._net.send_player_hit(hit_target, damage=5)

        self.projectiles.cull_hits_local_player(
            self.mario.rect,
            online=bool(self._online),
            local_username=self._username,
            mario_dead=self.mario.dead,
        )

        self.effects.update()

        broken = self.level.consume_broken_tiles()
        if broken:
            bricks = self.sprite_repo.static.get("bricks")
            if bricks:
                btex, bwh = bricks
                for tx, ty in broken:
                    self.effects.spawn_brick_break(tx, ty, btex, bwh)
            if self._online and self._net:
                for tx, ty in broken:
                    self._net.send_tile_break(tx, ty)

    def _compute_view_transform(self):
        w = float(self.width)
        h = float(self.height)
        if w <= 1 or h <= 1:
            self._virtual_w = float(self.VIRTUAL_W)
            self._view_scale = 1.0
            self._view_offset = (0.0, 0.0)
            return

        virtual_w, virtual_h = compute_virtual_framebuffer(w, h)
        aspect = w / h
        if aspect >= self.VIRTUAL_MIN_ASPECT:
            s = h / virtual_h
            ox = 0.0
            oy = (h - virtual_h * s) * 0.5
        else:
            s = w / virtual_w
            ox = (w - virtual_w * s) * 0.5
            oy = (h - virtual_h * s) * 0.5

        self._virtual_w = virtual_w
        self._view_scale = s
        self._view_offset = (ox, oy)

    def _to_virtual(self, x: float, y: float):
        """Map window coords -> virtual framebuffer coords."""
        s = self._view_scale or 1.0
        ox, oy = self._view_offset
        vx = (x - ox) / s
        vy = (y - oy) / s
        return vx, vy

    def _draw_tiled_sky(self, w: float, h: float):
        sky = self.sprite_repo.static.get("sky")
        if not sky:
            Color(0.42, 0.71, 1.0, 1.0)
            Rectangle(pos=(0, 0), size=(w, h))
            return
        tex, (sw, sh) = sky
        Color(1, 1, 1, 1)

        wx0 = math.floor(-self.camera_x / sw) * sw
        ix_span = max(8, int(w / sw) + 8)
        iy_span = max(8, int(h / sh) + 8)

        for iy in range(iy_span):
            for ix in range(-2, ix_span):
                wx = wx0 + ix * sw
                sx = wx + self.camera_x
                screen_y_bottom = iy * sh
                Rectangle(texture=tex, pos=(sx, screen_y_bottom), size=(sw, sh))

    def _draw_cell_tile(self, h: float, tx: int, ty: int, cell):
        sx = tx * TILE + self.camera_x
        y_top = ty * TILE
        # World Y is top-left based. Convert tile's top (y_top) to Kivy's bottom-left.
        # screen_bottom = screen_h - world_top - tile_height
        screen_y_bottom_tile = _world_to_kivy_y(h, y_top, TILE)

        if cell.sprite_key == "sky" and not cell.redraw_sky_below:
            return

        if cell.redraw_sky_below:
            sky = self.sprite_repo.static.get("sky")
            if sky:
                stex, _ = sky
                Color(1, 1, 1, 1)
                Rectangle(
                    texture=stex,
                    pos=(sx, screen_y_bottom_tile),
                    size=(TILE, TILE),
                )

        if cell.sprite_key == "CoinBox":
            ani = self.sprite_repo.animated.get("CoinBox")
            if ani and ani.frames:
                tex, (tw2, th2) = animated_frame_for(
                    ani, self._tick_i // self.COIN_ANIM_TICK_STRIDE
                )
                Color(1, 1, 1, 1)
                y_draw = screen_y_bottom_tile + (TILE - th2)
                Rectangle(
                    texture=tex,
                    pos=(sx + (TILE - tw2) / 2, y_draw),
                    size=(tw2, th2),
                )
            return

        if cell.sprite_key and cell.sprite_key != "sky":
            tup = self.sprite_repo.static.get(cell.sprite_key)
            if not tup:
                return
            tex, (tw2, th2) = tup
            Color(1, 1, 1, 1)
            y_draw = screen_y_bottom_tile + (TILE - th2)
            Rectangle(texture=tex, pos=(sx + (TILE - tw2) / 2, y_draw), size=(tw2, th2))

    def _redraw_sky_drops(self, h: float) -> None:
        """Server sky drops: falling coin/mushroom and landed pickups."""
        coin_ani = self.sprite_repo.animated.get("coin")
        coin_tex = coin_wh = None
        if coin_ani and coin_ani.frames:
            coin_tex, coin_wh = animated_frame_for(
                coin_ani, self._tick_i // self.COIN_ANIM_TICK_STRIDE
            )
        mush_tup = self.sprite_repo.get_static("mushroom")
        mush_tex = mush_wh = None
        if mush_tup:
            mush_tex, mush_wh = mush_tup

        Color(1, 1, 1, 1)
        for ent in self.drops.iter_visible():
            if ent.drop_type == "mushroom":
                if not mush_tex or not mush_wh:
                    continue
                tex, tw2, th2 = mush_tex, mush_wh[0], mush_wh[1]
            else:
                if not coin_tex or not coin_wh:
                    continue
                tex, tw2, th2 = coin_tex, coin_wh[0], coin_wh[1]
            px = ent.rect.x + self.camera_x
            py = _world_to_kivy_y(h, ent.rect.y, th2)
            Rectangle(texture=tex, pos=(px, py), size=(tw2, th2))

    def _hud_raster_text(self, text: str, font_size: float = 15.0):
        """Raster HUD strings onto canvas (same coords as HP strip); avoids Label widget stacking issues."""
        from kivy.core.text import Label as CoreLabel

        opts: Dict[str, Any] = {"text": text, "font_size": font_size, "color": (1, 1, 1, 1)}
        fn = get_ui_font_name()
        if fn:
            opts["font_name"] = fn
        core = CoreLabel(**opts)
        core.refresh()
        return core.texture

    def _draw_hud_text(self, text: str, x: float, y_top: float, size: float) -> None:
        tex = self._hud_raster_text(text, size)
        if not tex:
            return
        Color(1, 1, 1, 1)
        Rectangle(texture=tex, pos=(x, self.VIRTUAL_H - y_top - tex.height), size=tex.size)

    def _draw_pc_health_bar(self, x: float, y_top: float, width: float, height: float) -> None:
        y = self.VIRTUAL_H - y_top - height
        Color(40 / 255.0, 40 / 255.0, 40 / 255.0, 1)
        Rectangle(pos=(x, y), size=(width, height))
        Color(10 / 255.0, 10 / 255.0, 10 / 255.0, 1)
        Rectangle(pos=(x + 2, y + 2), size=(width - 4, height - 4))
        ratio = max(0.0, min(1.0, float(self.mario.hp) / float(self.MARIO_MAX_HP)))
        if ratio > 0:
            Color(220 / 255.0, 50 / 255.0, 40 / 255.0, 1)
            Rectangle(pos=(x + 2, y + 2), size=((width - 4) * ratio, height - 4))
        self._draw_hud_text("HP", x, y_top - 18, 14)
        self._draw_hud_text(f"{int(max(0, self.mario.hp)):02d}/{self.MARIO_MAX_HP:02d}", x + width + 12, y_top - 2, 12)

    def _draw_camera_debug_box(self, w: float, h: float) -> None:
        if not self.DEBUG_DRAW_GAME_CAMERA_POSITION:
            return
        cx, cy = w * 0.5, h * 0.5
        half = 10.0
        Color(0.0, 1.0, 200 / 255.0, 1.0)
        x0, y0 = cx - half, cy - half
        x1, y1 = cx + half, cy + half
        step = 8.0
        seg = 4.0
        x = x0
        while x < x1:
            Line(points=[x, y0, min(x + seg, x1), y0], width=2)
            Line(points=[x, y1, min(x + seg, x1), y1], width=2)
            x += step
        y = y0
        while y < y1:
            Line(points=[x0, y, x0, min(y + seg, y1)], width=2)
            Line(points=[x1, y, x1, min(y + seg, y1)], width=2)
            y += step

    def _draw_hud_strip(self, w: float, h: float) -> None:
        """Draw the pygame Dashboard-style HUD in the same virtual coordinates."""
        self._draw_hud_text("MARIO", 50, 20, 15)
        self._draw_hud_text("000000", 50, 37, 15)
        self._draw_hud_text(f"@x{int(self.mario.coins):02d}", 225, 37, 15)
        self._draw_hud_text("WORLD", 380, 20, 15)
        self._draw_hud_text("1-1", 395, 37, 15)
        self._draw_hud_text("TIME", 520, 20, 15)
        self._draw_hud_text(f"{int(self._tick_i // 60):03d}", 535, 37, 15)
        self._draw_pc_health_bar(48, 62, 200, 14)

    def _redraw_mario(self, h: float):
        mr = self.mario.rect
        if self.mario.dead:
            tup = self.sprite_repo.get_static("mario_dead", flip_x=(self.mario.heading < 0))
            if not tup:
                Color(1.0, 0.2, 0.2, 1.0)
                Rectangle(
                    pos=(mr.x + self.camera_x, _world_to_kivy_y(h, mr.y, mr.h)),
                    size=(mr.w, mr.h),
                )
                return
            tex, (tw2, th2) = tup
            px = mr.x + self.camera_x
            py = _world_to_kivy_y(h, mr.y, th2)
            Color(1, 1, 1, 1)
            Rectangle(texture=tex, pos=(px, py), size=(tw2, th2))
            return

        big_mario = mr.h >= 48
        fname = mario_pick_frame_name(
            self.mario.on_ground,
            abs(self.mario.vel.x),
            self._tick_i,
            big=big_mario,
        )
        tup = self.sprite_repo.get_static(fname, flip_x=(self.mario.heading < 0))
        if not tup:
            Color(1.0, 0.2, 0.2, 1.0)
            Rectangle(
                pos=(mr.x + self.camera_x, _world_to_kivy_y(h, mr.y, mr.h)),
                size=(mr.w, mr.h),
            )
            return

        tex, (tw2, th2) = tup
        px = mr.x + self.camera_x
        py = _world_to_kivy_y(h, mr.y, th2)

        Color(1, 1, 1, 1)
        Rectangle(texture=tex, pos=(px, py), size=(tw2, th2))

    def _redraw_remote_peers(self, h: float) -> None:
        if not self._online:
            return
        for rp in self._remotes.values():
            if not rp.visible:
                continue
            big_mario = rp.h >= 48
            fname = mario_pick_frame_name(
                rp.on_ground,
                abs(rp.vx),
                rp.anim_tick,
                big=big_mario,
            )
            tup = self.sprite_repo.get_static(fname, flip_x=(rp.heading < 0))
            if not tup:
                Color(0.2, 0.75, 1.0, 1.0)
                px = rp.x + self.camera_x
                py = _world_to_kivy_y(h, rp.y, rp.h)
                Rectangle(pos=(px, py), size=(rp.w, rp.h))
                continue
            tex, (tw2, th2) = tup
            px = rp.x + self.camera_x
            py = _world_to_kivy_y(h, rp.y, th2)
            Color(1, 1, 1, 1)
            Rectangle(texture=tex, pos=(px, py), size=(tw2, th2))

    def _redraw_fireballs(self, h: float):
        for fb in self.projectiles.by_key.values():
            r = fb.rect
            px = r.x + self.camera_x
            py = _world_to_kivy_y(h, r.y, r.h)
            Color(1.0, 0.55, 0.1, 0.92)
            Ellipse(pos=(px + 2, py + 2), size=(r.w - 4, r.h - 4))
            Color(1.0, 0.92, 0.45, 0.82)
            Ellipse(pos=(px + 5, py + 5), size=(r.w - 10, r.h - 10))

    def _redraw(self):
        self.canvas.clear()
        self._compute_view_transform()
        w = float(self._virtual_w)
        h = float(self.VIRTUAL_H)

        with self.canvas:
            # Letterbox background (window space)
            Color(0.0, 0.0, 0.0, 1.0)
            Rectangle(pos=(0, 0), size=(self.width, self.height))

            # Apply transform to draw the virtual framebuffer.
            PushMatrix()
            Translate(self._view_offset[0], self._view_offset[1])
            Scale(self._view_scale, self._view_scale, 1.0)

            self._draw_tiled_sky(w, h)

            tx0 = int((-self.camera_x) // TILE) - 2
            tx1 = int(((-self.camera_x) + w) // TILE) + 3

            # Only draw tiles that could intersect the current viewport vertically.
            # Without this, high-DPI window sizes may show far-below "underground" tiles.
            max_visible_ty = int(h // TILE) + 4
            for ty in range(min(len(self.level.tiles), max_visible_ty)):
                for tx in range(max(0, tx0), min(self.level.ncol, tx1)):
                    cell = self.level.tiles[ty][tx]
                    self._draw_cell_tile(h, tx, ty, cell)

            self._redraw_sky_drops(h)
            self._redraw_remote_peers(h)
            self._redraw_mario(h)
            self._redraw_fireballs(h)
            self.effects.draw(self.camera_x, self.VIRTUAL_H)

            self._draw_hud_strip(w, h)
            self._draw_camera_debug_box(w, h)

            PopMatrix()

        self._layout_name_tags()
        self._layout_corner_position()
        self._raise_corner_label_to_front()
