"""Non-blocking UDP helper used for high-frequency game updates."""

from __future__ import annotations

import socket
import time
from typing import List, Optional, Tuple

from .protocol import (
    MSG_HELLO,
    MSG_HELLO_ACK,
    current_millis,
    pack_message,
    unpack_message,
)


class UdpClient:
    """Lightweight UDP transport with minimal handshake support."""

    def __init__(self):
        self.socket: Optional[socket.socket] = None
        self.server_addr: Optional[Tuple[str, int]] = None
        self.client_id: int = 0
        self.seq: int = 0
        self.connected: bool = False
        self.token: str = ""
        self.last_hello_at: float = 0.0

    def open(self, token: str, client_id: int, host: str, port: int) -> None:
        """Initialise the UDP socket and kick off the handshake."""
        self.close()
        self.token = token or ""
        self.client_id = int(client_id) & 0xFF
        self.seq = 0
        self.connected = False
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.server_addr = (host, int(port))
        self._send_hello()

    def close(self) -> None:
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
        self.socket = None
        self.server_addr = None
        self.connected = False

    def _send_hello(self) -> None:
        if not self.socket or not self.server_addr:
            return
        payload = self.token.encode("utf-8")
        packet = pack_message(MSG_HELLO, self.client_id, self.seq & 0xFFFF, current_millis(), payload)
        self.seq = (self.seq + 1) & 0xFFFF
        try:
            self.socket.sendto(packet, self.server_addr)
            self.last_hello_at = time.time()
        except OSError:
            pass

    def send(self, msg_type: int, payload: bytes = b"", client_id: Optional[int] = None) -> bool:
        """Send a UDP packet to the server."""
        if not self.socket or not self.server_addr:
            return False
        cid = self.client_id if client_id is None else client_id
        packet = pack_message(msg_type, cid & 0xFF, self.seq & 0xFFFF, current_millis(), payload)
        self.seq = (self.seq + 1) & 0xFFFF
        try:
            self.socket.sendto(packet, self.server_addr)
            return True
        except OSError:
            return False

    def poll(self) -> List[Tuple[int, dict]]:
        """Poll the socket and return a list of (msg_type, data) tuples."""
        events: List[Tuple[int, dict]] = []
        if not self.socket:
            return events
        if not self.connected and (time.time() - self.last_hello_at) > 1.0:
            self._send_hello()
        while True:
            try:
                data, addr = self.socket.recvfrom(4096)
            except BlockingIOError:
                break
            except OSError:
                break
            try:
                msg_type, client_id, seq, timestamp, payload = unpack_message(data)
            except ValueError:
                continue
            event = {
                "client_id": client_id,
                "seq": seq,
                "timestamp": timestamp,
                "payload": payload,
                "addr": addr,
            }
            if msg_type == MSG_HELLO_ACK:
                if not self.connected:
                    self.connected = True
                    print(f"[udp] handshake ack from {addr} (client_id={self.client_id})")
                events.append((msg_type, event))
            else:
                events.append((msg_type, event))
        return events


