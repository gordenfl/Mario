"""Orchestrates TCP/UDP listeners and wires session, room, and UDP modules."""

from __future__ import annotations

import asyncio
import json
import logging

from models import ClientSession
from room_module import RoomModule
from session_module import SessionModule
from state import ServerState
from tcp_dispatch import TcpDispatch
from udp_module import UdpModule


class GameServer:
    """Thin coordinator: owns shared `ServerState`, one lock, and pluggable modules."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self._lock = asyncio.Lock()
        self._state = ServerState(host=host, port=port, udp_port=port)
        self._sessions = SessionModule(self._state, self._lock)
        self._rooms = RoomModule(self._state, self._lock, self._sessions)
        self._sessions.attach_room(self._rooms)
        self._udp = UdpModule(self._state, self._lock)
        self._tcp = TcpDispatch(self._sessions, self._rooms)

    @property
    def host(self) -> str:
        return self._state.host

    @property
    def port(self) -> int:
        return self._state.port

    @property
    def udp_port(self) -> int:
        return self._state.udp_port

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        server = await asyncio.start_server(self.handle_client, self._state.host, self._state.port)
        try:
            udp_transport, _udp_protocol = await loop.create_datagram_endpoint(
                lambda: self._udp.build_protocol(loop),
                local_addr=(self._state.host, self._state.udp_port),
            )
            self._state.udp_transport = udp_transport
            addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
            logging.info(
                "Server listening on %s (UDP port %s)",
                addrs,
                self._state.udp_port,
            )
            async with server:
                await server.serve_forever()
        finally:
            if self._state.udp_transport:
                self._state.udp_transport.close()
                self._state.udp_transport = None

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client = ClientSession(reader, writer)
        self._state.clients[client.id] = client
        logging.info("Client connected: %s", client.peername)
        try:
            while not reader.at_eof():
                data = await reader.readline()
                if not data:
                    break
                try:
                    message = json.loads(data.decode().strip())
                except json.JSONDecodeError:
                    await self._sessions.send_error(client, "invalid_json", "Unable to parse message")
                    continue
                await self._tcp.handle_message(client, message)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            logging.info("Client disconnected unexpectedly: %s", client.peername)
        finally:
            await self._sessions.cleanup_client(client)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(message)s")
    srv = GameServer()
    try:
        asyncio.run(srv.start())
    except KeyboardInterrupt:
        logging.info("Server shutting down")
