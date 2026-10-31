"""Run widget checks separately from the networking suite's QCoreApplication."""
import os
from pathlib import Path
import subprocess
import sys


def test_chat_interface_lifecycle() -> None:
    script = r'''
from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtWidgets import QApplication, QLabel
from clients.pyqt import main

main.load_settings = lambda: {'server_url':'http://127.0.0.1:8000','username':''}
app = QApplication([])
window = main.ChatWindow()
window.show()
app.processEvents()
window.auth_failed({'code':'INVALID_CREDENTIALS','message':'Invalid username or password'})
assert window.login_status.text() == 'Sign-in unsuccessful'
assert 'Invalid username or password' in window.login_error.text()
assert not window.send_button.isEnabled()
window.composer.setPlainText('A message')
assert window.send_button.isEnabled()
window.password_input.setText('private-password')
window.password_toggle.click()
assert window.password_input.echoMode() == window.password_input.EchoMode.Normal
window.password_toggle.click()
assert window.password_input.echoMode() == window.password_input.EchoMode.Password
window.current_username = 'alice'
window.stack.setCurrentWidget(window.chat_page)
window.add_room('group-test', 'Product team')
window.show_rooms({'rooms':[{'room_id':'direct-other','name':'Other person'}]})
assert window.current_room == 'group-test'
assert window.room_title.text() == 'Product team'
window.room_messages['group-test'] = [{'message_id':'m1','sender':{'username':'bob'},'kind':'text','text':'<b>Literal message text</b>','occurred_at':'2026-10-30T10:00:00Z'}]
window.render_current_room()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
bodies = window.message_container.findChildren(QLabel, 'messageText')
assert len(bodies) == 1
assert bodies[0].textFormat() == Qt.TextFormat.PlainText
assert bodies[0].text() == '<b>Literal message text</b>'
window.group_dialog.open()
app.processEvents()
window.show_error('Please choose another name')
assert window.group_error.text() == 'Please choose another name'
assert window.group_error.isVisible()
window.group_dialog.reject()
window.clear_session()
assert window.room_list.count() == 1
assert window.room_messages == {'general': []}
assert not window.composer.toPlainText()
window.close()
'''
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parents[3], env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
