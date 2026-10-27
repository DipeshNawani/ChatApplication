# QuantumBytes Chat Protocol

Protocol version: `1`

This document is the implementation contract for the Python and Electron
clients. Event names are stable across development identity and future JWT
authentication.

## Connection

- Local URL: `http://127.0.0.1:8000`
- LAN URL: `http://<server-lan-ip>:8000`
- Hosted URL: `https://<render-service>.onrender.com`
- Health check: `GET /health`
- Socket.IO authentication: `auth: {"token": "<short-lived-jwt>"}`

DEV_MODE is test-only and cannot be enabled through normal environment
configuration. Automated tests may explicitly patch it and connect with
`auth: {"username": "alice"}`. Normal clients always use JWTs.

For a local run, create `server/.env` with:

```env
JWT_SECRET=replace-with-a-random-secret-at-least-32-characters
JWT_EXPIRE_MINUTES=60
DATABASE_PATH=server/data/chat.db
HOST=127.0.0.1
PORT=8000
```

Start the server from the repository root with:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:socket_app --app-dir server --env-file server/.env
```

The access-token lifetime is 60 minutes by default and is configured with
`JWT_EXPIRE_MINUTES`; there is no refresh token. Passwords are never stored by
either desktop client. DEV_MODE belongs in test configuration only.

For a LAN run, execute this from the `quantumbytestask` folder so other
devices can reach the server:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:socket_app --app-dir server --env-file server/.env --host 0.0.0.0 --port 8000
```

When Windows Defender Firewall asks whether Python may communicate on the
network, allow it on **Private networks**. Do not enable public-network
access unless you explicitly need it. If no prompt appears, create an
inbound Windows Firewall rule for TCP port `8000` on the Private profile.

## Envelope

Client requests use:

```json
{
  "protocol_version": 1,
  "request_id": "optional-request-id",
  "data": {}
}
```

Server events use the same envelope and may add `occurred_at` at the top level.
Clients must ignore unknown fields and unknown event names.

## Authentication REST endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register` | Create an Argon2id-hashed account and return a JWT |
| POST | `/api/v1/auth/login` | Verify credentials and return a JWT |
| GET | `/api/v1/users/search?q=...` | Search users for a direct chat |
| POST | `/api/v1/chats/direct` | Get or create the room for a user pair |
| POST | `/api/v1/rooms/groups` | Create a group and become its owner |
| POST | `/api/v1/rooms/{room_id}/members` | Owner adds a member |
| DELETE | `/api/v1/rooms/{room_id}/members/{username}` | Owner removes a member |
| POST | `/api/v1/rooms/{room_id}/leave` | Leave a group; owner transfers or closes it |
| POST | `/api/v1/files` | Upload a validated file up to 5 MB |
| GET | `/api/v1/files/{file_id}` | Download after membership verification |
| GET | `/api/v1/rooms` | List rooms the authenticated user belongs to |
| GET | `/api/v1/rooms/{room_id}/messages` | Read membership-gated cursor history |

Send the token as `Authorization: Bearer <token>` for REST and as
`auth: {"token": "<token>"}` for Socket.IO. Tokens are checked at socket
connect and on every REST request. If a reconnect finds an expired token, the
client returns to login and keeps unsent messages only in memory.

Registration accepts usernames matching `[A-Za-z0-9_-]{3,32}` and compares
them case-insensitively. `admin`, `system`, `server`, and `you` are reserved.
Passwords are 8 to 128 characters. Login failures use the same response for a
missing username and a wrong password.

## Socket.IO events

### Client to server

| Event | v1 increment | Payload purpose |
|---|---:|---|
| `session:authenticate` | 1 | Re-authenticate a socket with a JWT |
| `room:join` | 1 | Join a room by `room_id` |
| `room:leave` | 1 | Leave a room by `room_id` |
| `message:send` | 1 | Send a text message |
| `typing:set` | 3 | Set `is_typing` for a room |
| `presence:refresh` | 3 | Refresh online status |
| `message:read` | 3 | Mark a message as read |

### Server to client

| Event | v1 increment | Payload purpose |
|---|---:|---|
| `connection:state` | 1 | Connection/authentication state |
| `room:joined` | 1 | Room join confirmation |
| `room:added` | 1 | Direct room created for the other member |
| `room:removed` | 4b | Membership removed or group closed |
| `room:left` | 1 | Room leave confirmation |
| `message:created` | 1 | Saved message broadcast |
| `message:ack` | 1 | Save success or rejection |
| `typing:changed` | 3 | Typing state broadcast |
| `presence:changed` | 3 | Online/offline state broadcast |
| `message:status` | 3 | Sent/delivered/read status |
| `server:error` | 1 | Structured event error |

## Basic message flow

1. Login through REST and keep the returned JWT in memory.
2. Send `room:join`.
3. Send `message:send` with a unique `client_message_id`.
4. Receive `message:created` in every connected member of the room.
5. Receive `message:ack` on the sending socket.

Example request:

