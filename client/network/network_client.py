import json
import queue
import socket
import threading
import time
from typing import Dict, List, Optional


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

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, timeout: float = 10.0):
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

