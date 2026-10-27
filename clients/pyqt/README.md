# PyQt6 Client

Run these commands from the `quantumbytestask` folder.

```powershell
.venv\Scripts\python.exe -m pip install -r clients\pyqt\requirements.txt
.venv\Scripts\python.exe -m clients.pyqt.main
```

The first screen accepts a server URL, username, and password for login or
registration. Only the server URL and username are saved in
`%APPDATA%\QuantumBytesChat\settings.json`; passwords and JWTs are not stored.

For two local windows:

1. Start the server with `DEV_MODE=false` and a `JWT_SECRET` in `server/.env`.
2. Launch the client and register two users, such as `alice` and `bob`.
3. Log in with each user in a separate window.
4. Both users join `general` automatically.
5. Search for the other username and select it to create a direct chat.