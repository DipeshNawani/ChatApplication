const app = document.querySelector('#app');
const state = { username: '', roomId: 'general', rooms: new Map(), messages: new Map(), seen: new Set(), read: new Set(), lastSequence: new Map(), unread: new Map(), status: 'Offline' };
let typingTimer;
const h = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
const initials = name => String(name || '?').replace(/[_-]/g, ' ').split(' ').filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase();
const paths = {
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  send: '<path d="m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13"/>',
  attach: '<path d="m21 11-8.5 8.5a6 6 0 0 1-8.5-8.5l9-9a4 4 0 0 1 5.7 5.7l-9 9a2 2 0 0 1-2.8-2.8L15 6"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/><circle cx="9" cy="7" r="4"/>',
  settings: '<path d="M12 3 14 6l3-.2 1.7 3-1.6 2.7 1.6 2.7-1.7 3-3-.2-2 3-2-3-3 .2-1.7-3 1.6-2.7L5.3 9 7 6l3 .2 2-3Z"/><circle cx="12" cy="11.5" r="3"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.chat}</svg>`;
const brand = '<div class="brand"><span class="brand-mark">qb</span><span class="brand-name">QuantumBytes<small>A little more connected</small></span></div>';

function resetSession() {
  state.roomId = 'general';
  state.rooms = new Map([['general', { room_id: 'general', name: 'General', kind: 'general' }]]);
  state.messages.clear(); state.seen.clear(); state.read.clear(); state.lastSequence.clear(); state.unread.clear();
  clearTimeout(typingTimer);
}

function renderLogin(settings = {}) {
  resetSession();
  app.innerHTML = `<section class="login-shell"><aside class="login-story">${brand}<div class="story-content"><span class="story-kicker">A SPACE FOR EVERY CONVERSATION</span><h2>Good conversations.<br>Great connections.</h2><p>Bring your people together in one calm, organized place. Pick up right where you left off.</p><div class="story-lines"><span>${icon('chat')}Direct messages that keep things personal</span><span>${icon('users')}Group spaces for shared ideas</span><span>${icon('attach')}Files and conversations, together</span></div></div><p class="story-footer">QUANTUMBYTES CHAT &nbsp; / &nbsp; DESKTOP</p></aside><div class="login-panel"><section class="login"><p class="eyebrow">WELCOME TO YOUR WORKSPACE</p><h1>Good to see you.</h1><p class="login-description">Sign in to continue the conversation.</p><form id="login-form"><label for="server">Server address<input id="server" autocomplete="url" required placeholder="https://your-server.com" value="${h(settings.serverUrl || 'http://127.0.0.1:8000')}"></label><label for="username">Username<input id="username" autocomplete="username" required minlength="3" maxlength="32" placeholder="Your username" value="${h(settings.username || '')}"></label><label for="password">Password</label><div class="password-field"><input id="password" type="password" autocomplete="current-password" required minlength="8" maxlength="128" placeholder="Enter your password"><button type="button" id="show-password" class="ghost" aria-label="Show password" aria-pressed="false">Show</button></div><div class="login-actions"><button type="submit" id="login">Sign in ${icon('arrow')}</button><button type="button" id="register" class="secondary">Create an account</button></div><p id="login-error" class="error" role="alert"></p></form><p class="login-status"><span class="status-dot"></span><span id="status" role="status">${h(state.status)}</span></p><p class="login-note">Your password is never saved on this device.</p></section></div></section>`;
  const form = document.querySelector('#login-form');
  const submit = async mode => {
    if (!form.reportValidity()) return;
    const values = { serverUrl: document.querySelector('#server').value.trim(), username: document.querySelector('#username').value.trim(), password: document.querySelector('#password').value };
    if (!values.serverUrl.includes('://')) values.serverUrl = `http://${values.serverUrl}`;
    document.querySelector('#login-error').textContent = '';
    document.querySelector('#status').textContent = 'Connecting to your workspace…';
    form.querySelectorAll('button').forEach(button => { button.disabled = true; });
    let authenticated = false;
    try {
      const result = await window.chatAPI[mode](values);
      state.username = result.username; authenticated = true;
      document.querySelector('#password').value = '';
      renderChat(); await loadRooms(); await selectRoom('general');
    } catch (error) {
      if (authenticated) showError(error);
      else {
        document.querySelector('#status').textContent = mode === 'register' ? 'Registration unsuccessful' : 'Sign-in unsuccessful';
        document.querySelector('#login-error').textContent = error.message || 'Please check your details and try again.';
      }
    } finally { form.querySelectorAll('button').forEach(button => { button.disabled = false; }); }
  };
  form.onsubmit = event => { event.preventDefault(); void submit('login'); };
  document.querySelector('#register').onclick = () => void submit('register');
  document.querySelector('#show-password').onclick = event => {
    const password = document.querySelector('#password'); const show = password.type === 'password';
    password.type = show ? 'text' : 'password'; event.currentTarget.textContent = show ? 'Hide' : 'Show';
    event.currentTarget.setAttribute('aria-label', show ? 'Hide password' : 'Show password'); event.currentTarget.setAttribute('aria-pressed', String(show));
  };
}

function renderChat() {
  app.innerHTML = `<section class="workspace"><nav class="rail" aria-label="Workspace"><span class="brand-mark" title="QuantumBytes">qb</span><button id="chats-nav" class="rail-button selected" aria-label="Focus conversations" title="Conversations">${icon('chat')}</button><div class="rail-spacer"></div><button id="settings" class="rail-button" aria-label="Connection settings" title="Connection settings">${icon('settings')}</button></nav><aside class="sidebar"><div class="sidebar-top"><div class="sidebar-title"><h1>Messages</h1><button id="new-group" class="icon-button ghost" aria-label="Create a group" title="Create a group">${icon('plus')}</button></div><p class="muted">A space to stay connected.</p><div class="search-field">${icon('search')}<input id="search" aria-label="Find people by username" placeholder="Find a person…" maxlength="32"><button id="find" class="icon-button ghost" aria-label="Search people" title="Search people">${icon('arrow')}</button></div></div><ul id="results" aria-label="People search results"></ul><div class="section-label">CONVERSATIONS<span id="room-count"></span></div><nav id="rooms" aria-label="Conversations"></nav><div class="account"><span class="avatar">${h(initials(state.username))}</span><div class="account-copy"><strong>${h(state.username)}</strong><small><span id="connection-dot" class="status-dot ${state.status === 'Connected' ? 'online' : ''}"></span><span id="status" role="status">${h(state.status)}</span></small></div></div></aside><main class="conversation"><header class="conversation-header"><span id="room-avatar" class="avatar group">#</span><div class="conversation-heading"><h1 id="room-title">General</h1><p id="room-description" class="muted">Your shared conversation space</p></div><div class="header-actions"><span id="presence" class="muted"></span><button id="manage-group" class="secondary" hidden>${icon('users')}Manage group</button></div></header><p id="errors" class="error" role="alert"></p><div class="history-tools"><button id="load-older" class="older" hidden>Load earlier messages</button></div><section id="messages" class="messages" aria-label="Messages"></section><div class="composer-area"><p id="typing" class="typing-line" role="status"></p><div class="composer-box"><button id="attach" class="icon-button ghost" aria-label="Attach a file" title="Attach a file · up to 5 MiB">${icon('attach')}</button><textarea id="composer" rows="1" maxlength="4000" aria-label="Message" placeholder="Write a message…"></textarea><button id="send" disabled>${icon('send')}Send</button></div><div class="composer-hint"><span>Enter to send · Shift + Enter for a new line</span><span>Files up to 5 MiB</span></div></div></main></section>
  <dialog id="settings-dialog" aria-labelledby="settings-title"><form id="settings-form"><div class="dialog-heading"><h2 id="settings-title">Connection settings</h2><button type="button" class="icon-button ghost" data-close="settings-dialog" aria-label="Close settings">${icon('close')}</button></div><p class="muted">Changing your server will sign you out.</p><label for="settings-url">Server address<input id="settings-url" required></label><div class="dialog-actions"><button type="button" class="secondary" data-close="settings-dialog">Cancel</button><button type="submit">Save changes</button></div></form></dialog>
  <dialog id="group-dialog" aria-labelledby="group-title"><form id="group-form"><div class="dialog-heading"><h2 id="group-title">Bring people together</h2><button type="button" class="icon-button ghost" data-close="group-dialog" aria-label="Close create group">${icon('close')}</button></div><p class="muted">Create a space for your next conversation.</p><label for="group-name">Group name<input id="group-name" required maxlength="64" placeholder="e.g. Design team"></label><p id="group-error" class="error" role="alert"></p><div class="dialog-actions"><button type="button" class="secondary" data-close="group-dialog">Cancel</button><button type="submit">Create group</button></div></form></dialog>
  <dialog id="members-dialog" aria-labelledby="members-title"><form id="members-form"><div class="dialog-heading"><h2 id="members-title">Manage group</h2><button type="button" class="icon-button ghost" data-close="members-dialog" aria-label="Close group settings">${icon('close')}</button></div><p class="muted">Group owners can invite people by username.</p><label for="member-name">Invite a person<input id="member-name" required maxlength="32" placeholder="Username"></label><p id="member-feedback" class="muted" role="status"></p><p id="member-error" class="error" role="alert"></p><div class="dialog-actions"><button type="button" id="leave-group" class="danger">Leave group</button><button type="submit">Add member</button></div></form></dialog>`;
  document.querySelector('#send').onclick = sendText;
  document.querySelector('#attach').onclick = sendFile;
  document.querySelector('#composer').onkeydown = event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendText(); } };
  document.querySelector('#composer').oninput = event => {
    document.querySelector('#send').disabled = !event.target.value.trim();
    event.target.style.height = 'auto'; event.target.style.height = `${Math.min(event.target.scrollHeight, 130)}px`;
    void window.chatAPI.setTyping({ room_id: state.roomId, is_typing: Boolean(event.target.value.trim()) });
    clearTimeout(typingTimer); const roomId = state.roomId;
    typingTimer = setTimeout(() => void window.chatAPI.setTyping({ room_id: roomId, is_typing: false }), 2500);
  };
  document.querySelector('#find').onclick = searchUsers;
  document.querySelector('#search').onkeydown = event => { if (event.key === 'Enter') void searchUsers(); };
  document.querySelector('#new-group').onclick = () => document.querySelector('#group-dialog').showModal();
  document.querySelector('#manage-group').onclick = () => document.querySelector('#members-dialog').showModal();
  document.querySelector('#group-form').onsubmit = event => { event.preventDefault(); void createGroup(); };
  document.querySelector('#members-form').onsubmit = event => { event.preventDefault(); void addGroupMember(); };
  document.querySelector('#leave-group').onclick = leaveGroup;
  document.querySelector('#load-older').onclick = () => void loadOlder().catch(showError);
  document.querySelector('#settings').onclick = () => void openSettings().catch(showError);
  document.querySelector('#settings-form').onsubmit = event => { event.preventDefault(); void saveSettings().catch(showError); };
  document.querySelector('#chats-nav').onclick = () => document.querySelector('#search').focus();
  document.querySelectorAll('[data-close]').forEach(button => { button.onclick = () => document.getElementById(button.dataset.close).close(); });
}

