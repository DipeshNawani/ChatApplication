"""Shared visual tokens and local vector icons for the desktop interface."""
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QLabel


STYLESHEET = """
QMainWindow, QDialog { background: #f6f8f9; }
QWidget { font-family: 'Segoe UI'; font-size: 13px; color: #20333d; }
QLabel { background: transparent; border: none; }
QLabel#muted { color: #75848b; font-size: 11px; }
QLabel#eyebrow { color: #197d70; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QLabel#heading { font-size: 28px; font-weight: 600; }
QLabel#sectionTitle { font-size: 22px; font-weight: 600; }
QLabel#sectionLabel { color: #75848b; font-size: 10px; font-weight: 600; letter-spacing: 1px; }
QLabel#roomTitle { font-size: 17px; font-weight: 600; }
QLabel#rowTitle { font-size: 12px; font-weight: 600; }
QLabel#rowPreview { font-size: 10px; color: #75848b; }
QLabel#avatar { background: #e5f1ed; color: #197d70; border-radius: 11px; font-weight: 600; }
QLabel#accountAvatar { background: #142b36; color: white; border-radius: 17px; font-size: 11px; font-weight: 600; }
QLabel#brandMark { background: #197d70; color: white; border-radius: 11px; font-size: 17px; font-weight: 700; }
QLabel#connectionStatus { color: #75848b; font-size: 10px; }
QLabel#connectionStatus[online="true"] { color: #197d70; }
QWidget#story, QWidget#rail { background: #142b36; }
QWidget#story QLabel { color: #d8e4e8; }
QWidget#story QLabel#storyTitle { color: #f4f8f8; font-size: 42px; font-weight: 600; }
QWidget#story QLabel#storyBody { color: #b2c3cb; font-size: 13px; }
QWidget#story QLabel#storyKicker { color: #8dd6c5; font-size: 10px; letter-spacing: 1px; }
QWidget#story QLabel#storyFooter { color: #9fb4bd; font-size: 10px; }
QWidget#loginPanel, QWidget#sidebar, QWidget#conversationHeader, QWidget#account { background: white; }
QWidget#sidebar { border-right: 1px solid #e5ebed; }
QWidget#conversationHeader { border-bottom: 1px solid #e5ebed; }
QWidget#account { border-top: 1px solid #e5ebed; }
QWidget#conversation, QWidget#messageContainer { background: #f6f8f9; }
QLineEdit { background: white; border: 1px solid #dbe3e6; border-radius: 8px; padding: 10px 12px; min-height: 18px; selection-background-color: #b9dfd4; }
QLineEdit:focus { border: 1px solid #197d70; }
QLineEdit#searchInput { background: #f6f8f9; font-size: 11px; }
QPushButton { border: 1px solid transparent; background: #197d70; color: white; border-radius: 8px; padding: 10px 15px; font-weight: 600; }
QPushButton:hover { background: #126658; }
QPushButton:pressed { background: #0e5449; }
QPushButton:focus { border: 1px solid #79b8ac; }
QPushButton:disabled { background: #e1e8e9; color: #87969d; }
QPushButton#secondary { background: white; color: #20333d; border: 1px solid #e5ebed; }
QPushButton#secondary:hover { background: #f0f4f5; }
QPushButton#ghost { background: transparent; color: #75848b; padding: 8px; }
QPushButton#ghost:hover { background: #edf2f3; }
QPushButton#railButton { background: transparent; padding: 10px; }
QPushButton#railButton:hover, QPushButton#railActive { background: #284650; padding: 10px; }
QPushButton#danger { background: #fff0ed; color: #a93b36; }
QPushButton#danger:hover { background: #f9e1dc; }
QPushButton#older { background: white; color: #75848b; border: 1px solid #e5ebed; border-radius: 13px; font-size: 10px; padding: 5px 13px; }
QListWidget { border: none; background: transparent; outline: none; padding: 0 10px; }
QListWidget::item { border: none; border-radius: 8px; margin: 2px 0; padding: 4px; }
QListWidget::item:hover { background: #f4f7f8; }
QListWidget::item:selected { background: #edf6f3; color: #20333d; }
QScrollArea { border: none; background: #f6f8f9; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }
QScrollBar::handle:vertical { background: #d2dcdf; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QWidget#composerBox { background: white; border: 1px solid #dbe4e6; border-radius: 12px; }
QTextEdit { background: transparent; border: none; padding: 7px 0; selection-background-color: #b9dfd4; }
QWidget#incomingBubble { background: white; border: 1px solid #e5ebed; border-radius: 12px; }
QWidget#outgoingBubble { background: #e1f1ec; border: 1px solid #d4e9e1; border-radius: 12px; }
QWidget#outgoingBubble QLabel#messageText { color: #234a40; }
QLabel#messageText { font-size: 13px; }
QLabel#messageAuthor { color: #627680; font-size: 10px; font-weight: 600; }
QLabel#messageMeta, QLabel#dateDivider { color: #75848b; font-size: 10px; }
QLabel#typing { color: #197d70; font-size: 11px; }
QLabel#error { background: #fff0ed; color: #a93b36; border-radius: 8px; padding: 10px 14px; font-size: 11px; }
QToolTip { background: #142b36; color: white; border: none; padding: 6px 9px; }
"""

PATHS = {
    "chat": '<path d="M21 11a9 9 0 0 1-9 9 10 10 0 0 1-4-.9L3 21l1.9-5A10 10 0 0 1 4 12a9 9 0 0 1 17-1Z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    "send": '<path d="m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13"/>',
    "attach": '<path d="m21 11-8.5 8.5a6 6 0 0 1-8.5-8.5l9-9a4 4 0 0 1 5.7 5.7l-9 9a2 2 0 0 1-2.8-2.8L15 6"/>',
    "users": '<circle cx="9" cy="7" r="4"/><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M22 21v-2a4 4 0 0 0-3-4M16 3a4 4 0 0 1 0 8"/>',
    "settings": '<path d="M12 3 14 6l3-.2 1.7 3-1.6 2.7 1.6 2.7-1.7 3-3-.2-2 3-2-3-3 .2-1.7-3 1.6-2.7L5.3 9 7 6l3 .2 2-3Z"/><circle cx="12" cy="11.5" r="3"/>',
    "arrow": '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5"/>',
}


def icon(name: str, color: str = "#75848b") -> QIcon:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def initials(name: str) -> str:
    return "".join(part[0] for part in name.replace("_", " ").replace("-", " ").split()[:2]).upper() or "?"
