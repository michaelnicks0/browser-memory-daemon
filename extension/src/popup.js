const DEFAULTS = { daemonUrl: 'http://127.0.0.1:8765', apiToken: '', capturePaused: false, policyMode: 'all', cdpRecorderEnabled: true, cdpRecorderDomains: ['x.com', 'twitter.com'], lastCdpRecorderStatus: null, lastCdpRecorderError: null };
let currentDomain = '';
let currentBlockRule = null;

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
    const url = new URL(tab?.url || '');
    currentDomain = url.hostname.replace(/^www\./, '');
    currentBlockRule = blockRuleForUrl(url);
  } catch (_) {
    currentDomain = '';
    currentBlockRule = null;
  }
  document.getElementById('domain').textContent = currentDomain || 'No http(s) tab selected.';
  const cfg = await config();
  document.getElementById('mode').textContent = `mode=${cfg.policyMode || 'all'} paused=${Boolean(cfg.capturePaused)} cdp=${Boolean(cfg.cdpRecorderEnabled)}`;
}

function blockRuleForUrl(url) {
  if (!['http:', 'https:'].includes(url.protocol)) return null;
  const hostname = url.hostname.replace(/^www\./, '');
  if ((hostname === 'localhost' || hostname.startsWith('127.')) && url.port) {
    return {rule_type: 'url-prefix', pattern: `${url.protocol}//${url.host}/`, action: 'block'};
  }
  return {rule_type: 'domain', pattern: hostname, action: 'block'};
}

async function config() {
  return chrome.storage.local.get(DEFAULTS);
}

function requestOutboxStatus() {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: 'BMD_OUTBOX_STATUS' }, (response) => {
      const error = chrome.runtime.lastError;
      if (error) return reject(new Error(error.message));
      if (!response?.ok) return reject(new Error(response?.error || 'outbox status unavailable'));
      resolve(response.result);
    });
  });
}

async function loadOutboxSummary() {
  const status = await requestOutboxStatus();
  const capture = status.capture || {};
  const lifecycle = status.lifecycle || {};
  const media = status.media || {};
  document.getElementById('outbox').textContent = status.available
    ? `outbox capture=${capture.count || 0}/${capture.max_items || 0} (${capture.serialized_bytes || 0}/${capture.max_bytes || 0} bytes, age=${Math.round((capture.oldest_age_ms || 0) / 1000)}s, attempts=${capture.attempts || 0}, errors=${capture.error_count || 0}, last=${capture.last_success_at || 'never'}); lifecycle=${lifecycle.count || 0}/${lifecycle.max_items || 0} (${lifecycle.serialized_bytes || 0}/${lifecycle.max_bytes || 0} bytes, age=${Math.round((lifecycle.oldest_age_ms || 0) / 1000)}s, attempts=${lifecycle.attempts || 0}, errors=${lifecycle.error_count || 0}, last=${lifecycle.last_success_at || 'never'}); media=${media.task_count || 0}/${media.max_tasks || 0} tasks, ${media.blob_bytes || 0}/${media.max_blob_bytes || 0} bytes; overflow=${status.last_overflow?.reason || 'none'}`
    : 'outbox unavailable';
  return status;
}

async function togglePause() {
  const cfg = await config();
  await chrome.storage.local.set({ capturePaused: !cfg.capturePaused });
  setStatus(`capturePaused=${!cfg.capturePaused}`);
  await loadCurrentDomain();
}

async function health() {
  const cfg = await config();
  const outbox = await loadOutboxSummary();
  const response = await fetch(`${normalizeDaemonUrl(cfg.daemonUrl)}/health`, { targetAddressSpace: 'loopback' });
  setStatus({
    extension: {
      policyMode: cfg.policyMode || 'all',
      capturePaused: Boolean(cfg.capturePaused),
      cdpRecorderEnabled: Boolean(cfg.cdpRecorderEnabled),
      cdpRecorderDomains: cfg.cdpRecorderDomains,
      lastCdpRecorderStatus: cfg.lastCdpRecorderStatus || null,
      lastCdpRecorderError: cfg.lastCdpRecorderError || null
    },
    outbox,
    daemon: await response.json()
  });
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
  if (!currentBlockRule) throw new Error('No current http(s) page to block.');
  const payload = await daemonRequest('/policy/rules', currentBlockRule);
  setStatus(payload);
}

async function forgetCurrentDomain() {
  if (!currentDomain) throw new Error('No current domain to forget.');
  const preview = await daemonRequest('/forget', {domain: currentDomain, dry_run: true});
  const selectedRecords = Number(preview.guard?.selected_records || 0);
  if (selectedRecords === 0) {
    setStatus(preview);
    return;
  }
  if (!confirm(`Forget ${preview.counts?.documents || 0} document(s) and ${selectedRecords} total stored record(s) for ${currentDomain}?`)) return;
  const payload = await daemonRequest('/forget', {domain: currentDomain, max_records: selectedRecords});
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
Promise.all([loadCurrentDomain(), loadOutboxSummary()]).catch((error) => setStatus(error.message));
