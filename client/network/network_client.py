import json
import logging
import queue
import socket
import threading
import time
from typing import Dict, List, Optional, Tuple

from .protocol import (
    MSG_HELLO_ACK,
    MSG_PLAYER_STATE,
    MSG_PROJECTILE_STATE,
    MSG_ACTION,
    pack_player_state,
    pack_projectile_state,
    pack_action,
    unpack_player_state,
    unpack_projectile_state,
    unpack_action,
)
from .udp_client import UdpClient


NEWLINE = "\n"
BUFFER_SIZE = 4096


class NetworkError(Exception):
    """Raised when a fatal networking issue occurs."""


class NetworkClient:
    """A lightweight TCP client that exchanges JSON messages with the server.

    Messages are delimited by newlines. The client maintains an outgoing queue
    that the main thread can push onto while a background thread flushes data
    to the socket. Incoming data is accumulated in a buffer that is parsed into
    JSON messages when complete lines are available.
    """

    def __init__(self, host: str = "192.168.1.75", port: int = 8765, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._recv_buffer = ""
        self._incoming: "queue.Queue[Dict]" = queue.Queue()
        self._outgoing: "queue.Queue[str]" = queue.Queue()
        self._writer_thread: Optional[threading.Thread] = None
        self._connected = threading.Event()
        self.username: Optional[str] = None
        self.room_id: Optional[str] = None
        self.running = False
        self._udp_client: Optional[UdpClient] = None
        self._udp_enabled = False
        self._udp_state_interval = 1.0 / 60.0
        self._last_udp_state_sent = 0.0
        self._last_udp_logged_payload: Optional[bytes] = None

    def connect(self, username: str) -> Dict:
        """Connect to the server and perform login. Returns login response."""
        self.username = username
        self._socket = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._socket.setblocking(False)
        self.running = True
        self._writer_thread = threading.Thread(target=self._flush_outgoing, daemon=True)
        self._writer_thread.start()
        self.send_message({"type": "login", "username": username})
        response = self.wait_for_message("login_ok")
        if not response:
            raise NetworkError("Failed to receive login confirmation")
        self._connected.set()
        return response

    def close(self):
        self.running = False
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=1.0)
        if self._udp_client:
            self._udp_client.close()
            self._udp_client = None
        self._udp_enabled = False
        self._last_udp_logged_payload = None

    def list_rooms(self) -> List[Dict]:
        self.send_message({"type": "list_rooms"})
        response = self.wait_for_message("rooms")
        return response.get("rooms", []) if response else []

    def create_room(self) -> Optional[str]:
        self.request_create_room()
        response = self.wait_for_message("room_created")
        if response:
            self.room_id = response.get("room_id")
        return self.room_id

    def join_room(self, room_id: str) -> bool:
        self.request_join_room(room_id)
        response = self.wait_for_message("room_joined", timeout=5)
        if response:
            self.room_id = room_id
            return True
        error = self.wait_for_message("error", timeout=0.1)
        if error:
            raise NetworkError(error.get("message", "Failed to join room"))
        return False

    def wait_for_room_ready(self, poll_interval: float = 0.1) -> Dict:
        while True:
            message = self.wait_for_message("room_ready", timeout=poll_interval)
            if message:
                return message

    def send_state(self, state: Dict):
        payload = {
            "type": "state_update",
            "state": state,
        }
        self.send_message(payload)

    def send_bullet_event(self, event: Dict):
        payload = {
            "type": "bullet_event",
            **event,
        }
        self.send_message(payload)

    def send_player_hit(self, target: str, damage: int = 1):
        payload = {
            "type": "player_hit",
            "target": target,
            "damage": damage,
        }
        self.send_message(payload)

    def send_drop_collected(self, drop_id: str):
        payload = {
            "type": "drop_collected",
            "drop_id": drop_id,
        }
        self.send_message(payload)

    def send_drop_collision(self, drop_id: str, side: str):
        payload = {
            "type": "drop_collision",
            "drop_id": drop_id,
            "side": side,
        }
        self.send_message(payload)

    def send_tile_break(self, x: int, y: int):
        payload = {
            "type": "tile_break",
            "x": int(x),
            "y": int(y),
        }
        self.send_message(payload)

    def send_floating_coin_collected(self, x: int, y: int):
        payload = {
            "type": "floating_coin_collected",
            "x": int(x),
            "y": int(y),
        }
        self.send_message(payload)

    # -- UDP support -----------------------------------------------------

    def enable_udp(self, token: str, client_id: int, port: Optional[int] = None, host: Optional[str] = None) -> bool:
        """Initialise the UDP transport for high-frequency messages."""
        token = (token or "").strip()
        if not token:
            logging.debug("UDP token missing; UDP channel not enabled")
            return False
        if host in (None, "", "0.0.0.0"):
            host = self.host
        if port is None:
            port = self.port
        if self._udp_client is None:
            self._udp_client = UdpClient()
        try:
            self._udp_client.open(token, client_id, host, port)
            self._udp_enabled = True
            self._last_udp_state_sent = 0.0
            self._last_udp_logged_payload = None
            logging.debug("UDP channel enabled: host=%s port=%s client_id=%s", host, port, client_id)
            return True
        except OSError as exc:
            logging.warning("Failed to open UDP channel: %s", exc)
            self._udp_enabled = False
            return False

    def poll_udp(self) -> List[Tuple[int, dict]]:
        """Poll the UDP socket and return decoded events."""
        if not self._udp_client or not self._udp_enabled:
            return []
        events = self._udp_client.poll()
        for msg_type, event in events:
            if msg_type == MSG_HELLO_ACK:
                logging.debug("Received UDP handshake acknowledgment from %s", event.get("addr"))
            elif msg_type == MSG_PLAYER_STATE:
                try:
                    event["player_state"] = unpack_player_state(event.get("payload", b""))
                except ValueError:
                    logging.debug("Dropping malformed player state payload from %s", event.get("addr"))
                    event["player_state"] = None
            elif msg_type == MSG_PROJECTILE_STATE:
                try:
                    event["projectile_state"] = unpack_projectile_state(event.get("payload", b""))
                except ValueError:
                    logging.debug("Dropping malformed projectile state from %s", event.get("addr"))
                    event["projectile_state"] = None
            elif msg_type == MSG_ACTION:
                try:
                    event["action"] = unpack_action(event.get("payload", b""))
                except ValueError:
                    event["action"] = None
        return events

    def udp_connected(self) -> bool:
        return bool(self._udp_client and self._udp_client.connected)

    def send_udp_player_state(self, state: Dict[str, float]) -> bool:
        """Send the player's current state over UDP."""
        if not self._udp_client or not self._udp_enabled:
            logging.debug("[udp] skip state send (udp disabled)")
            return False
        now = time.monotonic()
        if now - self._last_udp_state_sent < self._udp_state_interval:
            return False
        payload = pack_player_state(
            state.get("x", 0.0),
            state.get("y", 0.0),
            state.get("vx", 0.0),
            state.get("vy", 0.0),
            int(state.get("flags", 0)),
            int(state.get("heading", 0)),
        )
        ok = self._udp_client.send(MSG_PLAYER_STATE, payload)
        if payload != self._last_udp_logged_payload:
            logging.debug("[udp] send state -> %s payload=%s", ok, state)
            self._last_udp_logged_payload = payload
        if ok:
            self._last_udp_state_sent = now
        return ok

    def send_udp_action(self, action_type: int, param: int = 0, extra: int = 0, client_id: Optional[int] = None) -> bool:
        if not self._udp_client or not self._udp_enabled:
            logging.debug("[udp] skip action send (udp disabled)")
            return False
        payload = pack_action(action_type, param, extra)
        ok = self._udp_client.send(MSG_ACTION, payload, client_id=client_id)
        logging.debug("[udp] send action type=%s param=%s -> %s", action_type, param, ok)
        return ok

    def send_udp_projectile(self, projectile_id: int, x: float, y: float, vx: float, vy: float, flags: int, client_id: Optional[int] = None) -> bool:
        if not self._udp_client or not self._udp_enabled:
            return False
        payload = pack_projectile_state(projectile_id, x, y, vx, vy, flags)
        return self._udp_client.send(MSG_PROJECTILE_STATE, payload, client_id=client_id)

    # 非阻塞请求接口，配合轮询使用
    def request_room_list(self):
        self.send_message({"type": "list_rooms"})

    def request_create_room(self):
        self.send_message({"type": "create_room"})

    def request_join_room(self, room_id: str):
        self.send_message({"type": "join_room", "room_id": room_id})

    def send_message(self, message: Dict):
        data = json.dumps(message) + NEWLINE
        self._outgoing.put(data)

    def poll(self) -> List[Dict]:
        if not self._socket:
            return []
        messages: List[Dict] = []
        while True:
            try:
                chunk = self._socket.recv(BUFFER_SIZE)
                if not chunk:
                    self.running = False
                    break
                self._recv_buffer += chunk.decode("utf-8")
            except BlockingIOError:
                break
            except ConnectionResetError:
                self.running = False
                break
        while NEWLINE in self._recv_buffer:
            line, self._recv_buffer = self._recv_buffer.split(NEWLINE, 1)
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
                messages.append(message)
            except json.JSONDecodeError:
                continue
        for message in messages:
            self._incoming.put(message)
        drained: List[Dict] = []
        while True:
            try:
                drained.append(self._incoming.get_nowait())
            except queue.Empty:
                break
        return drained

    def wait_for_message(self, message_type: str, timeout: float = 5.0) -> Optional[Dict]:
        deadline = time.time() + timeout if timeout else None
        while True:
            messages = self.poll()
            for message in messages:
                if message.get("type") == message_type:
                    return message
            if deadline is not None and time.time() > deadline:
                return None
            time.sleep(0.05)

    def _flush_outgoing(self):
        while self.running:
            try:
                data = self._outgoing.get(timeout=0.1)
            except queue.Empty:
                continue
            if not self._socket:
                continue
            try:
                self._socket.sendall(data.encode("utf-8"))
            except OSError:
                self.running = False
                break

