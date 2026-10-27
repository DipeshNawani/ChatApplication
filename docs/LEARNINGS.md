# Project Learnings

## Phase 4b

Group membership is stateful authorization: joining a room is not enough by
itself, because history must begin at the member's join sequence and removals
must evict live sockets. Ownership transfer is easiest when it is handled in
one database transaction.

PyQt6 remains compact for this phase because its existing worker signals can
carry room events directly. Electron will need matching IPC messages, which
adds process-boundary code but keeps the renderer safer.

Common mistake: updating only the room list and forgetting the server-side
membership row or live Socket.IO room. Exercise: add a group owner badge to
the PyQt room list.

## Phase 5

File references are authorized through room membership, while presence and
typing are transient server events. File type is checked using both extension
and content signature, not just a filename. PyQt keeps these UI updates behind
worker signals.

Electron's Node main process can use the Socket.IO client without exposing its
token to the renderer. The preload bridge is an API allowlist, not a general
IPC tunnel. This separation adds code, but materially reduces renderer access
to secrets and Node capabilities.

Common mistake: a matching extension does not prove a file's contents are
safe. Another is sending a message immediately after requesting room join;
wait for server confirmation. Exercise: show image thumbnails for authorized
image attachments while retaining a download action.

## Phase 6

Electron main owns the JWT, socket, HTTP requests, and retry queue. The
renderer receives only application events through preload IPC. Compared with
PyQt, Electron uses more project scaffolding and JavaScript but provides
familiar web layout/styling; PyQt remains simpler for Python-centered work.

Common mistake: forwarding arbitrary IPC channels from preload defeats the
security boundary. Exercise: add a reconnect indicator that preserves the
current conversation while the main process reconnects.

## Phase 7

The protocol is genuinely shared: the Python worker and Electron main-process
client can exchange direct/group messages, use the same history cursor, and
resume rooms after a socket reconnect. The cross-client probe uses the real
`socket.io-client` package, while Electron's renderer still has no token.

PyQt's QThread signals and Electron's preload IPC are different UI bridges
around the same server contract. Common mistake: tests that only validate
payload helpers can miss transport and room-join races. Exercise: add a test
that removes an Electron user from a group while its client is connected.

For integration-test startup, a listening TCP port is not proof that the ASGI
application has completed startup. Poll `/health`, and allocate test ports
dynamically to avoid collisions between clients or parallel runs.

## Phase 8

Render's filesystem is temporary, so uploaded-file persistence must move to
object storage before production use. Local SQLite remains a development
profile; hosted persistence uses PostgreSQL through SQLAlchemy and Alembic.
Deployment and both Windows package builds are prepared. The service cannot
be activated without account-owned Supabase and Render configuration. Signing
certificates are not available in this workspace.

The initial Electron audit identified 34 advisories in Electron 38 and its
archive dependency. Electron was upgraded to patched 42.11.18; the refreshed
advisory scan and `npm audit` both report no known vulnerabilities.

Common mistake: treating a successful package build as proof of hosted
deployment. Exercise: configure Supabase, deploy the Blueprint, and verify
login from both packaged clients.