"""UDP datagram handling: handshake, player state relay, actions, projectiles."""

from __future__ import annotations

import asyncio
import logging
import math
from typing import List, Tuple

import udp_protocol
from models import UdpClientInfo
from state import ServerState


class UdpModule:
    def __init__(self, state: ServerState, lock: asyncio.Lock):
        self._state = state
        self._lock = lock

    class _UdpProtocol(asyncio.DatagramProtocol):
        def __init__(self, udp: "UdpModule", loop: asyncio.AbstractEventLoop):
            self._udp = udp
            self._loop = loop

        def datagram_received(self, data: bytes, addr):
            self._loop.create_task(self._udp.handle_datagram(data, addr))

        def error_received(self, exc):
            logging.warning("UDP error: %s", exc)

        def connection_lost(self, exc):
            if exc:
                logging.warning("UDP connection lost: %s", exc)

    def build_protocol(self, loop: asyncio.AbstractEventLoop) -> "UdpModule._UdpProtocol":
        return UdpModule._UdpProtocol(self, loop)

    async def handle_datagram(self, data: bytes, addr: Tuple[str, int]) -> None:
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
            logging.debug(
                "UDP action packet cid=%s seq=%s addr=%s payload=%s",
                client_index,
                seq,
                addr,
                payload.hex(),
            )
            await self._handle_udp_action(addr, client_index, timestamp, payload)
        elif msg_type == udp_protocol.MSG_PROJECTILE_STATE:
            logging.debug(
                "UDP projectile packet cid=%s seq=%s addr=%s payload=%s",
                client_index,
                seq,
                addr,
                payload.hex(),
            )
            await self._handle_udp_projectile_state(addr, client_index, seq, timestamp, payload)
        else:
            logging.debug("Unhandled UDP message type %s from %s (seq=%s)", msg_type, addr, seq)

    async def _handle_udp_hello(self, client_index: int, token: str, addr: Tuple[str, int]) -> None:
        token = (token or "").strip()
        async with self._lock:
            entry = self._state.pending_udp_tokens.get(token)
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
            room = self._state.rooms.get(room_id)
            if not room:
                logging.debug("UDP hello for non-existent room %s", room_id)
                return
            info = room.udp_clients.get(client_session_id)
            client = room.members.get(client_session_id)
            if not info or info.token != token:
                logging.debug("UDP hello token mismatch for client %s", client_session_id)
                return
            if info.address:
                self._state.udp_addr_map.pop(info.address, None)
            info.address = addr
            info.last_seq = -1
            info.last_timestamp = 0
            self._state.udp_addr_map[addr] = (room.room_id, client_session_id)
            self._state.udp_index_map[(room.room_id, info.client_index)] = client_session_id
            room.latest_states.pop(client_session_id, None)
            client_name = client.username if client else "<unknown>"
            self._state.pending_udp_tokens.pop(token, None)
        logging.info("UDP handshake success for %s (%s)", client_name, addr)
        self._send_udp_ack(info)

    def _send_udp_ack(self, info: UdpClientInfo) -> None:
        if not self._state.udp_transport or not info.address:
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
            self._state.udp_transport.sendto(packet, info.address)
        except OSError as exc:
            logging.warning("Failed to send UDP ACK to %s: %s", info.address, exc)

    async def _handle_udp_player_state(
        self,
        addr: Tuple[str, int],
        client_index: int,
        seq: int,
        timestamp: int,
        payload: bytes,
    ) -> None:
        async with self._lock:
            mapping = self._state.udp_addr_map.get(addr)
            if not mapping:
                logging.debug("UDP state from unknown address %s", addr)
                return
            room_id, client_session_id = mapping
            room = self._state.rooms.get(room_id)
            if not room:
                self._state.udp_addr_map.pop(addr, None)
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
            if not self._state.udp_transport:
                return
            packet_queue: List[Tuple[bytes, Tuple[str, int]]] = []
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
                self._state.udp_transport.sendto(packet, target_addr)
            except OSError as exc:
                logging.debug("Failed to forward UDP state to %s: %s", target_addr, exc)

    async def _handle_udp_action(
        self,
        addr: Tuple[str, int],
        client_index: int,
        timestamp: int,
        payload: bytes,
    ) -> None:
        try:
            action = udp_protocol.unpack_action(payload)
        except ValueError:
            logging.debug("Malformed action payload from %s", addr)
            return
        async with self._lock:
            mapping = self._state.udp_addr_map.get(addr)
            if not mapping:
                return
            room_id, client_session_id = mapping
            room = self._state.rooms.get(room_id)
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
            recipients = [client_info for session_id, client_info in room.udp_clients.items() if client_info.address]
            if not recipients or not self._state.udp_transport:
                return
            packets: List[Tuple[bytes, Tuple[str, int]]] = []
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
                self._state.udp_transport.sendto(packet, target_addr)
            except OSError as exc:
                logging.debug("Failed to send projectile spawn to %s: %s", target_addr, exc)

    async def _handle_udp_projectile_state(
        self,
        addr: Tuple[str, int],
        client_index: int,
        seq: int,
        timestamp: int,
        payload: bytes,
    ) -> None:
        try:
            state = udp_protocol.unpack_projectile_state(payload)
        except ValueError:
            logging.debug("Malformed projectile state from %s", addr)
            return
        recipients: List[UdpClientInfo] = []
        async with self._lock:
            mapping = self._state.udp_addr_map.get(addr)
            if not mapping:
                return
            room_id, client_session_id = mapping
            room = self._state.rooms.get(room_id)
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
        if not recipients or not self._state.udp_transport:
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
                self._state.udp_transport.sendto(packet, client_info.address)
            except OSError as exc:
                logging.debug("Failed to forward projectile state to %s: %s", client_info.address, exc)
