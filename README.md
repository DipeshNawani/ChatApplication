# QuantumBytes Chat

QuantumBytes Chat is a desktop messaging application with a shared FastAPI and
Socket.IO backend, a PyQt6 client, and an Electron client. Both clients use the
same server API and event protocol.

## Features

- Account registration and login with JWT authentication
- Direct conversations and group rooms with owner-managed membership
- Persistent message history, reconnect handling, and duplicate-send protection
- Typing indicators, online presence, and delivery/read status
- File and image attachments with type validation and a 5 MiB upload limit
- PyQt6 and Electron desktop clients

## Architecture

- `server/`: FastAPI, Socket.IO, SQLAlchemy, and Alembic migrations
- `clients/pyqt/`: PyQt6 desktop application and threaded socket worker
- `clients/electron/`: Electron application with isolated renderer and preload API
- `docs/`: architecture, protocol, decisions, and implementation learnings

The local development database is SQLite. Hosted deployments use PostgreSQL,
including the PostgreSQL database provided by Supabase. See
[docs/PROTOCOL.md](docs/PROTOCOL.md) for the API and Socket.IO event contract.

## Requirements

- Windows 10 or later for the desktop clients
- Python 3.13.4, as specified by `.python-version`
- Node.js and npm to run or package the Electron client

## Local Development

Run the following commands from the repository root in PowerShell:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r server\requirements.txt
.venv\Scripts\python.exe -m pip install -r clients\pyqt\requirements.txt
Copy-Item server\.env.example server\.env
```

Edit `server\.env` and replace the `JWT_SECRET` placeholder with a random
secret of at least 32 characters. To generate one locally:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep `DATABASE_PATH=server/data/chat.db` for local SQLite development. Do not
put a hosted database URL or any real credentials in `config.py`. Apply the
database migrations and start the server:

```powershell
.venv\Scripts\python.exe -m alembic -c server\alembic.ini upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:socket_app --app-dir server --env-file server\.env --host 127.0.0.1 --port 8000
```

Leave the server running. In another PowerShell terminal, start the PyQt6
client:

```powershell
.venv\Scripts\python.exe -m clients.pyqt.main
```

Or start the Electron client in another terminal:

```powershell
Push-Location clients\electron
npm ci
npm start
Pop-Location
```

Use `http://127.0.0.1:8000` as the server URL in the client. Client settings
store the server URL and username; passwords are not saved, and authentication
tokens remain in memory or the Electron main process.

## Tests

Run Python tests from the repository root:

```powershell
$env:PYTHONPATH = 'server'
$env:QT_QPA_PLATFORM = 'offscreen'
.venv\Scripts\python.exe -m pytest -q
```

Run Electron tests:

```powershell
Push-Location clients\electron
npm test
Pop-Location
```

## Windows Packages

Build the PyQt6 executable:

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\pyinstaller.exe clients\pyqt\QuantumBytesChat.spec
```

Build the Electron portable ZIP:

```powershell
Push-Location clients\electron
npm ci
npm run dist
Pop-Location
```

The Electron build is configured as a portable ZIP. The local NSIS installer
build exceeded the available memory-mapped archive limit. Packaged Electron
builds are unsigned; obtain a code-signing certificate before public release.

## Deployment: Render and Supabase

The root `render.yaml` defines a Render web-service Blueprint. It installs the
server dependencies, applies Alembic migrations at startup, and exposes the
`/health` endpoint. Supabase supplies the hosted PostgreSQL database; a
separate PostgreSQL installation is not required.

1. Push this repository to GitHub and create a Blueprint in Render from it.
2. In Supabase, open **Connect** and copy a PostgreSQL connection URI. Use the
   Session pooler URI for the Render connection when available. Replace its
   password placeholder with the Supabase database password.
3. In the Render service's **Environment** settings, set `DATABASE_URL` to
   that complete URI. Do not put it in `config.py`, commit it, or use Supabase
   API keys in its place.
4. Keep the Blueprint-generated `JWT_SECRET`. Keep `DEV_MODE` disabled. The
   Blueprint provides the remaining defaults, including `PORT` handling and
   trusted proxy configuration.
5. Deploy and confirm that `https://<your-render-service>/health` returns
   `{"status":"ok","dev_mode":false}`.
6. Enter the Render HTTPS service URL in the Server URL field in each desktop
   client.

Do not commit `.env` files, JWT secrets, database URLs, passwords, or access
tokens. If a credential has been exposed, rotate it before deployment.

Render's filesystem is ephemeral, so uploaded files may be lost after a
restart or redeploy. Configure persistent object storage before relying on
hosted file retention. See [docs/PROGRESS.md](docs/PROGRESS.md) for current
deployment status and [server/README.md](server/README.md) for server-specific
notes.
