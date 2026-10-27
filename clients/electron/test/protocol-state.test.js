const test = require('node:test');
const assert = require('node:assert/strict');
const { mergeMessages, ackStatus, nextCursor } = require('../src/shared/protocol-state');

test('history and realtime messages deduplicate by message_id', () => {
  const messages = [];
  mergeMessages(messages, [{ message_id: 'm1', sequence_id: 1, text: 'first' }]);
  mergeMessages(messages, [{ message_id: 'm1', sequence_id: 1, text: 'first again' }]);
  assert.equal(messages.length, 1);
  assert.equal(messages[0].text, 'first again');
});

test('server echo updates pending message by client_message_id', () => {
  const messages = [{ client_message_id: 'client-1', status: 'pending', text: 'hello' }];
  mergeMessages(messages, [{ message_id: 'server-1', client_message_id: 'client-1', sequence_id: 2, status: 'sent' }]);
  assert.equal(messages.length, 1);
  assert.equal(messages[0].message_id, 'server-1');
  assert.equal(messages[0].status, 'sent');
});

test('sequence cursor advances monotonically', () => {
  assert.equal(nextCursor([{ sequence_id: 11 }, { sequence_id: 7 }], 5), 11);
});

test('ack status exposes server failure and success', () => {
  assert.equal(ackStatus({ data: { code: 'RATE_LIMITED' } }), 'failed');
  assert.equal(ackStatus({ data: { status: 'sent' } }), 'sent');
});
