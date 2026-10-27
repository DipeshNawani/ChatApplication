const app = document.querySelector('#app');
const state = { username: '', roomId: 'general', rooms: new Map([['general', { room_id: 'general', name: 'general', kind: 'general' }]]), messages: new Map([['general', []]]), seen: new Set(), lastSequence: new Map(), pending: new Map(), status: 'Offline' };
const h = (value) => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);

function renderLogin(settings = {}) {
  app.innerHTML = `<section class="login"><div class="login-brand">QB<span>CHAT</span></div><p class="eyebrow">DESKTOP MESSENGER</p><h1>Sign in</h1><label>Server URL<input id="server" autocomplete="url" placeholder="http://127.0.0.1:8000" value="${h(settings.serverUrl || 'http://127.0.0.1:8000')}"></label><label>Username<input id="username" autocomplete="username" value="${h(settings.username || '')}"></label><label>Password<input id="password" type="password" autocomplete="current-password"></label><div class="login-actions"><button id="login">Login</button><button id="register" class="secondary">Create account</button></div><p id="status" class="status">${h(state.status)}</p><p id="login-error" class="error"></p></section>`;
  const submit = mode => async () => {
    const values = { serverUrl: document.querySelector('#server').value.trim(), username: document.querySelector('#username').value.trim(), password: document.querySelector('#password').value };
    if (!values.serverUrl.includes('://')) values.serverUrl = `http://${values.serverUrl}`;
    state.status = 'Connecting...';
    document.querySelector('#status').textContent = state.status;
    try {
      const result = await window.chatAPI[mode](values);
      state.username = result.username;
      document.querySelector('#password').value = '';
      renderChat();
      await loadRooms();
      await selectRoom('general');
    } catch (error) {
      state.status = 'Offline';
      document.querySelector('#status').textContent = state.status;
      document.querySelector('#login-error').textContent = `${error.code || 'ERROR'}: ${error.message || 'Request failed'}`;
    }
  };
  document.querySelector('#login').onclick = submit('login');
  document.querySelector('#register').onclick = submit('register');
}

function renderChat() {
  app.innerHTML = `<section class="workspace"><aside class="sidebar"><header><div class="login-brand">QB<span>CHAT</span></div><button id="settings" title="Settings">⚙</button></header><div class="account">${h(state.username)} <span id="status">Connecting...</span></div><div class="section-title">CHATS</div><nav id="rooms"></nav><div class="search"><input id="search" placeholder="Find a person"><button id="find">Search</button><ul id="results"></ul></div><details><summary>New group</summary><input id="group-name" maxlength="64" placeholder="Group name"><button id="create-group">Create</button><input id="member-name" placeholder="Member username"><button id="add-member">Add member</button><button id="leave-group" class="secondary">Leave this group</button></details></aside><main class="conversation"><header class="conversation-header"><div><h1 id="room-title">general</h1><p id="typing" class="muted"></p></div><span id="presence" class="muted"></span></header><p id="errors" class="error"></p><button id="load-older" class="older">Load older messages</button><section id="messages" class="messages"></section><footer><button id="attach" title="Attach file">＋</button><textarea id="composer" rows="2" placeholder="Write a message"></textarea><button id="send" class="send">Send</button></footer></main><dialog id="settings-dialog"><form method="dialog"><h2>Connection settings</h2><label>Server URL<input id="settings-url" type="url" required></label><p class="muted">Changing servers signs you out. Your password and token are not saved.</p><button id="settings-save" value="save">Save</button><button class="secondary" value="cancel">Cancel</button></form></dialog></section>`;
  document.querySelector('#send').onclick = sendText;
  document.querySelector('#attach').onclick = sendFile;
  document.querySelector('#composer').onkeydown = event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendText(); } };
  document.querySelector('#composer').oninput = event => window.chatAPI.setTyping({ room_id: state.roomId, is_typing: Boolean(event.target.value) });
  document.querySelector('#find').onclick = searchUsers;
  document.querySelector('#create-group').onclick = createGroup;
  document.querySelector('#add-member').onclick = addGroupMember;
  document.querySelector('#leave-group').onclick = leaveGroup;
  document.querySelector('#load-older').onclick = loadOlder;
  document.querySelector('#settings').onclick = openSettings;
  document.querySelector('#settings-save').onclick = saveSettings;
}

