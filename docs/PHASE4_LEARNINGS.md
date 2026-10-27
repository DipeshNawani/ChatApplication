# Phase 4 Learnings

## What I learned

Passwords are sent to the server only for register/login and are stored as
Argon2id hashes. The client keeps the JWT in memory, sends it to REST and
Socket.IO, and must return to login when the token expires.

Membership is a database rule, not just a GUI choice. The server checks it
before joining a room, posting, typing, or reading history. Cursor pagination
uses the database sequence number because it is ordered, while message IDs
remain stable random identifiers for deduplication.

## Python GUI versus Electron preview

PyQt6 now has to coordinate login, token lifetime, history loading, and
room-scoped state without blocking the GUI thread. Electron will solve the
same workflow with renderer state and IPC, usually with more frontend code but
more familiar web tooling for auth forms and chat views.

## Common mistakes and debugging

- Never put `JWT_SECRET`, passwords, or JWTs in Git or the settings JSON.
- A valid token does not imply room access; inspect the membership row when
  `NOT_IN_ROOM` appears.
- Use `before` or `after` with `sequence_id`, not `message_id`, for history.
- On reconnect, an expired token requires login; retrying the same token will
  never recover the connection.
- Run `alembic upgrade head` after resetting a local database.

## Small exercise

Add a "load older messages" button that requests the previous page with the
first loaded message's `sequence_id` as `before`, then merges by
`message_id`.