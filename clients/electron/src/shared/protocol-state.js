(function exposeProtocolState(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.ChatProtocolState = api;
})(typeof window !== 'undefined' ? window : globalThis, function createProtocolState() {
  function mergeMessages(current, incoming) {
    const byId = new Map();
    const byClientId = new Map();
    for (const message of current) {
      if (message.message_id) byId.set(message.message_id, message);
      if (message.client_message_id) byClientId.set(message.client_message_id, message);
    }
    for (const message of incoming) {
      const existing = (message.message_id && byId.get(message.message_id)) || (message.client_message_id && byClientId.get(message.client_message_id));
      if (existing) Object.assign(existing, message);
      else {
        current.push(message);
        if (message.message_id) byId.set(message.message_id, message);
        if (message.client_message_id) byClientId.set(message.client_message_id, message);
      }
    }
    current.sort((left, right) => (left.sequence_id || Number.MAX_SAFE_INTEGER) - (right.sequence_id || Number.MAX_SAFE_INTEGER));
    return current;
  }

  function ackStatus(payload) {
    const data = payload?.data || {};
    if (data.code) return 'failed';
    if (data.status === 'sent') return 'sent';
    return null;
  }

  function nextCursor(messages, previous = 0) {
    return messages.reduce((maximum, message) => Math.max(maximum, Number(message.sequence_id) || 0), previous);
  }

  return { mergeMessages, ackStatus, nextCursor };
});
