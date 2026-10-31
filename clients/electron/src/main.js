const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { io } = require('socket.io-client');
const { normalizeUrl, normalizeErrorPayload, createApiRequest } = require('./api-client');

let windowRef;
let socket;
let token = '';
// The hosted backend is the default so a newly installed client can connect
// to other devices immediately. Existing saved settings still take priority.
const DEFAULT_SERVER_URL = 'https://quantumbytes-chat.onrender.com';
let serverUrl = DEFAULT_SERVER_URL;
const pendingMessages = new Map();
const activeRooms = new Set(['general']);
const joinedRooms = new Set();

function settingsPath() {
  return path.join(app.getPath('appData'), 'QuantumBytesChat', 'electron-settings.json');
}

function loadSettings() {
  try {
    const values = JSON.parse(fs.readFileSync(settingsPath(), 'utf8'));
    return { serverUrl: values.serverUrl || DEFAULT_SERVER_URL, username: values.username || '' };
  } catch { return { serverUrl: DEFAULT_SERVER_URL, username: '' }; }
}

function saveSettings(values) {
  fs.mkdirSync(path.dirname(settingsPath()), { recursive: true });
  fs.writeFileSync(settingsPath(), JSON.stringify({ serverUrl: values.serverUrl, username: values.username }, null, 2));
}

function send(channel, payload) { if (windowRef) windowRef.webContents.send(channel, payload); }

const apiRequest = createApiRequest({ getServerUrl: () => serverUrl, getToken: () => token });

function connectSocket(username) {
  if (socket) socket.disconnect();
  send('connection-state', 'Connecting...');
  socket = io(serverUrl, { auth: { token }, timeout: 90000, reconnection: true, reconnectionAttempts: Infinity, reconnectionDelayMax: 30000 });
  socket.on('connect', () => {
    send('connection-state', 'Connected');
    joinedRooms.clear();
    for (const roomId of activeRooms) socket.emit('room:join', { data: { room_id: roomId } });
  });
  socket.io.on('reconnect_attempt', attempt => send('connection-state', `Reconnecting (attempt ${attempt})...`));
  socket.on('disconnect', () => send('connection-state', 'Offline'));
  for (const event of ['message:created', 'message:ack', 'server:error', 'room:joined', 'room:added', 'room:removed', 'typing:changed', 'presence:changed', 'message:status']) {
    socket.on(event, payload => send(event, payload));
  }
  socket.on('room:joined', payload => {
    const roomId = payload.data?.room_id;
    if (!roomId) return;
    joinedRooms.add(roomId);
    for (const queued of pendingMessages.values()) {
      if (queued.data.room_id === roomId) socket.emit('message:send', queued);
    }
  });
  socket.on('room:added', payload => {
    const roomId = payload.data?.room_id;
    if (roomId) { activeRooms.add(roomId); socket.emit('room:join', { data: { room_id: roomId } }); }
  });
  socket.on('room:removed', payload => { activeRooms.delete(payload.data?.room_id); joinedRooms.delete(payload.data?.room_id); });
  socket.on('message:ack', payload => {
    const requestId = payload.request_id;
    if (requestId && (payload.data?.status === 'sent' || payload.data?.code)) pendingMessages.delete(requestId);
  });
  socket.on('connect_error', error => {
    const message = error.data?.message || error.message || 'Unable to connect';
    if (error.data?.code === 'TOKEN_EXPIRED' || /token|expired/i.test(message)) { token = ''; socket.disconnect(); send('auth-error', { code: 'TOKEN_EXPIRED', message: 'Please log in again' }); }
  });
  void username;
}

function resetConnection() {
  socket?.disconnect();
  socket = undefined;
  token = '';
  pendingMessages.clear();
  joinedRooms.clear();
  activeRooms.clear();
  activeRooms.add('general');
}

