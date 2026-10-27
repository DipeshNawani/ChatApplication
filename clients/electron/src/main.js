const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { io } = require('socket.io-client');

let windowRef;
let socket;
let token = '';
let serverUrl = 'http://127.0.0.1:8000';
const pendingMessages = new Map();
const activeRooms = new Set(['general']);
const joinedRooms = new Set();

function settingsPath() {
  return path.join(app.getPath('appData'), 'QuantumBytesChat', 'electron-settings.json');
}

function loadSettings() {
  try { return JSON.parse(fs.readFileSync(settingsPath(), 'utf8')); } catch { return {}; }
}

function saveSettings(values) {
  fs.mkdirSync(path.dirname(settingsPath()), { recursive: true });
  fs.writeFileSync(settingsPath(), JSON.stringify({ serverUrl: values.serverUrl, username: values.username }, null, 2));
}

function send(channel, payload) { if (windowRef) windowRef.webContents.send(channel, payload); }

function normalizeUrl(value) {
  const trimmed = String(value || '').trim();
  return (trimmed.includes('://') ? trimmed : `http://${trimmed}`).replace(/\/$/, '');
}

async function apiRequest(pathname, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), pathname.startsWith('/api/v1/auth/') ? 90000 : 15000);
  try {
    const response = await fetch(`${serverUrl}${pathname}`, {
      ...options,
      signal: controller.signal,
      headers: { ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    });
    const body = await response.json();
    if (!response.ok) throw body.error || body.detail || { code: 'REQUEST_FAILED', message: 'Request failed' };
    return body;
  } finally {
    clearTimeout(timeout);
  }
}

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

async function createWindow() {
  windowRef = new BrowserWindow({
    width: 1100, height: 720,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  await windowRef.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

ipcMain.handle('settings:load', () => loadSettings());
ipcMain.handle('settings:save', (_event, values) => {
  serverUrl = normalizeUrl(values.serverUrl);
  saveSettings({ serverUrl, username: values.username || loadSettings().username || '' });
  token = '';
  joinedRooms.clear();
  activeRooms.clear();
  activeRooms.add('general');
  socket?.disconnect();
  return { serverUrl };
});
ipcMain.handle('auth:login', async (_event, values) => {
  serverUrl = normalizeUrl(values.serverUrl);
  const result = await apiRequest('/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: values.username, password: values.password }) });
  token = result.access_token;
  saveSettings(values);
  connectSocket(result.user.username);
  return { username: result.user.username };
});
ipcMain.handle('auth:register', async (_event, values) => {
  serverUrl = normalizeUrl(values.serverUrl);
  const result = await apiRequest('/api/v1/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: values.username, password: values.password }) });
  token = result.access_token;
  saveSettings(values);
  connectSocket(result.user.username);
  return { username: result.user.username };
});
ipcMain.handle('room:join', (_event, roomId) => { activeRooms.add(roomId); socket?.emit('room:join', { data: { room_id: roomId } }); });
ipcMain.handle('message:send', (_event, payload) => {
  const envelope = { data: payload, request_id: payload.client_message_id };
  pendingMessages.set(payload.client_message_id, envelope);
  if (socket?.connected && joinedRooms.has(payload.room_id)) socket.emit('message:send', envelope);
});
ipcMain.handle('typing:set', (_event, payload) => socket?.emit('typing:set', { data: payload }));
ipcMain.handle('history:load', (_event, roomId, after) => apiRequest(`/api/v1/rooms/${encodeURIComponent(roomId)}/messages?limit=50${after ? `&after=${after}` : ''}`));
ipcMain.handle('history:older', (_event, roomId, before) => apiRequest(`/api/v1/rooms/${encodeURIComponent(roomId)}/messages?limit=50&before=${before}`));
ipcMain.handle('message:read', (_event, roomId, messageId) => socket?.emit('message:read', { data: { room_id: roomId, message_id: messageId } }));
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
  if (!response.ok) { const result = await response.json(); throw result.error || result.detail; }
  const choice = await dialog.showSaveDialog(windowRef, { defaultPath: filename });
  if (!choice.canceled && choice.filePath) fs.writeFileSync(choice.filePath, Buffer.from(await response.arrayBuffer()));
});

app.whenReady().then(createWindow);
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
