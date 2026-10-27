import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QKeyEvent
from PyQt6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTextEdit, QVBoxLayout, QWidget

from .auth_client import AuthWorker
from .network_worker import SocketWorker
from .settings import load_settings, save_settings


class MessageEditor(QTextEdit):
    send_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.send_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ChatWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("QuantumBytes Chat")
        self.resize(1100, 720)
        self.settings = load_settings()
        self.worker: SocketWorker | None = None
        self.auth_worker: AuthWorker | None = None
        self.token = ""
        self.current_username = ""
        self.current_room = "general"
        self.seen_message_ids: set[str] = set()
        self.room_messages: dict[str, list[dict[str, Any]]] = {"general": []}
        self.last_sequence_by_room: dict[str, int] = {}
        self.read_message_ids: set[str] = set()
        self.is_typing = False
        self.typing_timer = QTimer(self)
        self.typing_timer.setSingleShot(True)
        self.typing_timer.setInterval(2500)
        self.typing_timer.timeout.connect(self.stop_typing)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self._build_login_page()
        self._build_chat_page()
        self.stack.setCurrentWidget(self.login_page)

    def _build_login_page(self) -> None:
        self.login_page = QWidget()
        layout = QVBoxLayout(self.login_page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form = QWidget()
        form.setMaximumWidth(420)
        form_layout = QVBoxLayout(form)
        title = QLabel("QuantumBytes Chat")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        form_layout.addWidget(title)
        form_layout.addWidget(QLabel("Sign in or create an account"))
        self.server_url_input = QLineEdit(self.settings["server_url"])
        self.server_url_input.setPlaceholderText("Server URL")
        self.username_input = QLineEdit(self.settings["username"])
        self.username_input.setPlaceholderText("Username")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        buttons = QHBoxLayout()
        login_button = QPushButton("Login")
        login_button.clicked.connect(lambda: self.authenticate("login"))
        register_button = QPushButton("Register")
        register_button.clicked.connect(lambda: self.authenticate("register"))
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_connection)
        self.cancel_button.setEnabled(False)
        buttons.addWidget(login_button)
        buttons.addWidget(register_button)
        buttons.addWidget(self.cancel_button)
        self.login_status = QLabel("Offline")
        self.login_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.login_error = QLabel("")
        self.login_error.setWordWrap(True)
        self.login_error.setStyleSheet("color: #b42318;")
        form_layout.addWidget(self.server_url_input)
        form_layout.addWidget(self.username_input)
        form_layout.addWidget(self.password_input)
        form_layout.addLayout(buttons)
        form_layout.addWidget(self.login_status)
        form_layout.addWidget(self.login_error)
        layout.addWidget(form)
        self.stack.addWidget(self.login_page)

    def _build_chat_page(self) -> None:
        self.chat_page = QWidget()
        root = QHBoxLayout(self.chat_page)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.addWidget(QLabel("Chats"))
        self.room_list = QListWidget()
        general_item = QListWidgetItem("general")
        general_item.setData(Qt.ItemDataRole.UserRole, "general")
        self.room_list.addItem(general_item)
        self.room_list.currentItemChanged.connect(self.select_room)
        sidebar_layout.addWidget(self.room_list)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search username")
        search_button = QPushButton("Search")
        search_button.clicked.connect(self.search_users)
        sidebar_layout.addWidget(self.search_input)
        sidebar_layout.addWidget(search_button)
        self.search_results = QListWidget()
        self.search_results.itemClicked.connect(self.open_direct_chat)
        sidebar_layout.addWidget(self.search_results)
        self.group_name_input = QLineEdit()
        self.group_name_input.setPlaceholderText("New group name")
        group_button = QPushButton("Create group")
        group_button.clicked.connect(self.create_group)
        self.member_input = QLineEdit()
        self.member_input.setPlaceholderText("Member username")
        add_member_button = QPushButton("Add member")
        add_member_button.clicked.connect(self.add_group_member)
        leave_button = QPushButton("Leave group")
        leave_button.clicked.connect(self.leave_group)
        sidebar_layout.addWidget(self.group_name_input)
        sidebar_layout.addWidget(group_button)
        sidebar_layout.addWidget(self.member_input)
        sidebar_layout.addWidget(add_member_button)
        sidebar_layout.addWidget(leave_button)
        splitter.addWidget(sidebar)

        chat = QWidget()
        chat_layout = QVBoxLayout(chat)
        header = QHBoxLayout()
        self.room_title = QLabel("general")
        self.room_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.chat_status = QLabel("Offline")
        self.presence_status = QLabel("")
        header.addWidget(self.room_title)
        header.addStretch()
        header.addWidget(self.presence_status)
        header.addWidget(self.chat_status)
        chat_layout.addLayout(header)
        self.typing_status = QLabel("")
        chat_layout.addWidget(self.typing_status)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #b42318;")
        chat_layout.addWidget(self.error_label)
        self.message_area = QScrollArea()
        self.message_area.setWidgetResizable(True)
        self.message_container = QWidget()
        self.message_layout = QVBoxLayout(self.message_container)
        self.message_layout.addStretch()
        self.message_area.setWidget(self.message_container)
        chat_layout.addWidget(self.message_area)
        composer = QHBoxLayout()
        self.composer = MessageEditor()
        self.composer.setPlaceholderText("Write a message... (Enter sends, Shift+Enter adds a line)")
        self.composer.setFixedHeight(70)
        self.composer.send_requested.connect(self.send_message)
        self.composer.textChanged.connect(self.typing_changed)
        send_button = QPushButton("Send")
        send_button.clicked.connect(self.send_message)
        attach_button = QPushButton("Attach file")
        attach_button.clicked.connect(self.choose_file)
        composer.addWidget(self.composer)
        composer.addWidget(attach_button)
        composer.addWidget(send_button)
        chat_layout.addLayout(composer)
        splitter.addWidget(chat)
        splitter.setStretchFactor(1, 1)
        self.stack.addWidget(self.chat_page)

    def normalized_server_url(self) -> str:
        server_url = self.server_url_input.text().strip()
        if "://" not in server_url:
            server_url = f"http://{server_url}"
            self.server_url_input.setText(server_url)
        return server_url.rstrip("/")

    def authenticate(self, mode: str) -> None:
        self.cancel_connection()
        server_url = self.normalized_server_url()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not server_url or not username or not password:
            self.login_status.setText("Server URL, username, and password are required")
            return
        save_settings(server_url, username)
        self.login_status.setText("Connecting...")
        self.login_error.clear()
        self.cancel_button.setEnabled(True)
        self.auth_worker = AuthWorker(mode, server_url, username, password)
        self.auth_worker.succeeded.connect(self.auth_succeeded)
        self.auth_worker.failed.connect(self.auth_failed)
        self.auth_worker.start()

    def auth_succeeded(self, payload: dict[str, Any]) -> None:
        self.token = str(payload["access_token"])
        self.current_username = str(payload["user"]["username"])
        self.password_input.clear()
        self.login_status.setText("Connected")
        self.cancel_button.setEnabled(True)
        self.worker = SocketWorker(self.normalized_server_url(), self.current_username, self.token)
        self.worker.connection_state_changed.connect(self.connection_state_changed)
        self.worker.message_received.connect(self.receive_message)
        self.worker.message_acknowledged.connect(self.receive_ack)
        self.worker.server_error.connect(self.receive_error)
        self.worker.history_received.connect(self.receive_history)
        self.worker.room_added.connect(self.receive_room_added)
        self.worker.room_removed.connect(self.receive_room_removed)
        self.worker.typing_received.connect(self.receive_typing)
        self.worker.presence_changed.connect(self.receive_presence)
        self.worker.status_changed.connect(self.receive_status)
        self.worker.authentication_failed.connect(self.authentication_failed)
        self.worker.start()

    def auth_failed(self, error: dict[str, Any]) -> None:
        self.cancel_button.setEnabled(False)
        self.login_status.setText("Offline")
        self.login_error.setText(f"{error.get('code', 'AUTH_ERROR')}: {error.get('message', 'Authentication failed')}")

    def cancel_connection(self) -> None:
        if self.auth_worker and self.auth_worker.isRunning():
            self.auth_worker.quit()
            self.auth_worker.wait(3000)
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        self.auth_worker = None
        self.worker = None
        self.cancel_button.setEnabled(False)
        self.login_status.setText("Offline")

    def authentication_failed(self, reason: str) -> None:
        self.login_error.setText(f"{reason}: Please log in again")
        self.cancel_connection()
        self.stack.setCurrentWidget(self.login_page)

    def connection_state_changed(self, state: str) -> None:
        self.login_status.setText(state)
        self.chat_status.setText(state)
        if state == "Connected":
            self.stack.setCurrentWidget(self.chat_page)
            self.load_rooms()
            if self.worker:
                self.worker.join_room(self.current_room)
        elif state == "Offline":
            self.cancel_button.setEnabled(False)
            if self.token:
                self.stack.setCurrentWidget(self.login_page)

    def select_room(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        del previous
        if current:
            self.current_room = str(current.data(Qt.ItemDataRole.UserRole) or current.text())
            self.room_title.setText(self.current_room)
            self.room_messages.setdefault(self.current_room, [])
            self.render_current_room()
            if self.worker:
                self.worker.join_room(self.current_room)

    def search_users(self) -> None:
        query = self.search_input.text().strip()
        if not query or not self.token:
            return
        self.search_results.clear()
        self.auth_worker = AuthWorker("search", self.normalized_server_url(), token=self.token, query=query)
        self.auth_worker.succeeded.connect(self.show_search_results)
        self.auth_worker.failed.connect(self.show_search_error)
        self.auth_worker.start()

    def load_rooms(self) -> None:
        self.auth_worker = AuthWorker("rooms", self.normalized_server_url(), token=self.token)
        self.auth_worker.succeeded.connect(self.show_rooms)
        self.auth_worker.failed.connect(self.show_search_error)
        self.auth_worker.start()

    def show_rooms(self, payload: dict[str, Any]) -> None:
        for room in payload.get("rooms", []):
            if room.get("room_id") != "general":
                self.add_room(room["room_id"], room["name"])

    def create_group(self) -> None:
        name = self.group_name_input.text().strip()
        if not name or not self.token:
            return
        self.auth_worker = AuthWorker("group", self.normalized_server_url(), token=self.token, query=name)
        self.auth_worker.succeeded.connect(lambda payload: self.add_room(payload["room"]["room_id"], payload["room"]["name"]))
        self.auth_worker.failed.connect(self.show_search_error)
        self.auth_worker.start()

    def add_group_member(self) -> None:
        username = self.member_input.text().strip()
        if not username or not self.token or not self.current_room.startswith("group-"):
            return
        self.auth_worker = AuthWorker("member", self.normalized_server_url(), username=username, token=self.token, query=self.current_room)
        self.auth_worker.failed.connect(self.show_search_error)
        self.auth_worker.start()

    def leave_group(self) -> None:
        if not self.token or not self.current_room.startswith("group-"):
            return
        self.auth_worker = AuthWorker("leave", self.normalized_server_url(), token=self.token, query=self.current_room)
        self.auth_worker.failed.connect(self.show_search_error)
        self.auth_worker.start()

    def show_search_results(self, payload: dict[str, Any]) -> None:
        self.search_results.clear()
        for user in payload.get("users", []):
            item = QListWidgetItem(user["username"])
            item.setData(Qt.ItemDataRole.UserRole, user["username"])
            self.search_results.addItem(item)

    def open_direct_chat(self, item: QListWidgetItem) -> None:
        username = str(item.data(Qt.ItemDataRole.UserRole))
        self.auth_worker = AuthWorker("direct", self.normalized_server_url(), token=self.token, query=username)
        self.auth_worker.succeeded.connect(lambda payload: self.add_room(payload["room"]["room_id"], payload["room"]["name"]))
        self.auth_worker.failed.connect(self.show_search_error)
        self.auth_worker.start()

    def add_room(self, room_id: str, name: str) -> None:
        matches = [self.room_list.item(index) for index in range(self.room_list.count()) if self.room_list.item(index).data(Qt.ItemDataRole.UserRole) == room_id]
        if not matches:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, room_id)
            self.room_list.addItem(item)
        else:
            item = matches[0]
            item.setText(name)
        self.room_list.setCurrentItem(item)
        self.current_room = room_id
        self.room_title.setText(name)
        self.room_messages.setdefault(room_id, [])
        if self.worker:
            self.worker.join_room(room_id)

    def receive_room_added(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        if data.get("room_id") and data.get("name"):
            self.add_room(data["room_id"], data["name"])

    def receive_room_removed(self, payload: dict[str, Any]) -> None:
        room_id = payload.get("data", {}).get("room_id")
        if room_id == self.current_room:
            self.current_room = "general"
            self.room_title.setText("general")
            self.render_current_room()

    def show_search_error(self, error: dict[str, Any]) -> None:
        self.show_error(f"{error.get('code', 'REQUEST_ERROR')}: {error.get('message', 'Request failed')}")

    def send_message(self) -> None:
        text = self.composer.toPlainText().strip()
        if not text or not self.worker:
            return
        client_message_id = f"client-{uuid4().hex}"
        message = {"message_id": None, "client_message_id": client_message_id, "room_id": self.current_room, "sender": {"username": self.current_username}, "mine": True, "kind": "text", "text": text, "status": "pending"}
        self.room_messages.setdefault(self.current_room, []).append(message)
        self.render_current_room()
        self.composer.clear()
        self.worker.send_message(self.current_room, client_message_id, text)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Share a file")
        if not path or not self.token:
            return
        if Path(path).stat().st_size > 5 * 1024 * 1024:
            self.show_error("Files must be 5 MB or smaller")
            return
        self.auth_worker = AuthWorker("upload", self.normalized_server_url(), token=self.token, query=path)
        self.auth_worker.succeeded.connect(lambda payload: self.send_file_reference(payload["file"]))
        self.auth_worker.failed.connect(self.show_search_error)
        self.auth_worker.start()

    def send_file_reference(self, file_info: dict[str, Any]) -> None:
        client_message_id = f"client-{uuid4().hex}"
        kind = "image" if str(file_info.get("content_type", "")).startswith("image/") else "file"
        message = {"message_id": None, "client_message_id": client_message_id, "room_id": self.current_room, "sender": {"username": self.current_username}, "mine": True, "kind": kind, "text": "", "file": file_info, "status": "pending"}
        self.room_messages.setdefault(self.current_room, []).append(message)
        self.render_current_room()
        if self.worker:
            self.worker.send_message(self.current_room, client_message_id, "", kind=kind, file_id=file_info["file_id"])

    def download_file(self, file_info: dict[str, Any]) -> None:
        destination, _ = QFileDialog.getSaveFileName(self, "Save file", file_info.get("name", "download"))
        if not destination:
            return
        worker = AuthWorker("download", self.normalized_server_url(), token=self.token, query=file_info["file_id"])
        def save_download(payload: dict[str, Any]) -> None:
            Path(destination).write_bytes(payload["content"])
        worker.succeeded.connect(save_download)
        worker.failed.connect(self.show_search_error)
        self.auth_worker = worker
        worker.start()

    def receive_typing(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        if data.get("room_id") == self.current_room:
            self.typing_status.setText(f"{data.get('username')} is typing..." if data.get("is_typing") else "")

    def receive_presence(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        self.presence_status.setText(f"{data.get('username')} {'online' if data.get('online') else 'offline'}")

    def receive_status(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        for messages in self.room_messages.values():
            for message in messages:
                if message.get("message_id") == data.get("message_id"):
                    message["status"] = data.get("status", message.get("status"))
        if data.get("room_id") == self.current_room:
            self.render_current_room()

    def typing_changed(self) -> None:
        has_text = bool(self.composer.toPlainText())
        if not self.worker:
            return
        if has_text:
            if not self.is_typing:
                self.worker.set_typing(self.current_room, True)
                self.is_typing = True
            self.typing_timer.start()
        else:
            self.stop_typing()

    def stop_typing(self) -> None:
        if self.worker and self.is_typing:
            self.worker.set_typing(self.current_room, False)
        self.is_typing = False

    def clear_messages(self) -> None:
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
        self.message_layout.addStretch()

    def render_current_room(self) -> None:
        self.clear_messages()
        for message in self.room_messages.get(self.current_room, []):
            self.add_message_bubble(message)
            message_id = message.get("message_id")
            if self.worker and message_id and not message.get("mine") and message_id not in self.read_message_ids:
                self.read_message_ids.add(message_id)
                self.worker.mark_read(self.current_room, message_id)

    def add_message_bubble(self, message: dict[str, Any]) -> QLabel:
        row = QHBoxLayout()
        sender = message.get("sender", {}).get("username", "Unknown")
        is_mine = bool(message.get("mine")) or sender == self.current_username
        display_sender = "You" if is_mine else sender
        file_info = message.get("file")
        display_text = message.get("text", "") or (file_info.get("name", "File") if file_info else "")
        bubble = QLabel(f"{display_sender}: {display_text}\n{message.get('status', 'sent')}")
        bubble.setWordWrap(True)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        bubble.setStyleSheet("background: #e7f6ec; border-radius: 8px; padding: 10px;")
        if is_mine:
            row.addStretch()
        row.addWidget(bubble)
        if not is_mine:
            row.addStretch()
        self.message_layout.insertLayout(self.message_layout.count() - 1, row)
        if file_info and file_info.get("file_id"):
            download_button = QPushButton("Download")
            download_button.clicked.connect(lambda _checked=False, value=file_info: self.download_file(value))
            self.message_layout.insertWidget(self.message_layout.count() - 1, download_button, alignment=Qt.AlignmentFlag.AlignLeft)
        return bubble

    def receive_history(self, payload: dict[str, Any]) -> None:
        room_id = payload["room_id"]
        messages = self.room_messages.setdefault(room_id, [])
        known = {message.get("message_id") for message in messages}
        for message in payload.get("messages", []):
            if message.get("message_id") not in known:
                message["mine"] = message.get("sender", {}).get("username") == self.current_username
                messages.append(message)
                self.seen_message_ids.add(message.get("message_id"))
                if isinstance(message.get("sequence_id"), int):
                    self.last_sequence_by_room[room_id] = max(self.last_sequence_by_room.get(room_id, 0), message["sequence_id"])
        if room_id == self.current_room:
            self.render_current_room()

    def receive_message(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        message_id = data.get("message_id")
        room_id = data.get("room_id")
        if not message_id or not room_id or message_id in self.seen_message_ids:
            return
        self.seen_message_ids.add(message_id)
        existing = next((message for message in self.room_messages.setdefault(room_id, []) if message.get("client_message_id") == data.get("client_message_id")), None)
        if existing:
            existing.update(data)
            existing["mine"] = data.get("sender", {}).get("username") == self.current_username
        else:
            data["mine"] = data.get("sender", {}).get("username") == self.current_username
            self.room_messages[room_id].append(data)
        if room_id == self.current_room:
            self.render_current_room()

    def receive_ack(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        request_id = payload.get("request_id")
        message = next((item for messages in self.room_messages.values() for item in messages if item.get("client_message_id") == request_id), None)
        if data.get("code") in {"RATE_LIMITED", "NOT_IN_ROOM", "INVALID_MESSAGE"}:
            if message:
                message["status"] = "failed"
                if message.get("room_id") == self.current_room:
                    self.render_current_room()
            self.show_error(f"{data['code']}: {data.get('message', 'Request rejected')}")
        elif data.get("status") == "sent" and message:
            message["message_id"] = data.get("message_id")
            message["status"] = "sent"
            if message.get("room_id") == self.current_room:
                self.render_current_room()

    def receive_error(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        self.show_error(f"{data.get('code', 'SERVER_ERROR')}: {data.get('message', 'Server error')}")

    def show_error(self, message: str) -> None:
        self.error_label.setText(message)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.cancel_connection()
        event.accept()


def run() -> None:
    application = QApplication(sys.argv)
    window = ChatWindow()
    window.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    run()
