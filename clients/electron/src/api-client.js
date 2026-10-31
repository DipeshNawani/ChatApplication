class ApiError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function normalizeUrl(value) {
  const trimmed = String(value || '').trim();
  try {
    if (!trimmed) throw new Error();
    const url = new URL(trimmed.includes('://') ? trimmed : `http://${trimmed}`);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error();
    return url.href.replace(/\/+$/, '');
  } catch {
    throw new ApiError('INVALID_SERVER_URL', 'Enter a valid server address, such as http://127.0.0.1:8000.');
  }
}

function normalizeErrorPayload(payload) {
  if (!payload) return { code: 'REQUEST_FAILED', message: 'Request failed' };
  if (typeof payload === 'string') return { code: 'REQUEST_FAILED', message: payload };
  if (payload.error && typeof payload.error === 'object') return payload.error;
  if (payload.detail && !Array.isArray(payload.detail) && typeof payload.detail === 'object') return payload.detail;
  if (payload.code || payload.message) return payload;
  return { code: 'REQUEST_FAILED', message: 'Request failed' };
}

function connectionError(error, baseUrl) {
  if (error instanceof ApiError) return error;
  if (['AbortError', 'TimeoutError'].includes(error.name)) {
    return new ApiError('SERVER_TIMEOUT', `The server at ${baseUrl} took too long to respond. It may be starting up; please try again.`);
  }
  const code = error.cause?.code || error.code;
  if (['CERT_HAS_EXPIRED', 'DEPTH_ZERO_SELF_SIGNED_CERT', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE'].includes(code)) {
    return new ApiError('TLS_ERROR', 'The server certificate could not be verified. Check the HTTPS address and certificate.');
  }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(new URL(baseUrl).hostname);
  return new ApiError('SERVER_UNREACHABLE', `Cannot reach the chat server at ${baseUrl}. ${local ? 'Start the backend with start-server.ps1, then try again.' : 'Check the server address and your network connection.'}`);
}

function createApiRequest({ getServerUrl, getToken = () => '', fetchImpl = (...args) => fetch(...args) }) {
  return async function apiRequest(pathname, options = {}) {
    const baseUrl = normalizeUrl(getServerUrl());
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), pathname.startsWith('/api/v1/auth/') ? 90000 : 15000);
    try {
      const token = getToken();
      const response = await fetchImpl(`${baseUrl}${pathname}`, {
        ...options, signal: controller.signal,
        headers: { ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });
      let body;
      try { body = await response.json(); }
      catch { throw new ApiError('INVALID_SERVER_RESPONSE', `The server at ${baseUrl} did not return a chat API response (HTTP ${response.status}). Check the server address.`); }
      if (!response.ok) {
        const detail = normalizeErrorPayload(body);
        throw new ApiError(detail.code || 'REQUEST_FAILED', detail.message || `Request failed (HTTP ${response.status}).`);
      }
      return body;
    } catch (error) { throw connectionError(error, baseUrl); }
    finally { clearTimeout(timer); }
  };
}

module.exports = { ApiError, normalizeUrl, normalizeErrorPayload, connectionError, createApiRequest };
