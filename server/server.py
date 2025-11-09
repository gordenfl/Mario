import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional
import random

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def _load_level_length(default_tiles: int = 60) -> int:
    level_path = os.path.join(os.path.dirname(__file__), "..", "client", "levels", "Level1-1.json")
    try:
        with open(level_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            length = int(data.get("length", default_tiles))
            if length > 0:
                return length
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logging.warning("Failed to load level length from %s: %s", level_path, exc)
    return default_tiles


LEVEL_TILE_LENGTH = _load_level_length()
LEVEL_WIDTH_PIXELS = LEVEL_TILE_LENGTH * 32


@dataclass
class ClientSession:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    username: Optional[str] = None
    room_id: Optional[str] = None
    hp: int = 30

    @property
    def peername(self) -> str:
        try:
            return f"{self.writer.get_extra_info('peername')}"
        except Exception:
            return self.id


@dataclass
class Room:
    room_id: str
    members: Dict[str, ClientSession] = field(default_factory=dict)
    active_drops: Dict[str, Dict] = field(default_factory=dict)

    def is_full(self) -> bool:
        return len(self.members) >= 2

    def is_empty(self) -> bool:
        return len(self.members) == 0

    def add_member(self, client: ClientSession) -> None:
        self.members[client.id] = client
        client.room_id = self.room_id

    def remove_member(self, client_id: str) -> None:
        self.members.pop(client_id, None)

    def others(self, client_id: str):
        for cid, member in self.members.items():
            if cid != client_id:
                yield member


class GameServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Dict[str, ClientSession] = {}
        self.rooms: Dict[str, Room] = {}
        self.lock = asyncio.Lock()
        self.room_drop_tasks: Dict[str, asyncio.Task] = {}

    async def start(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
        logging.info("Server listening on %s", addrs)
        async with server:
            await server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client = ClientSession(reader, writer)
        self.clients[client.id] = client
        logging.info("Client connected: %s", client.peername)
        try:
            while not reader.at_eof():
                data = await reader.readline()
                if not data:
                    break
                try:
                    message = json.loads(data.decode().strip())
                except json.JSONDecodeError:
                    await self.send_error(client, "invalid_json", "Unable to parse message")
                    continue
                await self.handle_message(client, message)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            logging.info("Client disconnected unexpectedly: %s", client.peername)
        finally:
            await self.cleanup_client(client)

    async def handle_message(self, client: ClientSession, message: Dict):
        msg_type = message.get("type")
        if msg_type == "login":
            await self.handle_login(client, message)
        elif msg_type == "list_rooms":
            await self.send_rooms_snapshot(client)
        elif msg_type == "create_room":
            await self.handle_create_room(client)
        elif msg_type == "join_room":
            await self.handle_join_room(client, message)
        elif msg_type == "leave_room":
            await self.handle_leave_room(client)
        elif msg_type == "state_update":
            await self.handle_state_update(client, message)
        elif msg_type == "bullet_event":
            await self.forward_to_room(client, message)
        elif msg_type == "player_hit":
            await self.handle_player_hit(client, message)
        elif msg_type == "player_fall":
            await self.handle_player_fall(client, message)
        elif msg_type == "drop_collected":
            await self.handle_drop_collected(client, message)
        elif msg_type == "drop_collision":
            await self.handle_drop_collision(client, message)
        else:
            await self.send_error(client, "unknown_type", f"Unknown message type: {msg_type}")

    async def handle_login(self, client: ClientSession, message: Dict):
        username = message.get("username")
        if not username:
            await self.send_error(client, "invalid_username", "Username is required")
            return
        client.username = username
        logging.info("Client %s logged in as %s", client.peername, username)
        await self.send(client, {
            "type": "login_ok",
            "username": username,
        })
        await self.send_rooms_snapshot(client)

    async def send_rooms_snapshot(self, client: ClientSession):
        rooms_payload = [
            {
                "room_id": room_id,
                "players": [member.username for member in room.members.values()],
                "is_full": room.is_full(),
            }
            for room_id, room in self.rooms.items()
            if not room.is_full()
        ]
        await self.send(client, {"type": "rooms", "rooms": rooms_payload})

    async def handle_create_room(self, client: ClientSession):
        async with self.lock:
            room_id = uuid.uuid4().hex[:6]
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6]
            room = Room(room_id)
            room.add_member(client)
            self.rooms[room_id] = room
        logging.info("Room %s created by %s", room_id, client.username)
        await self.send(client, {"type": "room_created", "room_id": room_id})
        async with self.lock:
            if room_id not in self.room_drop_tasks:
                self.room_drop_tasks[room_id] = asyncio.create_task(self._room_drop_loop(room_id))

    async def handle_join_room(self, client: ClientSession, message: Dict):
        room_id = message.get("room_id")
        if not room_id:
            await self.send_error(client, "invalid_room", "Room id required")
            return
        async with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                await self.send_error(client, "invalid_room", "Room does not exist")
                return
            if room.is_full():
                await self.send_error(client, "room_full", "Room is full")
                return
            room.add_member(client)
        logging.info("%s joined room %s", client.username, room_id)
        await self.send(client, {"type": "room_joined", "room_id": room_id})
        await self.notify_room_ready(room)

    async def notify_room_ready(self, room: Room):
        if not room.is_full():
            for member in room.members.values():
                await self.send(member, {
                    "type": "room_waiting",
                    "room_id": room.room_id,
                    "players": [m.username for m in room.members.values()],
                })
            return
        spawn_slots = ["left", "right"]
        spawn_map = {}
        members_ordered = list(room.members.values())
        for member, slot in zip(members_ordered, spawn_slots):
            spawn_map[member.id] = slot
        players = [
            {
                "username": member.username,
                "hp": member.hp,
                "spawn": spawn_map.get(member.id, "left"),
            }
            for member in members_ordered
        ]
        for member in members_ordered:
            await self.send(member, {
                "type": "room_ready",
                "room_id": room.room_id,
                "players": players,
                "your_spawn": spawn_map.get(member.id, "left"),
            })

    async def handle_leave_room(self, client: ClientSession):
        if not client.room_id:
            return
        async with self.lock:
            room = self.rooms.get(client.room_id)
            if room:
                room.remove_member(client.id)
                should_delete = room.is_empty()
            else:
                should_delete = False
            client.room_id = None
        if room and room.room_id in self.room_drop_tasks and room.is_empty():
            task = self.room_drop_tasks.pop(room.room_id)
            task.cancel()
            room.active_drops.clear()
        if room and not should_delete:
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
            async with self.lock:
                self.rooms.pop(room.room_id, None)
                task = self.room_drop_tasks.pop(room.room_id, None)
                if task:
                    task.cancel()
        logging.info("%s left room %s", client.username, room.room_id if room else "<unknown>")

    async def handle_state_update(self, client: ClientSession, message: Dict):
        if not client.room_id:
            return
        payload = {
            "type": "state_update",
            "username": client.username,
            "state": message.get("state", {}) or {},
        }
        await self.forward_to_room(client, payload)

    async def handle_player_hit(self, client: ClientSession, message: Dict):
        if not client.room_id:
            return
        target = message.get("target")
        damage = message.get("damage", 1)
        defeated_member: Optional[ClientSession] = None
        async with self.lock:
            room = self.rooms.get(client.room_id)
            if not room:
                return
            for member in room.members.values():
                if member.username == target:
                    member.hp = max(0, member.hp - damage)
                    await self.send(member, {
                        "type": "hp_update",
                        "hp": member.hp,
                    })
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
        if defeated_member:
            await self._broadcast_game_over(
                room, client.username, defeated_member.username
            )
    async def handle_player_fall(self, client: ClientSession, message: Dict):
        if not client.room_id:
            return
        async with self.lock:
            room = self.rooms.get(client.room_id)
            if not room:
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

    async def handle_drop_collected(self, client: ClientSession, message: Dict):
        drop_id = message.get("drop_id")
        if not drop_id or not client.room_id:
            return
        async with self.lock:
            room = self.rooms.get(client.room_id)
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
            await self.send(member, payload)

    async def handle_drop_collision(self, client: ClientSession, message: Dict):
        drop_id = message.get("drop_id")
        side = message.get("side")
        if not drop_id or not client.room_id:
            return
        async with self.lock:
            room = self.rooms.get(client.room_id)
            if not room:
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
        logging.info(
            "[room %s] drop %s collision from %s -> dir=%s",
            client.room_id,
            drop_id[:6],
            side,
            drop["direction"],
        )
        for member in recipients:
            await self.send(member, payload)

    async def _room_drop_loop(self, room_id: str):
        try:
            while True:
                await asyncio.sleep(random.uniform(3.0, 6.0))
                async with self.lock:
                    room = self.rooms.get(room_id)
                    if not room or room.is_empty():
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
                    await self.send(member, payload)
        except asyncio.CancelledError:
            pass
        finally:
            async with self.lock:
                self.room_drop_tasks.pop(room_id, None)
                room = self.rooms.get(room_id)
                if room:
                    room.active_drops.clear()

    async def _broadcast_game_over(self, room: Room, winner: str, loser: str):
        payload = {
            "type": "game_over",
            "winner": winner,
            "loser": loser,
            "room_id": room.room_id,
        }
        for member in list(room.members.values()):
            await self.send(member, payload)

    async def forward_to_room(self, client: ClientSession, message: Dict):
        if not client.room_id:
            return
        async with self.lock:
            room = self.rooms.get(client.room_id)
            if not room:
                return
            recipients = list(room.others(client.id))
        for member in recipients:
            await self.send(member, message)

    async def send(self, client: ClientSession, message: Dict):
        data = json.dumps(message) + "\n"
        client.writer.write(data.encode("utf-8"))
        try:
            await client.writer.drain()
        except ConnectionResetError:
            pass

    async def send_error(self, client: ClientSession, code: str, message: str):
        await self.send(client, {"type": "error", "code": code, "message": message})

    async def cleanup_client(self, client: ClientSession):
        logging.info("Cleaning up client %s", client.username or client.peername)
        await self.handle_leave_room(client)
        try:
            client.writer.close()
            await client.writer.wait_closed()
        except Exception:
            pass
        self.clients.pop(client.id, None)


if __name__ == "__main__":
    server = GameServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logging.info("Server shutting down")