async function openSettings() {
  const settings = await window.chatAPI.loadSettings();
  document.querySelector('#settings-url').value = settings.serverUrl || '';
  document.querySelector('#settings-dialog').showModal();
}

async function saveSettings(event) {
  event.preventDefault();
  const serverUrl = document.querySelector('#settings-url').value.trim();
  await window.chatAPI.saveSettings({ serverUrl, username: state.username });
  document.querySelector('#settings-dialog').close();
  state.status = 'Offline';
  renderLogin({ serverUrl, username: state.username });
}

function renderRooms() {
  const target = document.querySelector('#rooms');
  if (!target) return;
  target.innerHTML = [...state.rooms.values()].map(room => `<button class="room ${room.room_id === state.roomId ? 'active' : ''}" data-room="${h(room.room_id)}"><span class="room-dot"></span>${h(room.name)}</button>`).join('');
  target.querySelectorAll('[data-room]').forEach(button => button.onclick = () => selectRoom(button.dataset.room));
}

async function loadRooms() {
  const response = await window.chatAPI.listRooms();
  for (const room of response.rooms || []) state.rooms.set(room.room_id, room);
  renderRooms();
}

async function selectRoom(roomId) {
  const room = state.rooms.get(roomId) || { room_id: roomId, name: roomId, kind: 'group' };
  state.rooms.set(roomId, room);
  state.roomId = roomId;
  state.messages.set(roomId, state.messages.get(roomId) || []);
  renderRooms();
  document.querySelector('#room-title').textContent = room.name;
  document.querySelector('#typing').textContent = '';
  document.querySelector('#presence').textContent = '';
  await window.chatAPI.joinRoom(roomId);
  await loadHistory(roomId);
  renderMessages();
}

async function loadHistory(roomId, after) {
  let response = await window.chatAPI.loadHistory(roomId, after);
  while (true) {
    for (const message of response.messages || []) addMessage(message, false);
    if (!response.messages?.length) break;
    const last = ChatProtocolState.nextCursor(response.messages, state.lastSequence.get(roomId) || 0);
    state.lastSequence.set(roomId, Math.max(state.lastSequence.get(roomId) || 0, last));
    if (!response.has_more) break;
    response = await window.chatAPI.loadHistory(roomId, last);
  }
  renderMessages();
}

async function loadOlder() {
  const messages = state.messages.get(state.roomId) || [];
  const firstSequence = messages.reduce((minimum, message) => Math.min(minimum, Number(message.sequence_id) || Infinity), Infinity);
  if (Number.isFinite(firstSequence)) {
    const response = await window.chatAPI.loadOlder(state.roomId, firstSequence);
    for (const message of response.messages || []) addMessage(message, false);
    renderMessages();
  }
}

function addMessage(message, render = true) {
  if (message.message_id && state.seen.has(message.message_id)) return;
  if (message.message_id) state.seen.add(message.message_id);
  const messages = state.messages.get(message.room_id) || [];
  state.messages.set(message.room_id, ChatProtocolState.mergeMessages(messages, [message]));
  if (render && message.room_id === state.roomId) renderMessages();
}

function renderMessages() {
  const target = document.querySelector('#messages');
  if (!target) return;
  target.replaceChildren();
  for (const message of state.messages.get(state.roomId) || []) {
    const article = document.createElement('article');
    article.className = `bubble ${message.sender?.username === state.username ? 'mine' : ''}`;
    const sender = document.createElement('b');
    sender.textContent = message.sender?.username || 'Unknown';
    const body = document.createElement('p');
    body.textContent = message.file?.name || message.text || '';
    const footer = document.createElement('small');
    footer.textContent = message.status || 'sent';
    article.append(sender, body, footer);
    if (message.file?.file_id) {
      const download = document.createElement('button');
      download.textContent = 'Download';
      download.onclick = () => window.chatAPI.downloadFile(message.file.file_id, message.file.name);
      article.append(download);
    }
    target.append(article);
    if (message.sequence_id && message.sender?.username !== state.username) window.chatAPI.markRead(state.roomId, message.message_id);
  }
  target.scrollTop = target.scrollHeight;
}