async function createWindow() {
  windowRef = new BrowserWindow({
    width: 1180, height: 780, minWidth: 860, minHeight: 600,
    backgroundColor: '#f6f8f9', autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  await windowRef.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

ipcMain.handle('settings:load', () => loadSettings());
ipcMain.handle('settings:save', (_event, values) => {
  resetConnection();
  serverUrl = normalizeUrl(values.serverUrl);
  saveSettings({ serverUrl, username: values.username || loadSettings().username || '' });
  return { serverUrl };
});
async function authenticate(mode, values) {
  try {
    const address = normalizeUrl(values.serverUrl);
    resetConnection();
    serverUrl = address;
    const result = await apiRequest(`/api/v1/auth/${mode}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: values.username.trim(), password: values.password }),
    });
    if (!result?.access_token || !result.user?.username) {
      return { error: { code: 'INVALID_SERVER_RESPONSE', message: 'This address did not return a valid chat login response.' } };
    }
    token = result.access_token;
    saveSettings({ serverUrl, username: result.user.username });
    connectSocket(result.user.username);
    return { username: result.user.username };
  } catch (error) {
    return { error: { code: error.code || 'REQUEST_FAILED', message: error.message || 'Unable to sign in. Please try again.' } };
  }
}

ipcMain.handle('auth:login', (_event, values) => authenticate('login', values));
ipcMain.handle('auth:register', (_event, values) => authenticate('register', values));
ipcMain.handle('room:join', (_event, roomId) => { activeRooms.add(roomId); socket?.emit('room:join', { data: { room_id: roomId } }); });
ipcMain.handle('message:send', (_event, payload) => {
  const envelope = { data: payload, request_id: payload.client_message_id };
  pendingMessages.set(payload.client_message_id, envelope);
  if (socket?.connected && joinedRooms.has(payload.room_id)) socket.emit('message:send', envelope);
});
ipcMain.handle('typing:set', (_event, payload) => { socket?.emit('typing:set', { data: payload }); });
ipcMain.handle('history:load', (_event, roomId, after) => apiRequest(`/api/v1/rooms/${encodeURIComponent(roomId)}/messages?limit=50${after ? `&after=${after}` : ''}`));
ipcMain.handle('history:older', (_event, roomId, before) => apiRequest(`/api/v1/rooms/${encodeURIComponent(roomId)}/messages?limit=50&before=${before}`));
ipcMain.handle('message:read', (_event, roomId, messageId) => { socket?.emit('message:read', { data: { room_id: roomId, message_id: messageId } }); });
ipcMain.handle('users:search', (_event, query) => apiRequest(`/api/v1/users/search?q=${encodeURIComponent(query)}`));
ipcMain.handle('chat:direct', (_event, username) => apiRequest('/api/v1/chats/direct', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username }) }));
ipcMain.handle('rooms:list', () => apiRequest('/api/v1/rooms'));
ipcMain.handle('group:create', (_event, name) => apiRequest('/api/v1/rooms/groups', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }));
ipcMain.handle('group:add-member', (_event, roomId, username) => apiRequest(`/api/v1/rooms/${encodeURIComponent(roomId)}/members`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username }) }));
ipcMain.handle('group:leave', (_event, roomId) => apiRequest(`/api/v1/rooms/${encodeURIComponent(roomId)}/leave`, { method: 'POST' }));
ipcMain.handle('file:choose', async () => {
  const choice = await dialog.showOpenDialog(windowRef, { properties: ['openFile'] });
  return choice.canceled ? null : choice.filePaths[0];
});
ipcMain.handle('file:upload', async (_event, filePath) => {
  const stat = fs.statSync(filePath);
  if (stat.size > 5 * 1024 * 1024) throw { code: 'FILE_TOO_LARGE', message: 'Maximum file size is 5 MB' };
  const bytes = fs.readFileSync(filePath);
  const blob = new Blob([bytes]);
  const form = new FormData();
  form.append('file', blob, path.basename(filePath));
  return apiRequest('/api/v1/files', { method: 'POST', body: form });
});
ipcMain.handle('file:download', async (_event, fileId, filename) => {
  const response = await fetch(`${serverUrl}/api/v1/files/${encodeURIComponent(fileId)}`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(30000) });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    const detail = normalizeErrorPayload(result);
    const error = new Error(detail.message || 'Request failed');
    error.code = detail.code || 'REQUEST_FAILED';
    throw error;
  }
  const choice = await dialog.showSaveDialog(windowRef, { defaultPath: filename });
  if (!choice.canceled && choice.filePath) fs.writeFileSync(choice.filePath, Buffer.from(await response.arrayBuffer()));
});

app.whenReady().then(createWindow);
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
