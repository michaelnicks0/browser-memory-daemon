function normalizeDaemonUrl(url) {
  const trimmed = String(url || 'http://127.0.0.1:8765').replace(/\/+$/, '');
  return trimmed || 'http://127.0.0.1:8765';
}

function authHeaders(token) {
  return {
    'content-type': 'application/json',
    'authorization': `Bearer ${token}`
  };
}

if (typeof module !== 'undefined') {
  module.exports = { normalizeDaemonUrl, authHeaders };
}