```json
{
  "protocol_version": 1,
  "request_id": "req-901",
  "data": {
    "room_id": "general",
    "client_message_id": "client-8f3c",
    "kind": "text",
    "text": "Hello from Alice"
  }
}
```

Example created event:

```json
{
  "protocol_version": 1,
  "occurred_at": "2026-10-27T15:04:05Z",
  "data": {
    "message_id": "msg-1001",
    "client_message_id": "client-8f3c",
    "room_id": "general",
    "sender": {"user_id": 7, "username": "alice"},
    "sequence_id": 1001,
    "kind": "text",
    "text": "Hello from Alice",
    "file": null,
    "status": "sent"
  }
}
```

The server deduplicates a retry with the same `(sender_user_id,
client_message_id)` pair. Clients must reuse the ID when retrying.
For a duplicate retry, the server sends only `message:ack` with the original
`message_id`, sets `data.duplicate` to `true`, and does not send a new
`message:created` event.
Clients must also deduplicate received `message:created` events by
`message_id`, because reconnect/history recovery can deliver an already-known
message through more than one path.

## Validation rules

- `room_id` is required and non-empty.
- `room_id` is limited to 64 characters.
- `client_message_id` is required and non-empty.
- Supported kinds are `text`, `file`, and `image`.
- Text is trimmed, non-empty, and at most 4,000 characters.
- Sender identity comes from the authenticated socket, never from payload data.

Every registered user is automatically a member of the server-created
`general` room. Direct rooms contain exactly the two users in the pair. Any
user may create a group with a 1-64 character name. The owner adds/removes
members; groups cap at `MAX_GROUP_MEMBERS` (default 50). Any member may leave.
When the owner leaves, the oldest remaining member becomes owner; an empty
group is closed. Members can read only messages with a `sequence_id` greater
than their membership's `joined_sequence_id`. Membership changes
evict removed sockets immediately and send `room:removed`; newly added users
receive `room:added` and can then join.

History uses the increasing integer `sequence_id` as its cursor, not the
random `message_id`. With no cursor or with `before`, the server selects the
newest messages, orders them descending for selection, then returns them in
ascending display order. With `after`, it selects ascending messages after the
cursor. The endpoint accepts `limit` (default 50, maximum 100), fetches one
extra row to calculate `has_more`, and returns `next_before` or `next_after`.
Clients keep the last `sequence_id` per room and repeat `after` requests while
`has_more` is true after reconnect.

## Phase 5 realtime and files

- `typing:set` sends `{ "room_id": "...", "is_typing": true }`; the server
  broadcasts `typing:changed` only to other members currently in that room.
- `presence:changed` is server-generated when a socket enters or leaves a
  room. It is an online indicator, not durable account presence.
- `message:status` reports `delivered` and `read`. A client emits
  `message:read` with both `room_id` and `message_id`; both are validated
  against database membership and message-room ownership.
- Upload accepts `.png`, `.jpg`, `.gif`, `.webp`, `.pdf`, and `.txt`, with a
  5 MiB cap. The server checks extension, content signature/text encoding,
  stores under a random filename, and returns a `file_id`.
- A message with `kind: "file"` or `kind: "image"` includes `file_id`.
  The sender must own the upload. Download requires membership in a room
  containing a message that references that file.
- Upload storage is local in development. Render's filesystem is ephemeral;
  production uploads must use persistent external object storage.

REST errors always use this shape:

```json
{
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid username or password"
  }
}
```

If a socket sends `message:send` or `typing:set` for a room it has not joined,
the server rejects the event. For `message:send`, the response is
`message:ack`; for `typing:set`, the response is `server:error`. Both use the
error code `NOT_IN_ROOM`:

```json
{
  "protocol_version": 1,
  "data": {
    "code": "NOT_IN_ROOM",
    "message": "Join the room before sending messages"
  }
}
```

## Rate limits

The server has a process-local sliding-window limiter keyed by
`(user_id, event_name)` for sockets. Login and registration use separate
IP-based limits; in deployment, the IP must be derived from the trusted proxy
configuration rather than blindly trusting a client-supplied header.

- `message:send`: 10 events per 10 seconds.
- `typing:set`: 30 events per 10 seconds.
- `auth/login`: 10 attempts per minute per source IP.
- `auth/register`: 5 attempts per minute per source IP.

When exceeded, the server sends `message:ack` or `server:error` with:

```json
{
  "protocol_version": 1,
  "data": {
    "code": "RATE_LIMITED",
    "message": "Too many messages",
    "retry_after_seconds": 5
  }
}
```

This limiter protects one server process. A future multi-instance deployment
must move the counters to shared storage such as Redis.

## Phase 8 deployment checks

- Configure `CORS_ORIGINS` as a comma-separated allowlist of exact origins.
  Native clients that send no `Origin` header are not granted browser CORS
  privileges; do not use `*`.
- Configure trusted proxy handling before using `X-Forwarded-For` for rate
  limiting.
- Use a cold-start-aware login timeout and show `Connecting...` while Render
  wakes. Do not treat the first timeout as invalid credentials.
- Keep the `aiohttp` history request timeout finite and surface a retryable
  network error in the client.