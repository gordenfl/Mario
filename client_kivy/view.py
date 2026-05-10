from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, PopMatrix, PushMatrix, Rectangle, Scale, Translate
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from .font_config import text_font_kwargs
from .input import TouchControls
from .level import TILE, Level
from .mario import Mario
from .multiplayer import (
    build_remote_peers,
    build_udp_username_map,
    collect_tcp_state_kivy,
    collect_udp_state_kivy,
    compute_spawn_xy,
)
from .projectiles import ProjectileSystem
from .remote_peer import RemotePeer
from .sprites_loader import SpriteRepository, mario_pick_frame_name
from .effects import BrickDebrisSystem

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from client.network.protocol import MSG_PLAYER_STATE


def _world_to_kivy_y(screen_h: float, y_top: float, tex_h: float) -> float:
    return screen_h - y_top - tex_h


class GameView(Widget):
    CLIENT_ROOT = Path(__file__).resolve().parents[1] / "client"
    VIRTUAL_W = 852.0
    VIRTUAL_H = 480.0
    # World Y (top-left origin): above this line counts as fall death → HP = 0.
    FALL_DEATH_Y = -10.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.controls = TouchControls()
        self.sprite_repo = SpriteRepository(self.CLIENT_ROOT)
        self.sprite_repo.load_all()

        self.level = Level.from_json(self.CLIENT_ROOT / "levels" / "Level1-1.json")
        self.mario = Mario(2, 10, self.level)
        self.projectiles = ProjectileSystem()
        self.effects = BrickDebrisSystem()
        self.camera_x = 0.0
        self._dt = 1.0 / 60.0
        self._tick_i = 0
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

        self.bind(size=self._on_size)
        Clock.schedule_interval(self._tick, self._dt)

    def on_touch_down(self, touch):
        vx, vy = self._to_virtual(touch.x, touch.y)
        # Create a lightweight touch-like object with virtual coords for controls.
        touch_v = type("TouchV", (), {})()
        touch_v.x = vx
        touch_v.y = vy
        touch_v.uid = touch.uid
        return self.controls.on_touch_down(touch_v, self.VIRTUAL_W, self.VIRTUAL_H) or super().on_touch_down(touch)

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

    def configure_online(self, network: Any, username: str, room_ready: dict) -> None:
        """Spawn position, remotes, UDP map, enable UDP (matches pygame client flow)."""
        self.configure_offline()
        self._net = network
        self._username = username or ""
        self._remotes = build_remote_peers(
            room_ready, self._username, self.level.length_tiles, self.VIRTUAL_W
        )
        self._udp_username_map, self._local_udp_id = build_udp_username_map(room_ready, self._username)
        if self._local_udp_id is not None:
            self._udp_username_map[self._local_udp_id] = self._username

        spawn = room_ready.get("your_spawn", "left")
        sx, sy = compute_spawn_xy(str(spawn), self.level.length_tiles, self.VIRTUAL_W)
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
        self._reset_round_state()

    def configure_offline(self) -> None:
        self._online = False
        self._net = None
        self._remotes.clear()
        self._udp_username_map.clear()
        self._local_udp_id = None
        self._reset_round_state()

    def _reset_round_state(self) -> None:
        self.mario.dead = False
        self.mario.hp = 30
        self._fall_reported = False
        self._game_over_payload = None
        self._sync_game_over_overlay()

    def _on_size(self, *_args):
        self._refit_overlay_text()

    def _overlay_text(self) -> str:
        if self.mario.dead and not self._game_over_payload and self._online:
            return "等待结算…"
        if not self._game_over_payload:
            return ""
        if not self._online:
            return "游戏结束"
        winner = self._game_over_payload.get("winner")
        loser = self._game_over_payload.get("loser")
        if winner and self._username and winner == self._username:
            return "你赢了！"
        if loser and self._username and loser == self._username:
            return "你输了"
        return "游戏结束"

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
        if self.mario.dead:
            return
        self.mario.dead = True
        self.mario.hp = 0
        self.mario.vel.x = 0.0
        self.mario.vel.y = 0.0
        if reason == "fall" and self._online and self._net and not self._fall_reported:
            self._fall_reported = True
            self._net.send_message({"type": "player_fall", "loser": self._username})
        if not self._online:
            self._game_over_payload = {"winner": None, "loser": self._username or "player"}
        self._sync_game_over_overlay()

    def _poll_multiplayer(self) -> None:
        if not self._net:
            return
        for msg_type, event in self._net.poll_udp():
            if msg_type != MSG_PLAYER_STATE:
                continue
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

        for message in self._net.poll():
            self._handle_tcp_game_message(message)

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
            self._game_over_payload = {
                "winner": message.get("winner"),
                "loser": message.get("loser"),
            }
            self.mario.dead = True
            self.mario.hp = 0
            self._sync_game_over_overlay()

    def _tick(self, _dt):
        if self._online and self._net:
            if self.mario.dead:
                for message in self._net.poll():
                    self._handle_tcp_game_message(message)
            else:
                self._poll_multiplayer()

        if self.mario.dead:
            self._redraw()
            return

        joy = self.controls.joy
        self.mario.apply_controls(move_dir=joy.move_dir, jump=joy.jump, fire=self.controls.fire_pressed)
        self.mario.update()
        self._tick_i += 1

        if self.mario.rect.y < self.FALL_DEATH_Y:
            self._trigger_local_death(reason="fall")
        elif self.mario.hp <= 0:
            self._trigger_local_death(reason="hp")

        if self.mario.dead:
            self._redraw()
            return

        if self.mario.consume_fire():
            direction = self.mario.heading or 1
            self.projectiles.spawn_fireball(
                self.mario.rect.centerx + direction * 20,
                self.mario.rect.centery - 10,
                direction,
            )
        self.projectiles.update(self.level)
        self.effects.update()

        # Brick break events -> debris (local only; remotes use TCP + record_break=False)
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

        # Camera is computed in *virtual* pixels, independent of window scaling.
        target = -self.mario.rect.centerx + self.VIRTUAL_W * 0.5
        max_scroll = max(self.level.length_tiles * TILE - self.VIRTUAL_W, 0.0)
        self.camera_x = max(-max_scroll, min(0.0, target))

        self._redraw()

    def _compute_view_transform(self):
        w = float(self.width)
        h = float(self.height)
        if w <= 1 or h <= 1:
            self._view_scale = 1.0
            self._view_offset = (0.0, 0.0)
            return
        s = min(w / self.VIRTUAL_W, h / self.VIRTUAL_H)
        ox = (w - self.VIRTUAL_W * s) * 0.5
        oy = (h - self.VIRTUAL_H * s) * 0.5
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

        if cell.sprite_key and cell.sprite_key != "sky":
            tup = self.sprite_repo.static.get(cell.sprite_key)
            if not tup:
                return
            tex, (tw2, th2) = tup
            Color(1, 1, 1, 1)
            y_draw = screen_y_bottom_tile + (TILE - th2)
            Rectangle(texture=tex, pos=(sx + (TILE - tw2) / 2, y_draw), size=(tw2, th2))

    def _redraw_mario(self, h: float):
        big_mario = self.mario.rect.h >= 48
        fname = mario_pick_frame_name(
            self.mario.on_ground,
            abs(self.mario.vel.x),
            self._tick_i,
            big=big_mario,
        )
        tup = self.sprite_repo.get_static(fname, flip_x=(self.mario.heading < 0))
        if not tup:
            Color(1.0, 0.2, 0.2, 1.0)
            mr = self.mario.rect
            Rectangle(
                pos=(mr.x + self.camera_x, _world_to_kivy_y(h, mr.y, mr.h)),
                size=(mr.w, mr.h),
            )
            return

        tex, (tw2, th2) = tup
        mr = self.mario.rect
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
        for fb in self.projectiles.fireballs:
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
        w = float(self.VIRTUAL_W)
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

            self._redraw_remote_peers(h)
            self._redraw_mario(h)
            self._redraw_fireballs(h)
            self.effects.draw(self.camera_x, self.VIRTUAL_H)

            if self.controls.joy.active:
                cx, cy = self.controls.joy.center
                kx, ky = self.controls.joy.knob
                Color(0.0, 0.0, 0.0, 0.18)
                Ellipse(pos=(cx - 48, cy - 48), size=(96, 96))
                Color(1.0, 1.0, 1.0, 0.18)
                Ellipse(pos=(kx - 28, ky - 28), size=(56, 56))

            PopMatrix()
