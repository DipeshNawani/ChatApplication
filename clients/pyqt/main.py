import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QKeyEvent
from PyQt6.QtWidgets import QApplication, QFileDialog, QListWidgetItem, QMainWindow, QStackedWidget, QTextEdit

from .auth_client import AuthWorker
from .network_worker import SocketWorker
from .settings import load_settings, save_settings
from .theme import STYLESHEET, initials
from .ui import ChatInterface


class MessageEditor(QTextEdit):
    send_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.send_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ChatWindow(ChatInterface, QMainWindow):
    editor_class = MessageEditor

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("QuantumBytes Chat")
        self.resize(1180, 780)
        self.setMinimumSize(880, 640)
        self.setStyleSheet(STYLESHEET)
        self._auth_workers: set[AuthWorker] = set()
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
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(100)
        self.resize_timer.timeout.connect(self.render_current_room)

    def _start_auth_worker(self, worker: AuthWorker) -> None:
        # Keep each request alive until its thread finishes, including overlapping requests.
        self._auth_workers.add(worker)
        worker.finished.connect(lambda: self._auth_workers.discard(worker))
        worker.start()

    def clear_session(self) -> None:
        self.current_room = "general"
        self.room_messages = {"general": []}
        self.seen_message_ids.clear()
        self.read_message_ids.clear()
        self.last_sequence_by_room.clear()
        self.room_list.blockSignals(True)
        for index in reversed(range(self.room_list.count())):
            if self.room_list.item(index).data(Qt.ItemDataRole.UserRole) != "general":
                self.room_list.takeItem(index)
        self.room_list.setCurrentRow(0)
        self.room_list.blockSignals(False)
        self.search_results.clear()
        self.search_results.hide()
        self.refresh_rooms()
        self.update_header()
        self.composer.clear()
        self.render_current_room()

    def member_added(self, payload: dict[str, Any]) -> None:
        self.member_error.hide()
        self.member_feedback.setText(f"{self.member_input.text().strip()} was added to the group.")
        self.member_input.clear()

    def normalized_server_url(self) -> str:
        server_url = self.server_url_input.text().strip()
        if not server_url:
            return ""
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
            self.auth_failed({"code": "MISSING_DETAILS", "message": "Server address, username, and password are required."})
            return
        save_settings(server_url, username)
        self.login_status.setText("Connecting...")
        self.login_error.clear()
        self.login_error.hide()
        self.login_button.setEnabled(False)
        self.register_button.setEnabled(False)
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)
        self.auth_worker = AuthWorker(mode, server_url, username, password)
        self.auth_worker.succeeded.connect(self.auth_succeeded)
        self.auth_worker.failed.connect(self.auth_failed)
        self._start_auth_worker(self.auth_worker)

    def auth_succeeded(self, payload: dict[str, Any]) -> None:
        self.token = str(payload["access_token"])
        self.clear_session()
        self.current_username = str(payload["user"]["username"])
        self.account_name.setText(self.current_username)
        self.account_avatar.setText(initials(self.current_username))
        self.login_button.setEnabled(True)
        self.register_button.setEnabled(True)
        self.cancel_button.hide()
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
        mode = self.auth_worker.mode if self.auth_worker else "login"
        self.login_status.setText("Registration unsuccessful" if mode == "register" else "Sign-in unsuccessful")
        self.login_error.show()
        self.login_button.setEnabled(True)
        self.register_button.setEnabled(True)
        self.cancel_button.hide()
        self.login_error.setText(f"{error.get('code', 'AUTH_ERROR')}: {error.get('message', 'Authentication failed')}")

    def cancel_connection(self) -> None:
        for request_worker in list(self._auth_workers):
            for signal in (request_worker.succeeded, request_worker.failed):
                try:
                    signal.disconnect()
                except TypeError:
                    pass
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        self.auth_worker = None
        self.worker = None
        self.cancel_button.setEnabled(False)
        self.login_status.setText("Offline")
        self.login_button.setEnabled(True)
        self.register_button.setEnabled(True)
        self.cancel_button.hide()

    def authentication_failed(self, reason: str) -> None:
        self.login_error.setText(f"{reason}: Please log in again")
        self.login_error.show()
        self.cancel_connection()
        self.stack.setCurrentWidget(self.login_page)

    def connection_state_changed(self, state: str) -> None:
        self.login_status.setText(state)
        self.chat_status.setText(state)
        self.chat_status.setProperty("online", state == "Connected")
        self.chat_status.style().unpolish(self.chat_status)
        self.chat_status.style().polish(self.chat_status)
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
            self.stop_typing()
            self.current_room = str(current.data(Qt.ItemDataRole.UserRole) or current.text())
            self.update_header()
            self.room_messages.setdefault(self.current_room, [])
            self.render_current_room()
            if self.worker:
                self.worker.join_room(self.current_room)

    def search_users(self) -> None:
        query = self.search_input.text().strip()
        if not query or not self.token:
            return
        self.search_results.clear()
        self.search_results.show()
        self.auth_worker = AuthWorker("search", self.normalized_server_url(), token=self.token, query=query)
        self.auth_worker.succeeded.connect(self.show_search_results)
        self.auth_worker.failed.connect(self.show_search_error)
        self._start_auth_worker(self.auth_worker)

    def load_rooms(self) -> None:
        self.auth_worker = AuthWorker("rooms", self.normalized_server_url(), token=self.token)
        self.auth_worker.succeeded.connect(self.show_rooms)
        self.auth_worker.failed.connect(self.show_search_error)
        self._start_auth_worker(self.auth_worker)

    def show_rooms(self, payload: dict[str, Any]) -> None:
        for room in payload.get("rooms", []):
            if room.get("room_id") != "general":
                self.add_room(room["room_id"], room["name"], select=False)

    def create_group(self) -> None:
        name = self.group_name_input.text().strip()
        if not name or not self.token:
            return
        self.auth_worker = AuthWorker("group", self.normalized_server_url(), token=self.token, query=name)
        self.auth_worker.succeeded.connect(lambda payload: self.add_room(payload["room"]["room_id"], payload["room"]["name"]))
        self.auth_worker.failed.connect(self.show_search_error)
        self._start_auth_worker(self.auth_worker)

    def add_group_member(self) -> None:
        username = self.member_input.text().strip()
        if not username or not self.token or not self.current_room.startswith("group-"):
            return
        self.auth_worker = AuthWorker("member", self.normalized_server_url(), username=username, token=self.token, query=self.current_room)
        self.auth_worker.failed.connect(self.show_search_error)
        self.auth_worker.succeeded.connect(self.member_added)
        self._start_auth_worker(self.auth_worker)

    def leave_group(self) -> None:
        if not self.token or not self.current_room.startswith("group-"):
            return
        self.auth_worker = AuthWorker("leave", self.normalized_server_url(), token=self.token, query=self.current_room)
        self.auth_worker.failed.connect(self.show_search_error)
        self._start_auth_worker(self.auth_worker)

    def show_search_results(self, payload: dict[str, Any]) -> None:
        self.search_results.clear()
        self.search_results.show()
        for user in payload.get("users", []):
            item = QListWidgetItem(user["username"])
            item.setData(Qt.ItemDataRole.UserRole, user["username"])
            self.search_results.addItem(item)

    def open_direct_chat(self, item: QListWidgetItem) -> None:
        username = str(item.data(Qt.ItemDataRole.UserRole))
        self.auth_worker = AuthWorker("direct", self.normalized_server_url(), token=self.token, query=username)
        self.auth_worker.succeeded.connect(lambda payload: self.add_room(payload["room"]["room_id"], payload["room"]["name"]))
        self.auth_worker.failed.connect(self.show_search_error)
        self._start_auth_worker(self.auth_worker)

    def add_room(self, room_id: str, name: str, select: bool = True) -> None:
        matches = [self.room_list.item(index) for index in range(self.room_list.count()) if self.room_list.item(index).data(Qt.ItemDataRole.UserRole) == room_id]
        if not matches:
            item = QListWidgetItem("")
            item.setData(Qt.ItemDataRole.UserRole, room_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, name)
            self.room_list.addItem(item)
        else:
            item = matches[0]
            item.setData(Qt.ItemDataRole.UserRole + 1, name)
        self._paint_room(item)
        self.room_count.setText(f"CONVERSATIONS   {self.room_list.count()}")
        if select:
            self.room_list.setCurrentItem(item)
            self.current_room = room_id
            self.update_header()
            if self.group_dialog.isVisible():
                self.group_dialog.accept()
                self.group_name_input.clear()
        self.room_messages.setdefault(room_id, [])
        if self.worker:
            self.worker.join_room(room_id)

    def receive_room_added(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        if data.get("room_id") and data.get("name"):
            self.add_room(data["room_id"], data["name"], select=False)

    def receive_room_removed(self, payload: dict[str, Any]) -> None:
        room_id = payload.get("data", {}).get("room_id")
        for index in reversed(range(self.room_list.count())):
            if self.room_list.item(index).data(Qt.ItemDataRole.UserRole) == room_id:
                self.room_list.takeItem(index)
        self.room_messages.pop(room_id, None)
        self.members_dialog.accept()
        self.refresh_rooms()
        if room_id == self.current_room:
            self.current_room = "general"
            self.update_header()
            self.render_current_room()

    def show_search_error(self, error: dict[str, Any]) -> None:
        self.show_error(f"{error.get('code', 'REQUEST_ERROR')}: {error.get('message', 'Request failed')}")

    def send_message(self) -> None:
        text = self.composer.toPlainText().strip()
        if not text or not self.worker:
            return
        client_message_id = f"client-{uuid4().hex}"
        message = {"message_id": None, "client_message_id": client_message_id, "room_id": self.current_room, "sender": {"username": self.current_username}, "mine": True, "kind": "text", "text": text, "occurred_at": datetime.now(timezone.utc).isoformat(), "status": "pending"}
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
        self._start_auth_worker(self.auth_worker)

    def send_file_reference(self, file_info: dict[str, Any]) -> None:
        client_message_id = f"client-{uuid4().hex}"
        kind = "image" if str(file_info.get("content_type", "")).startswith("image/") else "file"
        message = {"message_id": None, "client_message_id": client_message_id, "room_id": self.current_room, "sender": {"username": self.current_username}, "mine": True, "kind": kind, "text": "", "file": file_info, "occurred_at": datetime.now(timezone.utc).isoformat(), "status": "pending"}
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
        self._start_auth_worker(worker)

    def receive_typing(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        if data.get("room_id") == self.current_room:
            self.typing_status.setText(f"{data.get('username')} is typing..." if data.get("is_typing") else "")

    def receive_presence(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        if data.get("room_id") != self.current_room:
            return
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
        self.refresh_rooms()
        if room_id == self.current_room:
            self.render_current_room()

    def receive_message(self, payload: dict[str, Any]) -> None:
        data = dict(payload.get("data", {}))
        if payload.get("occurred_at"):
            data["occurred_at"] = payload["occurred_at"]
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
        self.refresh_rooms()
        if room_id == self.current_room:
            self.render_current_room()

    def receive_ack(self, payload: dict[str, Any]) -> None:
        data = payload.get("data", {})
        request_id = payload.get("request_id")
        message = next((item for messages in self.room_messages.values() for item in messages if item.get("client_message_id") == request_id), None)
        if data.get("code"):
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
        if self.group_dialog.isVisible():
            self.group_error.setText(message)
            self.group_error.show()
        elif self.members_dialog.isVisible():
            self.member_error.setText(message)
            self.member_error.show()
        else:
            self.error_label.setText(message)
            self.error_label.show()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.cancel_connection()
        if self._auth_workers:
            event.ignore()
            self.login_status.setText("Finishing current request…")
            QTimer.singleShot(100, self.close)
            return
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "resize_timer"):
            self.resize_timer.start()


def run() -> None:
    application = QApplication(sys.argv)
    application.setStyle("Fusion")
    application.setApplicationName("QuantumBytes Chat")
    window = ChatWindow()
    window.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    run()
