const DEFAULTS = { daemonUrl: 'http://127.0.0.1:8765', apiToken: '', capturePaused: false, policyMode: 'all', cdpRecorderEnabled: true, cdpRecorderDomains: ['x.com', 'twitter.com'] };
const CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY = 'cdpRecorderDefaultOnMigratedAt';

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

async function loadOutboxStatus() {
  const status = await requestOutboxStatus();
  document.getElementById('outboxStatus').textContent = JSON.stringify(status, null, 2);
}

async function load() {
  const cfg = await chrome.storage.local.get(DEFAULTS);
  if (!cfg[CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY]) {
    const migratedAt = new Date().toISOString();
    cfg.cdpRecorderEnabled = true;
    const migration = {
      cdpRecorderEnabled: true,
      [CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY]: migratedAt
    };
    await chrome.storage.local.set(migration);
  }
  document.getElementById('daemonUrl').value = cfg.daemonUrl;
  document.getElementById('apiToken').value = cfg.apiToken;
  document.getElementById('capturePaused').checked = Boolean(cfg.capturePaused);
  document.getElementById('policyMode').value = cfg.policyMode || 'all';
  document.getElementById('cdpRecorderEnabled').checked = Boolean(cfg.cdpRecorderEnabled);
  document.getElementById('cdpRecorderDomains').value = (Array.isArray(cfg.cdpRecorderDomains) ? cfg.cdpRecorderDomains : DEFAULTS.cdpRecorderDomains).join(',');
  await loadOutboxStatus();
}

async function save() {
  await chrome.storage.local.set({
    daemonUrl: document.getElementById('daemonUrl').value,
    apiToken: document.getElementById('apiToken').value,
    capturePaused: document.getElementById('capturePaused').checked,
    policyMode: document.getElementById('policyMode').value,
    cdpRecorderEnabled: document.getElementById('cdpRecorderEnabled').checked,
    cdpRecorderDomains: document.getElementById('cdpRecorderDomains').value.split(',').map((item) => item.trim()).filter(Boolean),
    [CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY]: new Date().toISOString()
  });
  document.getElementById('status').textContent = 'Saved';
  await loadOutboxStatus();
}

document.getElementById('save').addEventListener('click', save);
load();