async function openSettings() {
  const settings = await window.chatAPI.loadSettings(); document.querySelector('#settings-url').value = settings.serverUrl || ''; document.querySelector('#settings-dialog').showModal();
}
async function saveSettings() {
  const serverUrl = document.querySelector('#settings-url').value.trim();
  await window.chatAPI.saveSettings({ serverUrl, username: state.username }); state.status = 'Offline'; renderLogin({ serverUrl, username: state.username });
}
function renderRooms() {
  const target = document.querySelector('#rooms'); if (!target) return;
  document.querySelector('#room-count').textContent = String(state.rooms.size);
  target.innerHTML = [...state.rooms.values()].map(room => {
    const messages = state.messages.get(room.room_id) || []; const last = messages[messages.length - 1];
    const description = last ? (last.file?.name || last.text || 'Attachment') : (room.kind === 'direct' ? 'Direct conversation' : room.kind === 'general' ? 'Everyone, together' : 'Group conversation');
    const unread = state.unread.get(room.room_id) || 0;
    return `<button class="room ${room.room_id === state.roomId ? 'active' : ''}" data-room="${h(room.room_id)}" ${room.room_id === state.roomId ? 'aria-current="page"' : ''}><span class="avatar ${room.kind !== 'direct' ? 'group' : ''}">${room.kind === 'general' ? '#' : h(initials(room.name))}</span><span class="room-copy"><span class="room-name">${h(room.name)}</span><span class="room-preview">${h(description)}</span></span>${unread ? `<span class="unread" aria-label="${unread} unread">${unread}</span>` : ''}</button>`;
  }).join('');
  target.querySelectorAll('[data-room]').forEach(button => { button.onclick = () => void selectRoom(button.dataset.room).catch(showError); });
}
async function loadRooms() {
  const response = await window.chatAPI.listRooms();
  for (const room of response.rooms || []) state.rooms.set(room.room_id, { ...room, name: room.kind === 'general' ? 'General' : room.name });
  renderRooms();
}
async function selectRoom(roomId) {
  const room = state.rooms.get(roomId) || { room_id: roomId, name: roomId, kind: 'group' };
  clearTimeout(typingTimer);
  if (state.roomId !== roomId) void window.chatAPI.setTyping({ room_id: state.roomId, is_typing: false });
  state.rooms.set(roomId, room); state.roomId = roomId; state.unread.delete(roomId); state.messages.set(roomId, state.messages.get(roomId) || []);
  renderRooms(); document.querySelector('#room-title').textContent = room.name;
  document.querySelector('#room-description').textContent = room.kind === 'direct' ? 'Direct conversation' : room.kind === 'general' ? 'Your shared conversation space' : 'A space for your group';
  document.querySelector('#room-avatar').textContent = room.kind === 'general' ? '#' : initials(room.name);
  document.querySelector('#manage-group').hidden = room.kind !== 'group';
  document.querySelector('#typing').textContent = ''; document.querySelector('#presence').textContent = ''; document.querySelector('#errors').textContent = ''; document.querySelector('#load-older').hidden = true;
  renderMessages(true); await window.chatAPI.joinRoom(roomId); await loadHistory(roomId);
  if (roomId === state.roomId) document.querySelector('#composer').focus();
}
async function loadHistory(roomId, after) {
  let response = await window.chatAPI.loadHistory(roomId, after);
  if (roomId === state.roomId && after === undefined) document.querySelector('#load-older').hidden = !response.has_more;
  while (true) {
    for (const message of response.messages || []) addMessage(message, false);
    if (!response.messages?.length) break;
    const last = ChatProtocolState.nextCursor(response.messages, state.lastSequence.get(roomId) || 0);
    state.lastSequence.set(roomId, Math.max(state.lastSequence.get(roomId) || 0, last));
    if (!response.has_more || after === undefined) break;
    response = await window.chatAPI.loadHistory(roomId, last);
  }
  renderRooms(); if (roomId === state.roomId) renderMessages(after === undefined);
}
async function loadOlder() {
  const roomId = state.roomId; const messages = state.messages.get(roomId) || [];
  const first = Math.min(...messages.filter(message => message.sequence_id).map(message => message.sequence_id)); if (!Number.isFinite(first)) return;
  const response = await window.chatAPI.loadOlder(roomId, first); const target = document.querySelector('#messages'); const previousHeight = target.scrollHeight; const previousScroll = target.scrollTop;
  for (const message of response.messages || []) addMessage(message, false);
  if (roomId === state.roomId) { document.querySelector('#load-older').hidden = !response.has_more; renderMessages(); target.scrollTop = previousScroll + target.scrollHeight - previousHeight; }
}
function addMessage(message, render = true) {
  const duplicate = message.message_id && state.seen.has(message.message_id);
  if (message.message_id) state.seen.add(message.message_id);
  state.messages.set(message.room_id, ChatProtocolState.mergeMessages(state.messages.get(message.room_id) || [], [message]));
  if (message.sequence_id) state.lastSequence.set(message.room_id, Math.max(state.lastSequence.get(message.room_id) || 0, message.sequence_id));
  if (render && !duplicate && message.room_id !== state.roomId && message.sender?.username !== state.username) state.unread.set(message.room_id, (state.unread.get(message.room_id) || 0) + 1);
  if (render) { renderRooms(); if (message.room_id === state.roomId) renderMessages(); }
}
function renderMessages(forceScroll = false) {
  const target = document.querySelector('#messages'); if (!target) return;
  const nearBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 100; const previousScroll = target.scrollTop;
  const messages = state.messages.get(state.roomId) || []; target.replaceChildren();
  if (!messages.length) target.innerHTML = `<div class="empty-conversation"><span class="avatar group">${icon('chat')}</span><h2>Start the conversation</h2><p>A hello, a fresh idea, or a quick check-in.<br>Your next conversation starts here.</p></div>`;
  let lastDay = '';
  for (const message of messages) {
    const date = message.occurred_at ? new Date(message.occurred_at) : null; const validDate = date && !Number.isNaN(date.getTime());
    const day = validDate ? date.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' }) : '';
    if (day && day !== lastDay) { const divider = document.createElement('div'); divider.className = 'date-divider'; divider.textContent = day; target.append(divider); lastDay = day; }
    const mine = message.sender?.username === state.username;
    const row = document.createElement('article'); row.className = `message-row ${mine ? 'mine' : ''}`;
    const avatar = document.createElement('span'); avatar.className = 'avatar message-avatar'; avatar.textContent = initials(message.sender?.username);
    const content = document.createElement('div'); content.className = 'message-content';
    const author = document.createElement('span'); author.className = 'message-author'; author.textContent = mine ? 'You' : message.sender?.username || 'Unknown';
    const bubble = document.createElement('div'); bubble.className = 'bubble';
    const body = document.createElement('p'); body.textContent = message.file?.name || message.text || (message.kind !== 'text' ? 'Attachment' : ''); bubble.append(body);
    if (message.file?.file_id) {
      const download = document.createElement('button'); download.className = 'file-download secondary'; download.innerHTML = `${icon('download')}Download${message.file.size ? ` · ${Math.max(1, Math.round(message.file.size / 1024))} KB` : ''}`;
      download.onclick = () => void window.chatAPI.downloadFile(message.file.file_id, message.file.name).catch(showError); bubble.append(download);
    }
    const meta = document.createElement('div'); meta.className = 'message-meta';
    if (validDate) { const time = document.createElement('time'); time.dateTime = date.toISOString(); time.textContent = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }); meta.append(time); }
    if (mine) { const status = document.createElement('span'); status.className = `message-status ${message.status === 'failed' ? 'failed' : ''}`; status.textContent = ({ pending: 'Sending…', sent: 'Sent', delivered: 'Delivered', read: 'Read', failed: 'Failed to send' })[message.status] || 'Sent'; meta.append(status); }
    content.append(author, bubble, meta); row.append(avatar, content); target.append(row);
    if (message.message_id && message.sequence_id && !mine && !state.read.has(message.message_id) && document.hasFocus()) {
      state.read.add(message.message_id); void window.chatAPI.markRead(state.roomId, message.message_id).catch(() => state.read.delete(message.message_id));
    }
  }
  target.scrollTop = forceScroll || nearBottom ? target.scrollHeight : previousScroll;
}
function sendText() {
  const input = document.querySelector('#composer'); const text = input.value.trim(); if (!text) return;
  const clientMessageId = `client-${crypto.randomUUID()}`;
  addMessage({ room_id: state.roomId, client_message_id: clientMessageId, sender: { username: state.username }, kind: 'text', text, occurred_at: new Date().toISOString(), status: 'pending' });
  void window.chatAPI.sendMessage({ room_id: state.roomId, client_message_id: clientMessageId, kind: 'text', text }).catch(showError);
  input.value = ''; input.style.height = 'auto'; document.querySelector('#send').disabled = true; clearTimeout(typingTimer);
  void window.chatAPI.setTyping({ room_id: state.roomId, is_typing: false }); renderMessages(true); input.focus();
}
async function sendFile() {
  const roomId = state.roomId;
  try {
    const filePath = await window.chatAPI.chooseFile(); if (!filePath) return;
    const { file } = await window.chatAPI.uploadFile(filePath); const kind = file.content_type?.startsWith('image/') ? 'image' : 'file'; const clientMessageId = `client-${crypto.randomUUID()}`;
    addMessage({ room_id: roomId, client_message_id: clientMessageId, sender: { username: state.username }, kind, text: '', file, occurred_at: new Date().toISOString(), status: 'pending' });
    await window.chatAPI.sendMessage({ room_id: roomId, client_message_id: clientMessageId, kind, text: '', file_id: file.file_id });
  } catch (error) { showError(error); }
}
async function searchUsers() {
  const query = document.querySelector('#search').value.trim(); const list = document.querySelector('#results'); list.replaceChildren(); if (!query) return;
  try {
    const result = await window.chatAPI.searchUsers(query);
    if (!result.users?.length) { const note = document.createElement('li'); note.className = 'search-note'; note.textContent = 'No people found. Try another username.'; list.append(note); }
    for (const user of result.users || []) {
      const item = document.createElement('li'); const button = document.createElement('button'); button.className = 'person-result'; button.textContent = user.username;
      button.onclick = async () => { try { const { room } = await window.chatAPI.openDirectChat(user.username); state.rooms.set(room.room_id, room); list.replaceChildren(); document.querySelector('#search').value = ''; await selectRoom(room.room_id); } catch (error) { showError(error); } }; item.append(button); list.append(item);
    }
  } catch (error) { showError(error); }
}
async function createGroup() {
  try {
    const name = document.querySelector('#group-name').value.trim(); if (!name) return;
    const { room } = await window.chatAPI.createGroup(name); state.rooms.set(room.room_id, room);
    document.querySelector('#group-dialog').close(); document.querySelector('#group-name').value = ''; document.querySelector('#group-error').textContent = ''; await selectRoom(room.room_id);
  } catch (error) { document.querySelector('#group-error').textContent = error.message || 'Could not create this group.'; }
}
async function addGroupMember() {
  const feedback = document.querySelector('#member-feedback'); const errorLabel = document.querySelector('#member-error'); feedback.textContent = ''; errorLabel.textContent = '';
  try { const username = document.querySelector('#member-name').value.trim(); if (!username) return; await window.chatAPI.addGroupMember(state.roomId, username); feedback.textContent = `${username} was added to the group.`; document.querySelector('#member-name').value = ''; }
  catch (error) { errorLabel.textContent = error.message || 'Could not add this person.'; }
}
async function leaveGroup() {
  try { await window.chatAPI.leaveGroup(state.roomId); document.querySelector('#members-dialog').close(); }
  catch (error) { document.querySelector('#member-error').textContent = error.message || 'Could not leave this group.'; }
}
function showError(error) { const target = document.querySelector('#errors'); if (target) target.textContent = error.message || 'Something went wrong. Please try again.'; }
window.chatAPI.on('connection-state', value => { state.status = value; const status = document.querySelector('#status'); if (status) status.textContent = value; const dot = document.querySelector('#connection-dot'); if (dot) dot.classList.toggle('online', value === 'Connected'); });
window.chatAPI.on('message:created', payload => addMessage({ ...payload.data, occurred_at: payload.occurred_at }));
window.chatAPI.on('message:ack', payload => {
  const data = payload.data || {}; const message = [...state.messages.values()].flat().find(item => item.client_message_id === payload.request_id);
  if (message) { message.status = ChatProtocolState.ackStatus(payload) || message.status; message.message_id = data.message_id || message.message_id; if (message.room_id === state.roomId) renderMessages(); } if (data.code) showError(data);
});
window.chatAPI.on('server:error', payload => showError(payload.data || {}));
window.chatAPI.on('room:added', payload => { const room = payload.data; state.rooms.set(room.room_id, room); renderRooms(); });
window.chatAPI.on('room:removed', payload => { const roomId = payload.data?.room_id; state.rooms.delete(roomId); state.messages.delete(roomId); state.unread.delete(roomId); renderRooms(); if (roomId === state.roomId) void selectRoom('general').catch(showError); });
window.chatAPI.on('typing:changed', payload => { const data = payload.data || {}; const target = document.querySelector('#typing'); if (target && data.room_id === state.roomId) target.textContent = data.is_typing ? `${data.username} is typing…` : ''; });
window.chatAPI.on('presence:changed', payload => { const data = payload.data || {}; const target = document.querySelector('#presence'); if (target && data.room_id === state.roomId) target.textContent = `${data.username} is ${data.online ? 'online' : 'offline'}`; });
window.chatAPI.on('message:status', payload => { const data = payload.data || {}; for (const messages of state.messages.values()) for (const message of messages) if (message.message_id === data.message_id) message.status = data.status; if (data.room_id === state.roomId) renderMessages(); });
window.chatAPI.on('auth-error', () => { state.status = 'Offline'; renderLogin({ username: state.username }); });
window.addEventListener('focus', () => { if (document.querySelector('#messages')) renderMessages(); });
window.chatAPI.loadSettings().then(renderLogin).catch(() => renderLogin());
