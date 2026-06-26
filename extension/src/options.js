const DEFAULTS = { daemonUrl: 'http://127.0.0.1:8765', apiToken: '', capturePaused: false, policyMode: 'all', cdpRecorderEnabled: false, cdpRecorderDomains: ['x.com', 'twitter.com'] };
const CDP_RECORDER_DEFAULT_OFF_MIGRATION_KEY = 'cdpRecorderDefaultOffMigratedAt';

async function load() {
  const cfg = await chrome.storage.local.get(DEFAULTS);
  if (!cfg[CDP_RECORDER_DEFAULT_OFF_MIGRATION_KEY]) {
    const migratedAt = new Date().toISOString();
    const migration = { [CDP_RECORDER_DEFAULT_OFF_MIGRATION_KEY]: migratedAt };
    if (cfg.cdpRecorderEnabled !== false) {
      cfg.cdpRecorderEnabled = false;
      migration.cdpRecorderEnabled = false;
    }
    await chrome.storage.local.set(migration);
  }
  document.getElementById('daemonUrl').value = cfg.daemonUrl;
  document.getElementById('apiToken').value = cfg.apiToken;
  document.getElementById('capturePaused').checked = Boolean(cfg.capturePaused);
  document.getElementById('policyMode').value = cfg.policyMode || 'all';
  document.getElementById('cdpRecorderEnabled').checked = Boolean(cfg.cdpRecorderEnabled);
  document.getElementById('cdpRecorderDomains').value = (Array.isArray(cfg.cdpRecorderDomains) ? cfg.cdpRecorderDomains : DEFAULTS.cdpRecorderDomains).join(',');
}

async function save() {
  await chrome.storage.local.set({
    daemonUrl: document.getElementById('daemonUrl').value,
    apiToken: document.getElementById('apiToken').value,
    capturePaused: document.getElementById('capturePaused').checked,
    policyMode: document.getElementById('policyMode').value,
    cdpRecorderEnabled: document.getElementById('cdpRecorderEnabled').checked,
    cdpRecorderDomains: document.getElementById('cdpRecorderDomains').value.split(',').map((item) => item.trim()).filter(Boolean),
    [CDP_RECORDER_DEFAULT_OFF_MIGRATION_KEY]: new Date().toISOString()
  });
  document.getElementById('status').textContent = 'Saved';
}

document.getElementById('save').addEventListener('click', save);
load();
