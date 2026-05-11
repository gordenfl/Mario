import asyncio
import json
import logging
import math
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import udp_protocol

logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(message)s")


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

# Room lifecycle: only WAITING rooms appear in list_rooms; FIGHTING is in-match; room dict entry removed after match.
ROOM_PHASE_WAITING = "waiting"
ROOM_PHASE_FIGHTING = "fighting"


@dataclass
class ClientSession:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    username: Optional[str] = None
    room_id: Optional[str] = None
    hp: int = 30
    udp_id: Optional[int] = None

    @property
    def peername(self) -> str:
        try:
            return f"{self.writer.get_extra_info('peername')}"
        except Exception:
            return self.id


@dataclass
class Room:
    room_id: str
    phase: str = ROOM_PHASE_WAITING
    members: Dict[str, ClientSession] = field(default_factory=dict)
    active_drops: Dict[str, Dict] = field(default_factory=dict)
    broken_tiles: set = field(default_factory=set)
    collected_floating_coins: set = field(default_factory=set)
    game_over: bool = False
    result: Optional[Dict[str, str]] = None
    udp_clients: Dict[str, "UdpClientInfo"] = field(default_factory=dict)
    udp_client_index_map: Dict[int, str] = field(default_factory=dict)
    latest_states: Dict[str, dict] = field(default_factory=dict)
    projectiles: Dict[int, dict] = field(default_factory=dict)
    projectile_counter: int = 0

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


@dataclass
class UdpClientInfo:
    token: str
    client_index: int
    address: Optional[Tuple[str, int]] = None
    last_seq: int = -1
    last_timestamp: int = 0
    next_server_seq: int = 0


class GameServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.udp_port = port  # reuse same numeric port for UDP
        self.clients: Dict[str, ClientSession] = {}
        self.rooms: Dict[str, Room] = {}
        self.lock = asyncio.Lock()
        self.room_drop_tasks: Dict[str, asyncio.Task] = {}
        self.pending_udp_tokens: Dict[str, Tuple[str, str, int]] = {}
        self.udp_transport: Optional[asyncio.transports.DatagramTransport] = None
        self._udp_protocol = None
        self.udp_addr_map: Dict[Tuple[str, int], Tuple[str, str]] = {}
        self.udp_index_map: Dict[Tuple[str, int], str] = {}
        self.room_snapshot_tasks: Dict[str, asyncio.Task] = {}

    async def start(self):
        loop = asyncio.get_running_loop()
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        try:
            udp_transport, udp_protocol = await loop.create_datagram_endpoint(
                lambda: self._UdpProtocol(self, loop),
                local_addr=(self.host, self.udp_port),
            )
            self.udp_transport = udp_transport
            self._udp_protocol = udp_protocol
            addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
            logging.info(
                "Server listening on %s (UDP port %s)",
                addrs,
                self.udp_port,
            )
            async with server:
                await server.serve_forever()
        finally:
            if self.udp_transport:
                self.udp_transport.close()
                self.udp_transport = None

    class _UdpProtocol(asyncio.DatagramProtocol):
        def __init__(self, server: "GameServer", loop: asyncio.AbstractEventLoop):
            self.server = server
            self.loop = loop

        def datagram_received(self, data: bytes, addr):
            self.loop.create_task(self.server.handle_udp_datagram(data, addr))

        def error_received(self, exc):
            logging.warning("UDP error: %s", exc)

        def connection_lost(self, exc):
            if exc:
                logging.warning("UDP connection lost: %s", exc)


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
        elif msg_type == "tile_break":
            await self.handle_tile_break(client, message)
        elif msg_type == "floating_coin_collected":
            await self.handle_floating_coin_collected(client, message)
        else:
            await self.send_error(client, "unknown_type", f"Unknown message type: {msg_type}")

    async def handle_udp_datagram(self, data: bytes, addr):
        try:
            msg_type, client_index, seq, timestamp, payload = udp_protocol.unpack_message(data)
        except ValueError:
            logging.debug("Received malformed UDP packet from %s", addr)
            return
        if msg_type == udp_protocol.MSG_HELLO:
            token = payload.decode("utf-8", "ignore")
            await self._handle_udp_hello(client_index, token, addr)
        elif msg_type == udp_protocol.MSG_PLAYER_STATE:
            await self._handle_udp_player_state(addr, client_index, seq, timestamp, payload)
        elif msg_type == udp_protocol.MSG_ACTION:
            logging.debug("UDP action packet cid=%s seq=%s addr=%s payload=%s", client_index, seq, addr, payload.hex())
            await self._handle_udp_action(addr, client_index, timestamp, payload)
        elif msg_type == udp_protocol.MSG_PROJECTILE_STATE:
            logging.debug("UDP projectile packet cid=%s seq=%s addr=%s payload=%s", client_index, seq, addr, payload.hex())
            await self._handle_udp_projectile_state(addr, client_index, seq, timestamp, payload)
        else:
            logging.debug("Unhandled UDP message type %s from %s (seq=%s)", msg_type, addr, seq)

    async def _handle_udp_hello(self, client_index: int, token: str, addr):
        token = (token or "").strip()
        async with self.lock:
            entry = self.pending_udp_tokens.get(token)
            if not entry:
                logging.debug("UDP hello with unknown token '%s' from %s", token, addr)
                return
            room_id, client_session_id, expected_index = entry
            if client_index != expected_index:
                logging.debug(
                    "UDP hello index mismatch token=%s expected=%s got=%s",
                    token,
                    expected_index,
                    client_index,
                )
                return
            room = self.rooms.get(room_id)
            if not room:
                logging.debug("UDP hello for non-existent room %s", room_id)
                return
            info = room.udp_clients.get(client_session_id)
            client = room.members.get(client_session_id)
            if not info or info.token != token:
                logging.debug("UDP hello token mismatch for client %s", client_session_id)
                return
            if info.address:
                self.udp_addr_map.pop(info.address, None)
            info.address = addr
            info.last_seq = -1
            info.last_timestamp = 0
            self.udp_addr_map[addr] = (room.room_id, client_session_id)
            self.udp_index_map[(room.room_id, info.client_index)] = client_session_id
            room.latest_states.pop(client_session_id, None)
            client_name = client.username if client else "<unknown>"
            self.pending_udp_tokens.pop(token, None)
        logging.info("UDP handshake success for %s (%s)", client_name, addr)
        self._send_udp_ack(info)

    def _send_udp_ack(self, info: UdpClientInfo):
        if not self.udp_transport or not info.address:
            return
        packet = udp_protocol.pack_message(
            udp_protocol.MSG_HELLO_ACK,
            info.client_index,
            info.next_server_seq & 0xFFFF,
            udp_protocol.current_millis(),
            info.token.encode("utf-8"),
        )
        info.next_server_seq = (info.next_server_seq + 1) & 0xFFFF
        try:
            self.udp_transport.sendto(packet, info.address)
        except OSError as exc:
            logging.warning("Failed to send UDP ACK to %s: %s", info.address, exc)

    async def _handle_udp_player_state(self, addr, client_index: int, seq: int, timestamp: int, payload: bytes):
        async with self.lock:
            mapping = self.udp_addr_map.get(addr)
            if not mapping:
                logging.debug("UDP state from unknown address %s", addr)
                return
            room_id, client_session_id = mapping
            room = self.rooms.get(room_id)
            if not room:
                self.udp_addr_map.pop(addr, None)
                return
            info = room.udp_clients.get(client_session_id)
            if not info:
                return
            if info.client_index != client_index:
                logging.debug(
                    "UDP state index mismatch for %s: expected %s got %s",
                    client_session_id,
                    info.client_index,
                    client_index,
                )
                return
            if info.last_seq != -1:
                delta = (seq - info.last_seq) & 0xFFFF
                if delta == 0 or delta > 0x8000:
                    return
            info.last_seq = seq
            info.last_timestamp = timestamp
            try:
                state = udp_protocol.unpack_player_state(payload)
            except ValueError:
                logging.debug("Malformed player state payload from %s", addr)
                return
            state["timestamp"] = timestamp
            room.latest_states[client_session_id] = state
            if not self.udp_transport:
                return
            packet_queue = []
            for session_id, other_info in room.udp_clients.items():
                if session_id == client_session_id or not other_info.address:
                    continue
                seq_out = other_info.next_server_seq & 0xFFFF
                other_info.next_server_seq = (other_info.next_server_seq + 1) & 0xFFFF
                packet = udp_protocol.pack_message(
                    udp_protocol.MSG_PLAYER_STATE,
                    info.client_index,
                    seq_out,
                    timestamp,
                    payload,
                )
                packet_queue.append((packet, other_info.address))
        for packet, target_addr in packet_queue:
            try:
                self.udp_transport.sendto(packet, target_addr)
            except OSError as exc:
                logging.debug("Failed to forward UDP state to %s: %s", target_addr, exc)

    async def _handle_udp_action(self, addr, client_index: int, timestamp: int, payload: bytes):
        try:
            action = udp_protocol.unpack_action(payload)
        except ValueError:
            logging.debug("Malformed action payload from %s", addr)
            return
        async with self.lock:
            mapping = self.udp_addr_map.get(addr)
            if not mapping:
                return
            room_id, client_session_id = mapping
            room = self.rooms.get(room_id)
            if not room:
                return
            info = room.udp_clients.get(client_session_id)
            if not info or info.client_index != client_index:
                return
            if action["action_type"] != udp_protocol.ACTION_FIRE:
                logging.debug("Unhandled action type %s from %s", action["action_type"], client_session_id)
                return
            state = room.latest_states.get(client_session_id)
            member = room.members.get(client_session_id)
            if not state or not member:
                logging.debug(
                    "[udp] action fire but no state for %s (states: %s)",
                    client_session_id,
                    list(room.latest_states.keys()),
                )
                return
            direction = 1 if action.get("param", 1) else -1
            heading = state.get("heading")
            if heading is not None:
                direction = 1 if heading >= 0 else -1
            room.projectile_counter = (room.projectile_counter + 1) & 0xFFFF
            projectile_id = room.projectile_counter
            spawn_x = state.get("x", 0) + 20 * direction
            spawn_y = state.get("y", 0) - 10
            speed = 8.0
            diag_speed = speed / math.sqrt(2)
            vx = diag_speed * direction
            vy = diag_speed
            projectile_state = {
                "projectile_id": projectile_id,
                "x": spawn_x,
                "y": spawn_y,
                "vx": vx,
                "vy": vy,
                "flags": udp_protocol.PROJECTILE_FLAG_SPAWN,
                "timestamp": timestamp,
            }
            room.projectiles[projectile_id] = {
                "owner": client_session_id,
                "state": projectile_state,
            }
            logging.debug(
                "[udp] spawn projectile id=%s owner=%s dir=%s pos=(%.1f, %.1f)",
                projectile_id,
                member.username,
                direction,
                spawn_x,
                spawn_y,
            )
            recipients = [
                client_info
                for session_id, client_info in room.udp_clients.items()
                if client_info.address
            ]
            if not recipients or not self.udp_transport:
                return
            packets = []
            payload_spawn = udp_protocol.pack_projectile_state(
                projectile_id, spawn_x, spawn_y, vx, vy, udp_protocol.PROJECTILE_FLAG_SPAWN
            )
            for client_info in recipients:
                seq_out = client_info.next_server_seq & 0xFFFF
                client_info.next_server_seq = (client_info.next_server_seq + 1) & 0xFFFF
                packet = udp_protocol.pack_message(
                    udp_protocol.MSG_PROJECTILE_STATE,
                    info.client_index,
                    seq_out,
                    timestamp,
                    payload_spawn,
                )
                packets.append((packet, client_info.address))
        for packet, target_addr in packets:
            try:
                self.udp_transport.sendto(packet, target_addr)
            except OSError as exc:
                logging.debug("Failed to send projectile spawn to %s: %s", target_addr, exc)

    async def _handle_udp_projectile_state(self, addr, client_index: int, seq: int, timestamp: int, payload: bytes):
        try:
            state = udp_protocol.unpack_projectile_state(payload)
        except ValueError:
            logging.debug("Malformed projectile state from %s", addr)
            return
        async with self.lock:
            mapping = self.udp_addr_map.get(addr)
            if not mapping:
                return
            room_id, client_session_id = mapping
            room = self.rooms.get(room_id)
            if not room:
                return
            info = room.udp_clients.get(client_session_id)
            if not info or info.client_index != client_index:
                return
            proj_id = state.get("projectile_id")
            record = room.projectiles.get(proj_id)
            if not record or record.get("owner") != client_session_id:
                return
            state["timestamp"] = timestamp
            record["state"] = state
            recipients = [
                client_info
                for session_id, client_info in room.udp_clients.items()
                if session_id != client_session_id and client_info.address
            ]
            if state.get("flags", 0) & udp_protocol.PROJECTILE_FLAG_DESPAWN:
                room.projectiles.pop(proj_id, None)
        if not recipients or not self.udp_transport:
            return
        for client_info in recipients:
            seq_out = client_info.next_server_seq & 0xFFFF
            client_info.next_server_seq = (client_info.next_server_seq + 1) & 0xFFFF
            packet = udp_protocol.pack_message(
                udp_protocol.MSG_PROJECTILE_STATE,
                client_index,
                seq_out,
                timestamp,
                payload,
            )
            try:
                self.udp_transport.sendto(packet, client_info.address)
            except OSError as exc:
                logging.debug("Failed to forward projectile state to %s: %s", client_info.address, exc)
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
                "phase": room.phase,
            }
            for room_id, room in self.rooms.items()
            if room.phase == ROOM_PHASE_WAITING and not room.is_full()
        ]
        await self.send(client, {"type": "rooms", "rooms": rooms_payload})

    async def broadcast_rooms_to_lobby(self) -> None:
        """Notify lobby browsers when joinable room set changes (e.g. room fills / starts)."""
        async with self.lock:
            recipients = [
                c for c in self.clients.values() if c.username and c.room_id is None
            ]
        for client in recipients:
            await self.send_rooms_snapshot(client)

    async def _purge_room(self, room: Room, *, broadcast_lobby: bool) -> None:
        """Remove room from registry, detach members, cancel tasks (match ended or room emptied)."""
        rid = room.room_id
        async with self.lock:
            if rid not in self.rooms:
                return
            self.rooms.pop(rid, None)
            task = self.room_drop_tasks.pop(rid, None)
            if task:
                task.cancel()
            snapshot_task = self.room_snapshot_tasks.pop(rid, None)
            if snapshot_task:
                snapshot_task.cancel()
            room.active_drops.clear()
            room.projectiles.clear()
            for info in list(room.udp_clients.values()):
                self.pending_udp_tokens.pop(info.token, None)
                if info.address:
                    self.udp_addr_map.pop(info.address, None)
                self.udp_index_map.pop((rid, info.client_index), None)
            room.udp_clients.clear()
            room.latest_states.clear()
            room.udp_client_index_map.clear()
            for m in list(room.members.values()):
                m.room_id = None
                m.udp_id = None
            room.members.clear()
        logging.info("Room %s purged from registry", rid)
        if broadcast_lobby:
            await self.broadcast_rooms_to_lobby()

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
        reject: Optional[Tuple[str, str]] = None
        async with self.lock:
            room = self.rooms.get(room_id)
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
            await self.send_error(client, code, errmsg)
            return
        logging.info("%s joined room %s", client.username, room_id)
        await self.send(client, {"type": "room_joined", "room_id": room_id})
        await self.notify_room_ready(room)

    async def notify_room_ready(self, room: Room):
        if not room.is_full():
            room.phase = ROOM_PHASE_WAITING
            for member in room.members.values():
                await self.send(member, {
                    "type": "room_waiting",
                    "room_id": room.room_id,
                    "players": [m.username for m in room.members.values()],
                })
            return
        for info in room.udp_clients.values():
            self.pending_udp_tokens.pop(info.token, None)
            if info.address:
                self.udp_addr_map.pop(info.address, None)
            self.udp_index_map.pop((room.room_id, info.client_index), None)
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
        spawn_map = {}
        members_ordered = list(room.members.values())
        for member, slot in zip(members_ordered, spawn_slots):
            spawn_map[member.id] = slot
        udp_host = None if self.host in ("0.0.0.0", "::", "") else self.host
        for index, member in enumerate(members_ordered):
            member.udp_id = index
            token = uuid.uuid4().hex
            info = UdpClientInfo(token=token, client_index=index)
            room.udp_clients[member.id] = info
            room.udp_client_index_map[index] = member.id
            self.pending_udp_tokens[token] = (room.room_id, member.id, index)
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
            await self.send(member, {
                "type": "room_ready",
                "room_id": room.room_id,
                "players": players,
                "your_spawn": spawn_map.get(member.id, "left"),
                "udp": {
                    "port": self.udp_port,
                    "token": udp_info.token if udp_info else "",
                    "client_id": udp_info.client_index if udp_info else 0,
                    "host": udp_host,
                },
            })
        room.phase = ROOM_PHASE_FIGHTING
        if room.room_id in self.room_snapshot_tasks:
            task = self.room_snapshot_tasks.pop(room.room_id)
            task.cancel()
        self.room_snapshot_tasks[room.room_id] = asyncio.create_task(self._room_snapshot_loop(room.room_id))
        await self.broadcast_rooms_to_lobby()

    async def handle_leave_room(self, client: ClientSession):
        if not client.room_id:
            return
        try:
            await self._handle_leave_room_body(client)
        finally:
            await self.broadcast_rooms_to_lobby()

    async def _handle_leave_room_body(self, client: ClientSession) -> None:
        async with self.lock:
            room = self.rooms.get(client.room_id)
            if room:
                room.remove_member(client.id)
                should_delete = room.is_empty()
                info = room.udp_clients.pop(client.id, None)
                if info:
                    self.pending_udp_tokens.pop(info.token, None)
                    if info.address:
                        self.udp_addr_map.pop(info.address, None)
                    self.udp_index_map.pop((room.room_id, info.client_index), None)
                    room.latest_states.pop(client.id, None)
                    room.udp_client_index_map.pop(info.client_index, None)
            else:
                should_delete = False
            client.room_id = None
            client.udp_id = None
        if room and room.room_id in self.room_drop_tasks and room.is_empty():
            task = self.room_drop_tasks.pop(room.room_id)
            task.cancel()
            room.active_drops.clear()
        if room and room.is_empty():
            snapshot_task = self.room_snapshot_tasks.pop(room.room_id, None)
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

    async def handle_state_update(self, client: ClientSession, message: Dict):
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
        async with self.lock:
            room = self.rooms.get(client.room_id)
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
            if room.game_over:
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
        '''
        logging.info(
            "[room %s] drop %s collision from %s -> dir=%s",
            client.room_id,
            drop_id[:6],
            side,
            drop["direction"],
        )
        '''
        for member in recipients:
            await self.send(member, payload)

    async def handle_tile_break(self, client: ClientSession, message: Dict):
        if not client.room_id:
            return
        tile_x = message.get("x")
        tile_y = message.get("y")
        if not isinstance(tile_x, int) or not isinstance(tile_y, int):
            return
        async with self.lock:
            room = self.rooms.get(client.room_id)
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
            await self.send(member, payload)

    async def handle_floating_coin_collected(self, client: ClientSession, message: Dict):
        """Broadcast floating coin pickup so all clients remove the same tile."""
        if not client.room_id:
            return
        tx = message.get("x")
        ty = message.get("y")
        if not isinstance(tx, int) or not isinstance(ty, int):
            return
        async with self.lock:
            room = self.rooms.get(client.room_id)
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
            await self.send(member, payload)

    async def _room_drop_loop(self, room_id: str):
        try:
            while True:
                await asyncio.sleep(random.uniform(3.0, 6.0))
                async with self.lock:
                    room = self.rooms.get(room_id)
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
                    await self.send(member, payload)
        except asyncio.CancelledError:
            pass
        finally:
            async with self.lock:
                self.room_drop_tasks.pop(room_id, None)
                room = self.rooms.get(room_id)
                if room:
                    room.active_drops.clear()

    async def _room_snapshot_loop(self, room_id: str):
        try:
            while True:
                await asyncio.sleep(0.25)
                async with self.lock:
                    room = self.rooms.get(room_id)
                    if not room or room.is_empty() or room.game_over:
                        break
                    snapshot_players = []
                    for member_id, member in room.members.items():
                        state = room.latest_states.get(member_id)
                        if not state:
                            continue
                        info = room.udp_clients.get(member_id)
                        snapshot_players.append({
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
                        })
                    recipients = list(room.members.values())
                if not snapshot_players or not recipients:
                    continue
                payload = {
                    "type": "state_snapshot",
                    "timestamp": udp_protocol.current_millis(),
                    "players": snapshot_players,
                }
                for member in recipients:
                    await self.send(member, payload)
        except asyncio.CancelledError:
            pass
        finally:
            async with self.lock:
                self.room_snapshot_tasks.pop(room_id, None)

    async def _broadcast_game_over(self, room: Room, winner: str, loser: str):
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
            await self.send(member, payload)
        await self._purge_room(room, broadcast_lobby=True)

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
