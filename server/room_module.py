"""Rooms, match lifecycle, world sync, and TCP gameplay messages."""

from __future__ import annotations

import asyncio
import logging
import math
import random
import uuid
from typing import Any, Dict, Optional, Tuple

import udp_protocol
from config import LEVEL_WIDTH_PIXELS
from interfaces import SessionPort
from models import (
    ROOM_PHASE_FIGHTING,
    ROOM_PHASE_WAITING,
    ClientSession,
    Room,
    UdpClientInfo,
)
from state import ServerState


class RoomModule:
    def __init__(self, state: ServerState, lock: asyncio.Lock, sessions: SessionPort):
        self._state = state
        self._lock = lock
        self._sessions = sessions

    async def _purge_room(self, room: Room, *, broadcast_lobby: bool) -> None:
        rid = room.room_id
        async with self._lock:
            if rid not in self._state.rooms:
                return
            self._state.rooms.pop(rid, None)
            task = self._state.room_drop_tasks.pop(rid, None)
            if task:
                task.cancel()
            snapshot_task = self._state.room_snapshot_tasks.pop(rid, None)
            if snapshot_task:
                snapshot_task.cancel()
            room.active_drops.clear()
            room.projectiles.clear()
            for info in list(room.udp_clients.values()):
                self._state.pending_udp_tokens.pop(info.token, None)
                if info.address:
                    self._state.udp_addr_map.pop(info.address, None)
                self._state.udp_index_map.pop((rid, info.client_index), None)
            room.udp_clients.clear()
            room.latest_states.clear()
            room.udp_client_index_map.clear()
            for m in list(room.members.values()):
                m.room_id = None
                m.udp_id = None
            room.members.clear()
        logging.info("Room %s purged from registry", rid)
        if broadcast_lobby:
            await self._sessions.broadcast_rooms_to_lobby()

    async def handle_create_room(self, client: ClientSession) -> None:
        async with self._lock:
            room_id = uuid.uuid4().hex[:6]
            while room_id in self._state.rooms:
                room_id = uuid.uuid4().hex[:6]
            room = Room(room_id)
            room.add_member(client)
            self._state.rooms[room_id] = room
        logging.info("Room %s created by %s", room_id, client.username)
        await self._sessions.send(client, {"type": "room_created", "room_id": room_id})
        async with self._lock:
            if room_id not in self._state.room_drop_tasks:
                self._state.room_drop_tasks[room_id] = asyncio.create_task(self._room_drop_loop(room_id))

    async def handle_join_room(self, client: ClientSession, message: Dict[str, Any]) -> None:
        room_id = message.get("room_id")
        if not room_id:
            await self._sessions.send_error(client, "invalid_room", "Room id required")
            return
        reject: Optional[Tuple[str, str]] = None
        async with self._lock:
            room = self._state.rooms.get(room_id)
            if not room:
                reject = ("invalid_room", "Room does not exist")
            elif room.phase != ROOM_PHASE_WAITING:
                reject = ("invalid_room", "Room is not open for joining")
            elif room.is_full():
                reject = ("room_full", "Room is full")
            else:
                room.add_member(client)
        if reject:
            code, errmsg = reject
            await self._sessions.send_error(client, code, errmsg)
            return
        logging.info("%s joined room %s", client.username, room_id)
        await self._sessions.send(client, {"type": "room_joined", "room_id": room_id})
        await self.notify_room_ready(room)

    async def notify_room_ready(self, room: Room) -> None:
        if not room.is_full():
            room.phase = ROOM_PHASE_WAITING
            for member in room.members.values():
                await self._sessions.send(
                    member,
                    {
                        "type": "room_waiting",
                        "room_id": room.room_id,
                        "players": [m.username for m in room.members.values()],
                    },
                )
            return
        for info in room.udp_clients.values():
            self._state.pending_udp_tokens.pop(info.token, None)
            if info.address:
                self._state.udp_addr_map.pop(info.address, None)
            self._state.udp_index_map.pop((room.room_id, info.client_index), None)
        room.udp_clients.clear()
        room.udp_client_index_map.clear()
        room.latest_states.clear()
        room.projectiles.clear()
        room.broken_tiles.clear()
        room.collected_floating_coins.clear()
        room.game_over = False
        room.result = None
        for member in room.members.values():
            member.hp = 30
        spawn_slots = ["left", "right"]
        spawn_map: Dict[str, str] = {}
        members_ordered = list(room.members.values())
        for member, slot in zip(members_ordered, spawn_slots):
            spawn_map[member.id] = slot
        udp_host = None if self._state.host in ("0.0.0.0", "::", "") else self._state.host
        for index, member in enumerate(members_ordered):
            member.udp_id = index
            token = uuid.uuid4().hex
            info = UdpClientInfo(token=token, client_index=index)
            room.udp_clients[member.id] = info
            room.udp_client_index_map[index] = member.id
            self._state.pending_udp_tokens[token] = (room.room_id, member.id, index)
        players = [
            {
                "username": member.username,
                "hp": member.hp,
                "spawn": spawn_map.get(member.id, "left"),
                "client_id": member.udp_id,
            }
            for member in members_ordered
        ]
        for member in members_ordered:
            udp_info = room.udp_clients.get(member.id)
            await self._sessions.send(
                member,
                {
                    "type": "room_ready",
                    "room_id": room.room_id,
                    "players": players,
                    "your_spawn": spawn_map.get(member.id, "left"),
                    "udp": {
                        "port": self._state.udp_port,
                        "token": udp_info.token if udp_info else "",
                        "client_id": udp_info.client_index if udp_info else 0,
                        "host": udp_host,
                    },
                },
            )
        room.phase = ROOM_PHASE_FIGHTING
        if room.room_id in self._state.room_snapshot_tasks:
            task = self._state.room_snapshot_tasks.pop(room.room_id)
            task.cancel()
        self._state.room_snapshot_tasks[room.room_id] = asyncio.create_task(
            self._room_snapshot_loop(room.room_id)
        )
        await self._sessions.broadcast_rooms_to_lobby()

    async def handle_leave_room(self, client: ClientSession) -> None:
        if not client.room_id:
            return
        try:
            await self._handle_leave_room_body(client)
        finally:
            await self._sessions.broadcast_rooms_to_lobby()

    async def _handle_leave_room_body(self, client: ClientSession) -> None:
        async with self._lock:
            room = self._state.rooms.get(client.room_id)
            if room:
                room.remove_member(client.id)
                should_delete = room.is_empty()
                info = room.udp_clients.pop(client.id, None)
                if info:
                    self._state.pending_udp_tokens.pop(info.token, None)
                    if info.address:
                        self._state.udp_addr_map.pop(info.address, None)
                    self._state.udp_index_map.pop((room.room_id, info.client_index), None)
                    room.latest_states.pop(client.id, None)
                    room.udp_client_index_map.pop(info.client_index, None)
            else:
                should_delete = False
            client.room_id = None
            client.udp_id = None
        if room and room.room_id in self._state.room_drop_tasks and room.is_empty():
            task = self._state.room_drop_tasks.pop(room.room_id)
            task.cancel()
            room.active_drops.clear()
        if room and room.is_empty():
            snapshot_task = self._state.room_snapshot_tasks.pop(room.room_id, None)
            if snapshot_task:
                snapshot_task.cancel()
            room.projectiles.clear()
        if room and not should_delete:
            if room.game_over:
                logging.info("%s left room %s after game over", client.username, room.room_id)
                return
            logging.info("%s left room %s, declaring opponent winner", client.username, room.room_id)
            winner_name = None
            for member in room.members.values():
                if member.username != client.username:
                    winner_name = member.username
                    break
            if not winner_name and room.members:
                winner_name = next(iter(room.members.values())).username
            if winner_name:
                await self._broadcast_game_over(room, winner_name, client.username)
        if room and should_delete:
            await self._purge_room(room, broadcast_lobby=False)
        logging.info("%s left room %s", client.username, room.room_id if room else "<unknown>")

    async def handle_state_update(self, client: ClientSession, message: Dict[str, Any]) -> None:
        if not client.room_id:
            return
        state_payload = message.get("state", {}) or {}
        position = state_payload.get("position", [0, 0])
        velocity = state_payload.get("velocity", [0, 0])
        try:
            x, y = position
        except (TypeError, ValueError):
            x, y = 0, 0
        try:
            vx, vy = velocity
        except (TypeError, ValueError):
            vx, vy = 0.0, 0.0
        async with self._lock:
            room = self._state.rooms.get(client.room_id)
            if room:
                room.latest_states[client.id] = {
                    "x": x,
                    "y": y,
                    "vx": vx,
                    "vy": vy,
                    "flags": state_payload.get("flags", 0),
                    "heading": state_payload.get("heading", 0),
                    "timestamp": udp_protocol.current_millis(),
                }
        payload = {
            "type": "state_update",
            "username": client.username,
            "state": state_payload,
        }
        await self.forward_to_room(client, payload)

    async def handle_player_hit(self, client: ClientSession, message: Dict[str, Any]) -> None:
        if not client.room_id:
            return
        target = message.get("target")
        damage = message.get("damage", 1)
        defeated_member: Optional[ClientSession] = None
        room: Optional[Room] = None
        async with self._lock:
            room = self._state.rooms.get(client.room_id)
            if not room:
                return
            if room.game_over:
                return
            for member in room.members.values():
                if member.username == target:
                    member.hp = max(0, member.hp - damage)
                    await self._sessions.send(
                        member,
                        {
                            "type": "hp_update",
                            "hp": member.hp,
                        },
                    )
                    if member.hp == 0:
                        defeated_member = member
                    break
        payload = {
            "type": "player_hit",
            "source": client.username,
            "target": target,
            "damage": damage,
        }
        await self.forward_to_room(client, payload)
        if defeated_member and room:
            await self._broadcast_game_over(room, client.username, defeated_member.username)

    async def handle_player_fall(self, client: ClientSession, message: Dict[str, Any]) -> None:
        if not client.room_id:
            return
        async with self._lock:
            room = self._state.rooms.get(client.room_id)
            if not room:
                return
            if room.game_over:
                return
            loser_name = message.get("loser") or client.username
            logging.info("Player %s reported fall in room %s", loser_name, client.room_id)
            winner_name = None
            for member in room.members.values():
                if member.username == loser_name:
                    member.hp = 0
                else:
                    winner_name = member.username
            if not winner_name:
                winner_name = client.username if client.username != loser_name else loser_name
        await self._broadcast_game_over(room, winner_name, loser_name)
        logging.info("Room %s game over: winner=%s loser=%s", room.room_id, winner_name, loser_name)

    async def handle_drop_collected(self, client: ClientSession, message: Dict[str, Any]) -> None:
        drop_id = message.get("drop_id")
        if not drop_id or not client.room_id:
            return
        async with self._lock:
            room = self._state.rooms.get(client.room_id)
            if not room:
                return
            if drop_id not in room.active_drops:
                return
            room.active_drops.pop(drop_id, None)
            recipients = list(room.members.values())
        payload = {
            "type": "drop_collected",
            "drop_id": drop_id,
            "collector": client.username,
        }
        logging.info("[room %s] drop %s collected by %s", client.room_id, drop_id[:6], client.username)
        for member in recipients:
            await self._sessions.send(member, payload)

    async def handle_drop_collision(self, client: ClientSession, message: Dict[str, Any]) -> None:
        drop_id = message.get("drop_id")
        side = message.get("side")
        if not drop_id or not client.room_id:
            return
        async with self._lock:
            room = self._state.rooms.get(client.room_id)
            if not room:
                return
            if room.game_over:
                return
            drop = room.active_drops.get(drop_id)
            if not drop or drop.get("type") != "mushroom":
                return
            current_dir = drop.get("direction", 1)
            if side == "left":
                new_direction = 1
            elif side == "right":
                new_direction = -1
            else:
                new_direction = -current_dir if current_dir else 1
            drop["direction"] = new_direction or 1
            recipients = list(room.members.values())
        payload = {
            "type": "drop_direction",
            "drop_id": drop_id,
            "direction": drop["direction"],
        }
        for member in recipients:
            await self._sessions.send(member, payload)

    async def handle_tile_break(self, client: ClientSession, message: Dict[str, Any]) -> None:
        if not client.room_id:
            return
        tile_x = message.get("x")
        tile_y = message.get("y")
        if not isinstance(tile_x, int) or not isinstance(tile_y, int):
            return
        async with self._lock:
            room = self._state.rooms.get(client.room_id)
            if not room:
                return
            if room.game_over:
                return
            key = (tile_x, tile_y)
            if key in room.broken_tiles:
                return
            room.broken_tiles.add(key)
            recipients = list(room.members.values())
        payload = {
            "type": "tile_break",
            "x": tile_x,
            "y": tile_y,
            "username": client.username,
        }
        logging.info(
            "[room %s] tile_break at (%d, %d) by %s",
            client.room_id,
            tile_x,
            tile_y,
            client.username,
        )
        for member in recipients:
            await self._sessions.send(member, payload)

    async def handle_floating_coin_collected(self, client: ClientSession, message: Dict[str, Any]) -> None:
        if not client.room_id:
            return
        tx = message.get("x")
        ty = message.get("y")
        if not isinstance(tx, int) or not isinstance(ty, int):
            return
        async with self._lock:
            room = self._state.rooms.get(client.room_id)
            if not room:
                return
            if room.game_over:
                return
            key = (tx, ty)
            if key in room.collected_floating_coins:
                return
            room.collected_floating_coins.add(key)
            recipients = list(room.members.values())
        payload = {
            "type": "floating_coin_collected",
            "x": tx,
            "y": ty,
            "username": client.username,
        }
        logging.info(
            "[room %s] floating_coin_collected at (%d, %d) by %s",
            client.room_id,
            tx,
            ty,
            client.username,
        )
        for member in recipients:
            await self._sessions.send(member, payload)

    async def _room_drop_loop(self, room_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(random.uniform(3.0, 6.0))
                async with self._lock:
                    room = self._state.rooms.get(room_id)
                    if not room or room.is_empty():
                        break
                    if room.game_over:
                        break
                    level_width = LEVEL_WIDTH_PIXELS
                    drop_type = random.choice(["coin", "mushroom"])
                    spawn_x = random.uniform(48, max(96, level_width - 48))
                    direction = random.choice([-1, 1])
                    drop_id = uuid.uuid4().hex
                    room.active_drops[drop_id] = {
                        "type": drop_type,
                        "x": spawn_x,
                        "direction": direction,
                    }
                    logging.info(
                        "[room %s] spawn_drop id=%s type=%s x=%.2f dir=%s",
                        room_id,
                        drop_id[:6],
                        drop_type,
                        spawn_x,
                        direction,
                    )
                    payload = {
                        "type": "spawn_drop",
                        "drop_id": drop_id,
                        "owner": "server",
                        "drop_type": drop_type,
                        "x": spawn_x,
                        "direction": direction,
                    }
                    recipients = list(room.members.values())
                for member in recipients:
                    await self._sessions.send(member, payload)
        except asyncio.CancelledError:
            pass
        finally:
            async with self._lock:
                self._state.room_drop_tasks.pop(room_id, None)
                room = self._state.rooms.get(room_id)
                if room:
                    room.active_drops.clear()

    async def _room_snapshot_loop(self, room_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(0.25)
                async with self._lock:
                    room = self._state.rooms.get(room_id)
                    if not room or room.is_empty() or room.game_over:
                        break
                    snapshot_players = []
                    for member_id, member in room.members.items():
                        state = room.latest_states.get(member_id)
                        if not state:
                            continue
                        info = room.udp_clients.get(member_id)
                        snapshot_players.append(
                            {
                                "username": member.username,
                                "x": state.get("x", 0),
                                "y": state.get("y", 0),
                                "vx": state.get("vx", 0.0),
                                "vy": state.get("vy", 0.0),
                                "flags": state.get("flags", 0),
                                "heading": state.get("heading", 0),
                                "hp": member.hp,
                                "client_id": info.client_index if info else None,
                                "timestamp": state.get("timestamp", udp_protocol.current_millis()),
                            }
                        )
                    recipients = list(room.members.values())
                if not snapshot_players or not recipients:
                    continue
                payload = {
                    "type": "state_snapshot",
                    "timestamp": udp_protocol.current_millis(),
                    "players": snapshot_players,
                }
                for member in recipients:
                    await self._sessions.send(member, payload)
        except asyncio.CancelledError:
            pass
        finally:
            async with self._lock:
                self._state.room_snapshot_tasks.pop(room_id, None)

    async def _broadcast_game_over(self, room: Room, winner: str, loser: str) -> None:
        if room.game_over:
            return
        room.game_over = True
        room.result = {"winner": winner, "loser": loser}
        payload = {
            "type": "game_over",
            "winner": winner,
            "loser": loser,
            "room_id": room.room_id,
        }
        for member in list(room.members.values()):
            await self._sessions.send(member, payload)
        await self._purge_room(room, broadcast_lobby=True)

    async def forward_to_room(self, client: ClientSession, message: Dict[str, Any]) -> None:
        if not client.room_id:
            return
        async with self._lock:
            room = self._state.rooms.get(client.room_id)
            if not room:
                return
            recipients = list(room.others(client.id))
        for member in recipients:
            await self._sessions.send(member, message)
