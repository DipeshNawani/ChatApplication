const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const protocol = require('../src/shared/protocol-state');

function renderer() {
  const handlers = new Map();
  const elements = new Map();
  const receipts = [];
  const element = () => ({
    children: [], style: {}, classList: { toggle() {} },
    scrollHeight: 200, scrollTop: 0, clientHeight: 200, value: '',
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    querySelectorAll() { return []; }, reportValidity() { return true; }, setAttribute() {}, focus() {},
  });
  const context = vm.createContext({
    ChatProtocolState: protocol, clearTimeout, setTimeout,
    document: {
      querySelector(selector) { if (!elements.has(selector)) elements.set(selector, element()); return elements.get(selector); },
      querySelectorAll() { return []; }, createElement: element, hasFocus() { return true; },
    },
    window: { addEventListener() {}, chatAPI: {
      on(name, handler) { handlers.set(name, handler); },
      loadSettings() { return { then() { return { catch() {} }; } }; },
      markRead(room, id) { receipts.push([room, id]); return Promise.resolve(); },
    } },
  });
  const run = source => vm.runInContext(source, context);
  run(fs.readFileSync(path.join(__dirname, '../src/renderer/app.js'), 'utf8'));
  run("resetSession(); state.username = 'alice'; renderChat();");
  return { run, handlers, receipts, elements };
}

test('read receipt echoes do not send repeated receipts', () => {
  const ui = renderer();
  ui.run("addMessage({message_id:'m1',sequence_id:1,room_id:'general',sender:{username:'bob'},text:'hello',status:'sent'});");
  for (let n = 0; n < 10; n++) ui.handlers.get('message:status')({ data: { message_id: 'm1', room_id: 'general', status: 'read' } });
  assert.deepEqual(ui.receipts, [['general', 'm1']]);
});

test('background room acknowledgements update the matching message', () => {
  const ui = renderer();
  ui.run("state.messages.set('other', [{client_message_id:'pending-1',room_id:'other',status:'pending'}]);");
  ui.handlers.get('message:ack')({ request_id: 'pending-1', data: { code: 'MESSAGE_TOO_LONG', message: 'Too long' } });
  assert.equal(ui.run("state.messages.get('other')[0].status"), 'failed');
});

test('returning to login clears conversation and receipt state', () => {
  const ui = renderer();
  ui.run("state.messages.set('old-account', [{text:'private'}]); state.read.add('old-id'); state.unread.set('old-room', 3); renderLogin();");
  assert.equal(ui.run('state.messages.size'), 0);
  assert.equal(ui.run('state.read.size'), 0);
  assert.equal(ui.run('state.unread.size'), 0);
  assert.equal(ui.run('state.rooms.size'), 1);
});

test('new room notifications preserve the current conversation', () => {
  const ui = renderer();
  ui.handlers.get('room:added')({ data: { room_id: 'group-new', name: 'New team', kind: 'group' } });
  assert.equal(ui.run('state.roomId'), 'general');
  assert.equal(ui.run("state.rooms.has('group-new')"), true);
});

test('messages render user content as plain text', () => {
  const ui = renderer();
  ui.run("addMessage({message_id:'m1',room_id:'general',sender:{username:'bob'},text:'<img src=x onerror=alert(1)>',kind:'text'});");
  const all = node => [node, ...node.children.flatMap(all)];
  assert.ok(all(ui.elements.get('#messages')).some(node => node.textContent === '<img src=x onerror=alert(1)>'));
});

for (const mode of ['login', 'register']) {
  test(`${mode} rejection does not mislabel a server response as a connection failure`, async () => {
    const ui = renderer();
    ui.run(`renderLogin(); window.chatAPI.${mode} = async () => { throw new Error('Invalid username or password'); };`);
    ui.run("document.querySelector('#server').value = 'https://quantumbytes-chat.onrender.com'; document.querySelector('#username').value = 'alice'; document.querySelector('#password').value = 'password-123';");
    if (mode === 'login') ui.elements.get('#login-form').onsubmit({ preventDefault() {} });
    else ui.elements.get('#register').onclick();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(ui.elements.get('#status').textContent, mode === 'register' ? 'Registration unsuccessful' : 'Sign-in unsuccessful');
    assert.equal(ui.elements.get('#login-error').textContent, 'Invalid username or password');
  });
}
