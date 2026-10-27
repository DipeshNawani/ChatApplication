const { contextBridge, ipcRenderer } = require('electron');
const allowedEvents = new Set([
  'connection-state', 'message:created', 'message:ack', 'server:error',
  'room:joined', 'room:added', 'room:removed', 'typing:changed',
  'presence:changed', 'message:status', 'auth-error',
]);

contextBridge.exposeInMainWorld('chatAPI', {
  loadSettings: () => ipcRenderer.invoke('settings:load'),
  saveSettings: values => ipcRenderer.invoke('settings:save', values),
  login: values => ipcRenderer.invoke('auth:login', values),
  register: values => ipcRenderer.invoke('auth:register', values),
  joinRoom: roomId => ipcRenderer.invoke('room:join', roomId),
  sendMessage: payload => ipcRenderer.invoke('message:send', payload),
  setTyping: payload => ipcRenderer.invoke('typing:set', payload),
  loadHistory: (roomId, after) => ipcRenderer.invoke('history:load', roomId, after),
  loadOlder: (roomId, before) => ipcRenderer.invoke('history:older', roomId, before),
  markRead: (roomId, messageId) => ipcRenderer.invoke('message:read', roomId, messageId),
  searchUsers: query => ipcRenderer.invoke('users:search', query),
  openDirectChat: username => ipcRenderer.invoke('chat:direct', username),
  listRooms: () => ipcRenderer.invoke('rooms:list'),
  createGroup: name => ipcRenderer.invoke('group:create', name),
  addGroupMember: (roomId, username) => ipcRenderer.invoke('group:add-member', roomId, username),
  leaveGroup: roomId => ipcRenderer.invoke('group:leave', roomId),
  chooseFile: () => ipcRenderer.invoke('file:choose'),
  uploadFile: filePath => ipcRenderer.invoke('file:upload', filePath),
  downloadFile: (fileId, name) => ipcRenderer.invoke('file:download', fileId, name),
  on: (channel, handler) => {
    if (!allowedEvents.has(channel)) throw new Error('Unsupported event channel');
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on(channel, listener);
    return () => ipcRenderer.removeListener(channel, listener);
  },
});
