# QuantumBytes Chat

A desktop chat learning project with one FastAPI + Socket.IO server, a PyQt6
client, and a secure Electron client. Both clients use the same event contract
in [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Windows setup

Run commands from the `quantumbytestask` repository folder.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r server\requirements.txt
.venv\Scripts\python.exe -m pip install -r clients\pyqt\requirements.txt
Copy-Item server\.env.example server\.env
```

For local development, set `JWT_SECRET` in `server/.env` to a random value of
at least 32 characters. Keep `DEV_MODE` off; the automated tests monkeypatch
the test-only identity instead. Then apply migrations and launch:

```powershell
.venv\Scripts\python.exe -m alembic -c server\alembic.ini upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:socket_app --app-dir server --env-file server/.env --host 127.0.0.1 --port 8000
```

### PyQt6 client

In another PowerShell terminal, from the repository folder:

```powershell
.venv\Scripts\python.exe -m clients.pyqt.main
```

The settings file stores server URL and username only. Passwords are never
saved; the JWT remains in memory.

### Electron client

```powershell
Push-Location clients\electron
npm install
npm start
Pop-Location
```

## LAN testing

Start the server with `--host 0.0.0.0 --port 8000`. Set the client server URL
to the server computer's LAN IP, such as `http://192.168.1.20:8000`. Allow
Python through Windows Defender Firewall on Private networks only.

## Tests

```powershell
$env:PYTHONPATH='server'
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -m pytest -v server\tests clients\pyqt\tests
Push-Location clients\electron
npm test
Pop-Location
```

## Package builds

PyQt6:

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\pyinstaller.exe clients\pyqt\QuantumBytesChat.spec
```

Electron:

```powershell
Push-Location clients\electron
npm run dist
Pop-Location
```

This builds a portable Windows ZIP. The local NSIS build exceeded the
available memory-mapped archive limit; the target can be switched to NSIS in a
release build environment with more available memory.

## Deployment notes

`render.yaml` is a Render Free web-service Blueprint. It runs migrations at
startup, binds to Render's `PORT`, enables trusted proxy IP handling, and
requires `DATABASE_URL` from Supabase PostgreSQL. Render Free has an ephemeral
filesystem, so uploaded files in `UPLOAD_DIRECTORY` disappear on restart or
redeploy. Use object storage before relying on file persistence.

### Steps for Legend

1. Create a Supabase project and copy its PostgreSQL connection URI. Use the
   session pooler URI if the direct endpoint is not reachable from Render.
2. Create/import the `render.yaml` Blueprint in Render.
3. In the Render service environment, set `DATABASE_URL` to the Supabase URI,
   set `CORS_ORIGINS` to the approved origins (no wildcard), and verify
   `DEV_MODE=false` and a generated `JWT_SECRET` of at least 32 characters.
4. Deploy and wait for `/health` to return `{"status":"ok","dev_mode":false}`.
5. Set the hosted HTTPS URL in both desktop clients and test login, direct and
   group chat, reconnect, and upload limits.
6. Configure Supabase Storage or another persistent object store before
   expecting uploaded files to survive Render restarts.
7. For packaged desktop builds, use the commands in Package builds above;
   configure the hosted URL in each app's settings screen.
8. The Electron installer is unsigned because no code-signing certificate is
   available. Windows may show SmartScreen warnings; a release publisher must
   sign the installer before public distribution.

Do not commit `.env`, JWT secrets, Supabase connection strings, user passwords,
or access tokens.
