# Phase 3 Learnings

## What I learned

The PyQt6 window must stay on the main Qt thread. The Socket.IO client runs
inside a worker thread with its own asyncio loop, then emits Qt signals back
to the window. Signals are the safe bridge between network events and widgets.

The client does not own message truth. It creates a `client_message_id`, shows
a pending bubble, and lets the server's `message:created` event change it to
sent. A reconnect reuses pending IDs, while `message_id` deduplication avoids
duplicate bubbles.

## Python GUI versus Electron preview

PyQt6 keeps this first client close to Python and needs little frontend
tooling. Electron will require more process and JavaScript structure, but it
will make web-style visual design and frontend reuse easier. PyQt6 is a good
choice for this learning-first desktop client; Electron becomes attractive
when a web UI team or browser-based component ecosystem matters more.

## Common mistakes and debugging

- Updating a widget directly from the Socket.IO thread can crash or freeze
  the application. Emit a Qt signal instead.
- `127.0.0.1` means the current computer. Use the server's LAN IP for a
  second device.
- A `Connecting...` or `Reconnecting...` state can be a Render cold start,
  firewall block, wrong URL, or server not running. Check `/health` first.
- Never store passwords in the JSON settings file. Phase 4 will add JWT
  session handling separately.

## Small exercise

Add a message timestamp to each bubble using the `occurred_at` value from the
server event, while keeping all widget updates on the Qt main thread.