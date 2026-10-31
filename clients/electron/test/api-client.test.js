const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { normalizeUrl, createApiRequest } = require('../src/api-client');

test('normalizes server addresses and rejects missing or non-HTTP addresses', () => {
  assert.equal(normalizeUrl(' 127.0.0.1:8000/ '), 'http://127.0.0.1:8000');
  assert.equal(normalizeUrl('https://chat.example.com/'), 'https://chat.example.com');
  for (const value of ['', 'file:///server', 'http://', 'http://user:secret@example.com', 'https://example.com?token=x']) {
    assert.throws(() => normalizeUrl(value), { code: 'INVALID_SERVER_URL' });
  }
});

for (const mode of ['login', 'register']) {
  test(`${mode} reports an unavailable local server with startup instructions`, async () => {
    const request = createApiRequest({ getServerUrl: () => 'http://127.0.0.1:8000', fetchImpl: async () => { throw new TypeError('fetch failed', { cause: { code: 'ECONNREFUSED' } }); } });
    await assert.rejects(request(`/api/v1/auth/${mode}`), error => error.code === 'SERVER_UNREACHABLE' && error.message.includes('start-server.ps1') && error.message.includes('127.0.0.1:8000'));
  });
  test(`${mode} returns a successful authentication response`, async () => {
    const result = { access_token: 'test-token', user: { username: 'alice' } };
    const request = createApiRequest({ getServerUrl: () => 'http://127.0.0.1:8000', fetchImpl: async (url, options) => {
      assert.equal(url, `http://127.0.0.1:8000/api/v1/auth/${mode}`);
      assert.equal(options.method, 'POST');
      return { ok: true, json: async () => result };
    } });
    assert.deepEqual(await request(`/api/v1/auth/${mode}`, { method: 'POST' }), result);
  });
}

test('keeps invalid credentials distinct from connection failures', async () => {
  const request = createApiRequest({ getServerUrl: () => 'http://127.0.0.1:8000', fetchImpl: async () => ({ ok: false, status: 401, json: async () => ({ error: { code: 'INVALID_CREDENTIALS', message: 'Invalid username or password' } }) }) });
  await assert.rejects(request('/api/v1/auth/login'), { code: 'INVALID_CREDENTIALS', message: 'Invalid username or password' });
});

test('reports timeout and wrong-server responses clearly', async () => {
  const timedOut = createApiRequest({ getServerUrl: () => 'https://chat.example.com', fetchImpl: async () => { const error = new Error(); error.name = 'AbortError'; throw error; } });
  await assert.rejects(timedOut('/api/v1/auth/login'), { code: 'SERVER_TIMEOUT' });
  const wrongServer = createApiRequest({ getServerUrl: () => 'https://chat.example.com', fetchImpl: async () => ({ status: 502, json: async () => { throw new Error('HTML response'); } }) });
  await assert.rejects(wrongServer('/api/v1/auth/login'), { code: 'INVALID_SERVER_RESPONSE' });
});

test('preload preserves structured authentication errors without an IPC exception prefix', async () => {
  let api;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../src/preload.js'), 'utf8'), {
    require: () => ({ contextBridge: { exposeInMainWorld(_name, value) { api = value; } }, ipcRenderer: { invoke: async () => ({ error: { code: 'SERVER_UNREACHABLE', message: 'Start the backend with start-server.ps1.' } }) } }),
  });
  for (const mode of ['login', 'register']) {
    await assert.rejects(api[mode]({}), error => error.code === 'SERVER_UNREACHABLE' && error.message === 'Start the backend with start-server.ps1.');
  }
});
