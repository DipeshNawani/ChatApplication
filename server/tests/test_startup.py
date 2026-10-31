"""Verify the supported launcher and both client authentication transports."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import threading
import runpy
import urllib.error
import urllib.request


def test_launcher_does_not_treat_another_service_as_chat():
    class OtherService(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"} if self.path == "/health" else {"info": {"title": "Another application"}}).encode())

        def log_message(self, *args):
            pass

    import pytest
    runner = runpy.run_path(str(Path(__file__).parents[1] / "run.py"))
    with ThreadingHTTPServer(("127.0.0.1", 0), OtherService) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with pytest.raises(SystemExit, match="not a healthy QuantumBytes backend"):
                runner["check_existing_server"]("127.0.0.1", server.server_port)
        finally:
            server.shutdown()
            thread.join(timeout=3)


def test_launcher_and_client_authentication_from_another_directory(tmp_path):
    project = Path(__file__).parents[2]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    environment = dict(os.environ, DATABASE_PATH=str(tmp_path / "chat.db"), JWT_SECRET="startup-test-secret-0123456789abcdef", HOST="127.0.0.1", PORT=str(port))
    environment.pop("DATABASE_URL", None)
    with (tmp_path / "startup.log").open("w+") as log:
        process = subprocess.Popen([sys.executable, str(project / "server/run.py")], cwd=tmp_path, env=environment, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    log.seek(0)
                    raise AssertionError(log.read())
                try:
                    with urllib.request.urlopen(base_url + "/health", timeout=0.3) as response:
                        assert json.load(response)["status"] == "ok"
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.05)
            else:
                log.seek(0)
                raise AssertionError("Server did not start: " + log.read())

            duplicate = subprocess.run([sys.executable, str(project / "server/run.py")], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
            assert duplicate.returncode == 0, duplicate.stdout + duplicate.stderr
            assert "already running" in duplicate.stdout

            from clients.pyqt.auth_client import AuthWorker
            for mode in ("register", "login"):
                successes, failures = [], []
                worker = AuthWorker(mode, base_url, "python_auth_check", "password-123")
                worker.succeeded.connect(successes.append)
                worker.failed.connect(failures.append)
                worker.run()
                assert not failures, failures
                assert successes[0]["user"]["username"] == "python_auth_check"
                assert successes[0]["access_token"]

            script = """
const { createApiRequest } = require('./clients/electron/src/api-client');
const request = createApiRequest({getServerUrl: () => process.argv[1]});
(async () => {
  for (const mode of ['register', 'login']) {
    const result = await request(`/api/v1/auth/${mode}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:'electron_auth_check',password:'password-123'})});
    if (!result.access_token || result.user.username !== 'electron_auth_check') throw new Error('Authentication response invalid');
  }
  console.log('Electron registration and login passed');
})().catch(error => { console.error(error.message); process.exitCode=1; });
"""
            result = subprocess.run(["node", "-e", script, base_url], cwd=project, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stdout + result.stderr
        finally:
            process.terminate()
            process.wait(timeout=10)