function sendText() {
  const input = document.querySelector('#composer');
  const text = input.value.trim();
  if (!text) return;
  const clientMessageId = `client-${crypto.randomUUID()}`;
  addMessage({ room_id: state.roomId, client_message_id: clientMessageId, sender: { username: state.username }, kind: 'text', text, status: 'pending' });
  window.chatAPI.sendMessage({ room_id: state.roomId, client_message_id: clientMessageId, kind: 'text', text });
  input.value = '';
}

async function sendFile() {
  try {
    const filePath = await window.chatAPI.chooseFile();
    if (!filePath) return;
    const result = await window.chatAPI.uploadFile(filePath);
    const file = result.file;
    const kind = file.content_type?.startsWith('image/') ? 'image' : 'file';
    const clientMessageId = `client-${crypto.randomUUID()}`;
    addMessage({ room_id: state.roomId, client_message_id: clientMessageId, sender: { username: state.username }, kind, text: '', file, status: 'pending' });
    window.chatAPI.sendMessage({ room_id: state.roomId, client_message_id: clientMessageId, kind, text: '', file_id: file.file_id });
  } catch (error) { showError(error); }
}

async function searchUsers() {
  try {
    const result = await window.chatAPI.searchUsers(document.querySelector('#search').value);
    const list = document.querySelector('#results');
    list.replaceChildren();
    for (const user of result.users || []) {
      const item = document.createElement('li');
      item.textContent = user.username;
      item.onclick = async () => {
        try {
          const response = await window.chatAPI.openDirectChat(user.username);
          const room = response.room;
          state.rooms.set(room.room_id, room);
          renderRooms();
          await selectRoom(room.room_id);
        } catch (error) { showError(error); }
      };
      list.append(item);
    }
  } catch (error) { showError(error); }
}

async function createGroup() {
  try {
    const result = await window.chatAPI.createGroup(document.querySelector('#group-name').value);
    state.rooms.set(result.room.room_id, result.room);
    renderRooms();
    await selectRoom(result.room.room_id);
  } catch (error) { showError(error); }
}

async function addGroupMember() {
  try { await window.chatAPI.addGroupMember(state.roomId, document.querySelector('#member-name').value); }
  catch (error) { showError(error); }
}

async function leaveGroup() {
  try { await window.chatAPI.leaveGroup(state.roomId); }
  catch (error) { showError(error); }
}

function showError(error) {
  const target = document.querySelector('#errors');
  if (target) target.textContent = `${error.code || 'ERROR'}: ${error.message || 'Request failed'}`;
}

window.chatAPI.on('connection-state', value => { state.status = value; const status = document.querySelector('#status'); if (status) status.textContent = value; });
window.chatAPI.on('message:created', payload => addMessage(payload.data));
window.chatAPI.on('message:ack', payload => {
  const data = payload.data || {};
  const message = (state.messages.get(state.roomId) || []).find(item => item.client_message_id === payload.request_id);
  if (message) { message.status = ChatProtocolState.ackStatus(payload) || message.status; message.message_id = data.message_id || message.message_id; renderMessages(); }
  if (data.code) showError(data);
});
window.chatAPI.on('server:error', payload => showError(payload.data || {}));
window.chatAPI.on('room:added', payload => { const room = payload.data; state.rooms.set(room.room_id, room); renderRooms(); void selectRoom(room.room_id); });
window.chatAPI.on('room:removed', payload => { const roomId = payload.data?.room_id; state.rooms.delete(roomId); state.messages.delete(roomId); renderRooms(); if (roomId === state.roomId) void selectRoom('general'); });
window.chatAPI.on('typing:changed', payload => { const data = payload.data || {}; const target = document.querySelector('#typing'); if (target && data.room_id === state.roomId) target.textContent = data.is_typing ? `${data.username} is typing...` : ''; });
window.chatAPI.on('presence:changed', payload => { const data = payload.data || {}; const target = document.querySelector('#presence'); if (target && data.room_id === state.roomId) target.textContent = `${data.username} ${data.online ? 'online' : 'offline'}`; });
window.chatAPI.on('message:status', payload => {
  const data = payload.data || {};
  for (const messages of state.messages.values()) for (const message of messages) if (message.message_id === data.message_id) message.status = data.status;
  renderMessages();
});
window.chatAPI.on('auth-error', error => { showError(error); state.status = 'Offline'; renderLogin({}); });
window.chatAPI.loadSettings().then(renderLogin);
