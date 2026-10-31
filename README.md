<div align="center">

# 💬 QuantumBytes Chat

### A real-time desktop messaging platform with one shared backend and two desktop clients

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Socket.IO](https://img.shields.io/badge/Socket.IO-010101?style=for-the-badge&logo=socketdotio&logoColor=white)](https://socket.io/)
[![PyQt6](https://img.shields.io/badge/PyQt6-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![Electron](https://img.shields.io/badge/Electron-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://www.electronjs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Render](https://img.shields.io/badge/Hosting-Render-46E3B7?style=for-the-badge&logo=render&logoColor=black)](https://render.com/)

[Features](#-features) • [Architecture](#-architecture) • [Getting Started](#-getting-started) • [Testing](#-testing) • [Packaging](#-windows-packaging) • [Deployment](#-deployment) • [Documentation](#-documentation)

</div>

---

## 📖 Overview

**QuantumBytes Chat** is a desktop messaging application built around a single **FastAPI + Socket.IO** backend. Two independent desktop clients, one written in **PyQt6** and one in **Electron**, connect to the same server API and share the same event protocol, so users get an identical experience whichever client they choose.

---

## ✨ Features

| | Feature | Description |
|---|---|---|
| 🔐 | **Secure Authentication** | Account registration and login backed by JWT tokens |
| 💬 | **Direct & Group Chat** | One-to-one conversations and group rooms with owner-managed membership |
| 🗂️ | **Persistent History** | Messages are stored and restored, with reconnect handling and duplicate-send protection |
| ⌨️ | **Live Presence** | Typing indicators, online presence, and delivery/read status |
| 📎 | **Attachments** | File and image sharing with type validation and a 5 MiB upload limit |
| 🖥️ | **Two Desktop Clients** | A PyQt6 client and an Electron client on one shared protocol |

---

## 🏗️ Architecture

```text
ChatApplication/
├── server/              # FastAPI, Socket.IO, SQLAlchemy, Alembic migrations
├── clients/
│   ├── pyqt/            # PyQt6 desktop app with a threaded socket worker
│   └── electron/        # Electron app with isolated renderer and preload API
├── docs/                # Architecture, protocol, decisions, and learnings
├── render.yaml          # Render Blueprint for hosted deployment
└── .python-version      # Pinned Python version
```

| Layer | Technology |
|---|---|
| **API & Realtime** | FastAPI, Socket.IO |
| **Data Access** | SQLAlchemy, Alembic |
| **Database** | SQLite (local development), PostgreSQL (hosted, via Supabase) |
| **Desktop Clients** | PyQt6, Electron |
| **Hosting** | Render |

> 📡 The full API and Socket.IO event contract is documented in [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

---

## 🚀 Getting Started

### 📋 Prerequisites

- 🪟 **Windows 10 or later** for the desktop clients
- 🐍 **Python 3.13.4** (as specified in `.python-version`)
- 🟢 **Node.js and npm** to run or package the Electron client

### ⚙️ 1. Set Up the Environment

Run the following from the repository root in **PowerShell**:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r server\requirements.txt
.venv\Scripts\python.exe -m pip install -r clients\pyqt\requirements.txt
Copy-Item server\.env.example server\.env
```

### 🔑 2. Configure Secrets

Open `server\.env` and replace the `JWT_SECRET` placeholder with a random secret of **at least 32 characters**. To generate one:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep `DATABASE_PATH=server/data/chat.db` for local SQLite development.

> ⚠️ **Never** put a hosted database URL or real credentials in `config.py`.

### 🗄️ 3. Start the Server

```powershell
.\start-server.ps1
```

This loads `server/.env` and applies pending database migrations. You can also
run `.venv\Scripts\python.exe server\run.py` directly. Leave the server running
and open a second PowerShell terminal for a client. Both login and registration
need this backend; launching a client alone does not start it.

### 🖥️ 4. Launch a Client

**Option A: PyQt6 client**

```powershell
.venv\Scripts\python.exe -m clients.pyqt.main
```

**Option B: Electron client**

```powershell
Push-Location clients\electron
npm ci
npm start
Pop-Location
```

For a new installation, the clients default to the hosted server, so no local
backend is required for a multi-device chat. The server address is
**`https://quantumbytes-chat.onrender.com`**.

For local-only development, enter **`http://127.0.0.1:8000`** instead and run
`start-server.ps1` on the same computer.

To chat from different computers using Render, run a desktop client on each
computer and enter **`https://quantumbytes-chat.onrender.com`** in the GUI's
**Server address** field on both computers. Keep the normal client launch
commands above; do not put the Render URL into `start-server.ps1`. The local
server is not needed when the clients use Render. Each person registers an
account on Render, then searches for the other username to start a chat.
Local and Render accounts and message history belong to separate databases.
The Render URL hosts the backend API, not the desktop interface.

> 🔒 **Privacy by design:** client settings store only the server URL and username. Passwords are never saved, and authentication tokens stay in memory (or in the Electron main process).

---

## 🧪 Testing

**Python tests** (from the repository root):

```powershell
$env:PYTHONPATH = 'server'
$env:QT_QPA_PLATFORM = 'offscreen'
.venv\Scripts\python.exe -m pytest -q
```

**Electron tests:**

```powershell
Push-Location clients\electron
npm test
Pop-Location
```

---

## 📦 Windows Packaging

**PyQt6 executable**

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\pyinstaller.exe clients\pyqt\QuantumBytesChat.spec
```

**Electron portable ZIP**

```powershell
Push-Location clients\electron
npm ci
npm run dist
Pop-Location
```

The rebuilt Windows packages are produced at:

- `clients/electron/dist/QuantumBytes Chat-0.1.0-win.zip`
- `dist/QuantumBytesChat.exe`

Upload either file to a GitHub Release, Google Drive, OneDrive, or another
file host. On each Windows computer, download and run the same client, leave
the server address as **`https://quantumbytes-chat.onrender.com`**, and create
an account on that hosted server. Do not upload `server/.env` or any database
file; those may contain secrets or local-only data.

> ℹ️ The Electron build is configured as a **portable ZIP**, because the local NSIS installer build exceeded the available memory-mapped archive limit.
>
> ⚠️ Packaged Electron builds are **unsigned**. Obtain a code-signing certificate before any public release.

---

## ☁️ Deployment

The root [`render.yaml`](render.yaml) defines a **Render web-service Blueprint**. It installs server dependencies, applies Alembic migrations at startup, and exposes a `/health` endpoint. **Supabase** supplies the hosted PostgreSQL database, so no separate PostgreSQL installation is required.

### Deployment Steps

1. **Create the Blueprint.** Push this repository to GitHub, then create a Blueprint in Render from it.
2. **Get the database URI.** In Supabase, open **Connect** and copy a PostgreSQL connection URI. Prefer the **Session pooler** URI when available, and replace its password placeholder with your Supabase database password.
3. **Set `DATABASE_URL`.** In the Render service's **Environment** settings, set `DATABASE_URL` to that complete URI. Do not put it in `config.py`, commit it, or substitute Supabase API keys.
4. **Keep the defaults.** Keep the Blueprint-generated `JWT_SECRET` and leave `DEV_MODE` disabled. The Blueprint provides the remaining defaults, including `PORT` handling and trusted proxy configuration.
5. **Verify the deploy.** Confirm that `https://<your-render-service>/health` returns:
   ```json
   {"status": "ok", "dev_mode": false}
   ```
6. **Connect the clients.** Enter the Render HTTPS service URL in the **Server URL** field of each desktop client.

### 🛡️ Security Notes

- Never commit `.env` files, JWT secrets, database URLs, passwords, or access tokens.
- If a credential has been exposed, **rotate it before deploying**.

### ⚠️ Known Limitation

Render's filesystem is **ephemeral**, so uploaded files may be lost after a restart or redeploy. Configure persistent object storage before relying on hosted file retention.

---

## 📚 Documentation

| Document | Contents |
|---|---|
| [`docs/PROTOCOL.md`](docs/PROTOCOL.md) | API and Socket.IO event contract |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Current deployment status |
| [`server/README.md`](server/README.md) | Server-specific notes |

---

<div align="center">

**Built by [Dipesh Nawani](https://github.com/DipeshNawani)**

⭐ If you find this project useful, consider giving it a star!
</div>
