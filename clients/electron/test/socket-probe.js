const readline = require('node:readline');
const fs = require('node:fs');
const path = require('node:path');
const { io } = require('socket.io-client');

const [url, token] = process.argv.slice(2);
const socket = io(url, { auth: { token }, reconnection: true, reconnectionDelay: 100, reconnectionDelayMax: 500 });
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
const activeRooms = new Set();

function write(value) { process.stdout.write(`${JSON.stringify(value)}\n`); }

socket.on('connect', () => {
  write({ type: 'connected', sid: socket.id });
  for (const roomId of activeRooms) socket.emit('room:join', { data: { room_id: roomId } });
});
socket.on('connect_error', error => write({ type: 'connect_error', message: error.message, data: error.data }));
socket.on('disconnect', reason => write({ type: 'disconnected', reason }));
for (const event of ['connection:state', 'room:joined', 'room:added', 'room:removed', 'message:created', 'message:ack', 'message:status', 'typing:changed', 'presence:changed', 'server:error']) {
  socket.on(event, payload => write({ type: 'event', event, payload }));
}

input.on('line', line => {
  try {
    const command = JSON.parse(line);
    if (command.op === 'join') {
      activeRooms.add(command.roomId);
      socket.emit('room:join', { data: { room_id: command.roomId } });
    } else if (command.op === 'emit') socket.emit(command.event, command.payload);
    else if (command.op === 'disconnect') socket.disconnect();
    else if (command.op === 'connect') socket.connect();
    else if (command.op === 'history') {
      fetch(`${url}/api/v1/rooms/${encodeURIComponent(command.roomId)}/messages?limit=50`, { headers: { Authorization: `Bearer ${token}` } })
        .then(response => response.json()).then(payload => write({ type: 'history', roomId: command.roomId, payload }))
        .catch(error => write({ type: 'probe_error', message: error.message }));
    }
    else if (command.op === 'upload') {
      const buffer = fs.readFileSync(command.filePath);
      const form = new FormData();
      form.append('file', new Blob([buffer]), path.basename(command.filePath));
      fetch(`${url}/api/v1/files`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form })
        .then(async response => write({ type: 'upload', status: response.status, payload: await response.json() }))
        .catch(error => write({ type: 'probe_error', message: error.message }));
    }
    else if (command.op === 'exit') { socket.disconnect(); process.exit(0); }
  } catch (error) {
    write({ type: 'probe_error', message: error.message });
  }
});
