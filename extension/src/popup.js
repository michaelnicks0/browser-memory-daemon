const DEFAULTS = { daemonUrl: 'http://127.0.0.1:8765', apiToken: '', capturePaused: false };

async function togglePause() {
  const cfg = await chrome.storage.local.get(DEFAULTS);
  await chrome.storage.local.set({ capturePaused: !cfg.capturePaused });
  document.getElementById('status').textContent = `capturePaused=${!cfg.capturePaused}`;
}

async function health() {
  const cfg = await chrome.storage.local.get(DEFAULTS);
  const response = await fetch(`${normalizeDaemonUrl(cfg.daemonUrl)}/health`, { targetAddressSpace: 'loopback' });
  document.getElementById('status').textContent = await response.text();
}

document.getElementById('pause').addEventListener('click', togglePause);
document.getElementById('health').addEventListener('click', health);
