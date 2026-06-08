const DEFAULTS = { daemonUrl: 'http://127.0.0.1:8765', apiToken: '', capturePaused: false };

async function load() {
  const cfg = await chrome.storage.local.get(DEFAULTS);
  document.getElementById('daemonUrl').value = cfg.daemonUrl;
  document.getElementById('apiToken').value = cfg.apiToken;
  document.getElementById('capturePaused').checked = Boolean(cfg.capturePaused);
}

async function save() {
  await chrome.storage.local.set({
    daemonUrl: document.getElementById('daemonUrl').value,
    apiToken: document.getElementById('apiToken').value,
    capturePaused: document.getElementById('capturePaused').checked
  });
  document.getElementById('status').textContent = 'Saved';
}

document.getElementById('save').addEventListener('click', save);
load();
