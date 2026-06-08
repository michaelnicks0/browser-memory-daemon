const DEFAULTS = { daemonUrl: 'http://127.0.0.1:8765', apiToken: '', capturePaused: false };
let currentDomain = '';

function setStatus(value) {
  document.getElementById('status').textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
}

async function currentTab() {
  const tabs = await chrome.tabs.query({active: true, currentWindow: true});
  return tabs[0] || null;
}

async function loadCurrentDomain() {
  const tab = await currentTab();
  try {
    currentDomain = new URL(tab?.url || '').hostname.replace(/^www\./, '');
  } catch (_) {
    currentDomain = '';
  }
  document.getElementById('domain').textContent = currentDomain || 'No http(s) tab selected.';
}

async function config() {
  return chrome.storage.local.get(DEFAULTS);
}

async function togglePause() {
  const cfg = await config();
  await chrome.storage.local.set({ capturePaused: !cfg.capturePaused });
  setStatus(`capturePaused=${!cfg.capturePaused}`);
}

async function health() {
  const cfg = await config();
  const response = await fetch(`${normalizeDaemonUrl(cfg.daemonUrl)}/health`, { targetAddressSpace: 'loopback' });
  setStatus(await response.json());
}

async function daemonRequest(path, body) {
  const cfg = await config();
  if (!cfg.apiToken) throw new Error('API token is not configured. Open extension options first.');
  const response = await fetch(`${normalizeDaemonUrl(cfg.daemonUrl)}${path}`, {
    method: 'POST',
    headers: authHeaders(cfg.apiToken),
    body: JSON.stringify(body),
    targetAddressSpace: 'loopback'
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `${response.status} ${response.statusText}`);
  return payload;
}

async function blockCurrentDomain() {
  if (!currentDomain) throw new Error('No current domain to block.');
  const payload = await daemonRequest('/policy/rules', {rule_type: 'domain', pattern: currentDomain, action: 'block'});
  setStatus(payload);
}

async function forgetCurrentDomain() {
  if (!currentDomain) throw new Error('No current domain to forget.');
  if (!confirm(`Forget all stored memory for ${currentDomain}?`)) return;
  const payload = await daemonRequest('/forget', {domain: currentDomain});
  setStatus(payload);
}

async function openDashboard() {
  const cfg = await config();
  await chrome.tabs.create({url: `${normalizeDaemonUrl(cfg.daemonUrl)}/ui`});
}

function bind(id, fn) {
  document.getElementById(id).addEventListener('click', () => fn().catch((error) => setStatus(error.message)));
}

bind('pause', togglePause);
bind('health', health);
bind('open-dashboard', openDashboard);
bind('block-domain', blockCurrentDomain);
bind('forget-domain', forgetCurrentDomain);
loadCurrentDomain().catch((error) => setStatus(error.message));
