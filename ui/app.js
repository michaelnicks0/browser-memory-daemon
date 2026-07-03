const els = {
  token: document.querySelector('#token'),
  tokenStatus: document.querySelector('#token-status'),
  saveToken: document.querySelector('#save-token'),
  searchForm: document.querySelector('#search-form'),
  query: document.querySelector('#query'),
  recent: document.querySelector('#recent'),
  refreshRecent: document.querySelector('#refresh-recent'),
  timelineDate: document.querySelector('#timeline-date'),
  loadTimeline: document.querySelector('#load-timeline'),
  timeline: document.querySelector('#timeline'),
  results: document.querySelector('#results'),
  blockForm: document.querySelector('#block-form'),
  blockDomain: document.querySelector('#block-domain'),
  policyRules: document.querySelector('#policy-rules'),
  loadDoctor: document.querySelector('#load-doctor'),
  doctor: document.querySelector('#doctor'),
};

function bootstrapConfig() {
  const node = document.querySelector('#bmd-bootstrap');
  if (!node?.textContent) return {};
  try {
    return JSON.parse(node.textContent);
  } catch (_) {
    return {};
  }
}

const bootstrap = bootstrapConfig();

const state = {
  token: bootstrap.api_token || localStorage.getItem('bmd.apiToken') || '',
  tokenSource: bootstrap.api_token ? 'daemon' : (localStorage.getItem('bmd.apiToken') ? 'localStorage' : ''),
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  }[char]));
}

function setMuted(target, text) {
  target.classList.add('muted');
  target.textContent = text;
}

async function api(path, options = {}) {
  if (!state.token) throw new Error('API token is required');
  const headers = {
    ...(options.body ? {'content-type': 'application/json'} : {}),
    authorization: `Bearer ${state.token}`,
    ...(options.headers || {}),
  };
  const response = await fetch(path, {...options, headers});
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(payload.error || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function renderCaptureList(items, {target, empty = 'No captures.'}) {
  target.classList.remove('muted');
  if (!items?.length) {
    setMuted(target, empty);
    return;
  }
  target.innerHTML = items.map((item) => `
    <article class="item">
      <h3>${escapeHtml(item.title || '(untitled)')}</h3>
      <div class="meta">${escapeHtml(item.domain)} · ${escapeHtml(item.captured_at)} · ${escapeHtml(item.browser_profile || '')} · media=${escapeHtml(item.media_artifact_count || 0)}</div>
      <p class="snippet">${escapeHtml(item.snippet || '')}</p>
      <div class="actions">
        ${item.document_id ? `<button class="secondary" data-doc="${escapeHtml(item.document_id)}">Document</button>` : ''}
        ${item.snapshot_id ? `<button class="secondary" data-snapshot="${escapeHtml(item.snapshot_id)}">Snapshot</button>` : ''}
        ${item.domain ? `<button class="secondary" data-block-domain="${escapeHtml(item.domain)}">Block domain</button>` : ''}
        ${item.domain ? `<button class="danger" data-forget-domain="${escapeHtml(item.domain)}">Forget domain</button>` : ''}
      </div>
      <div class="meta">${escapeHtml(item.url)}</div>
    </article>
  `).join('');
}

function renderSearchResults(results) {
  els.results.classList.remove('muted');
  if (!results.length) {
    setMuted(els.results, 'No results.');
    return;
  }
  els.results.innerHTML = results.map((item) => `
    <article class="item">
      <h3>${escapeHtml(item.title || '(untitled)')}</h3>
      <div class="meta">${escapeHtml(item.domain)} · ${escapeHtml(item.captured_at)} · score ${Number(item.score || 0).toFixed(3)} · media=${escapeHtml(item.media_artifact_count || 0)}</div>
      <p class="snippet">${escapeHtml(item.snippet || '')}</p>
      <div class="actions">
        <button class="secondary" data-doc="${escapeHtml(item.document_id)}">Document</button>
        <button class="secondary" data-snapshot="${escapeHtml(item.snapshot_id)}">Snapshot</button>
        <button class="danger" data-forget-domain="${escapeHtml(item.domain)}">Forget domain</button>
      </div>
      <div class="meta">${escapeHtml(item.url)}</div>
    </article>
  `).join('');
}

function renderMediaArtifacts(items = []) {
  if (!items.length) return '<span class="muted">No media artifacts.</span>';
  return items.map((item) => `
    <div class="media-item">
      <strong>${escapeHtml(item.media_type)}:${escapeHtml(item.role || 'content')}</strong>
      <span class="meta">${escapeHtml(item.capture_status)} · ${escapeHtml(item.mime_type || '')} · ${escapeHtml(item.byte_size || 0)} bytes · ${escapeHtml(item.width || '')}×${escapeHtml(item.height || '')}</span>
      ${item.has_file ? `<button class="secondary" data-media="${escapeHtml(item.id)}">Open media</button>` : ''}
      <div class="meta">${escapeHtml(item.source_url)}</div>
    </div>
  `).join('');
}

function renderDocument(payload) {
  const doc = payload.document;
  els.results.classList.remove('muted');
  els.results.innerHTML = `
    <article class="item">
      <h3>${escapeHtml(doc.title || '(untitled document)')}</h3>
      <div class="meta">${escapeHtml(doc.domain)} · first ${escapeHtml(doc.first_seen_at)} · last ${escapeHtml(doc.last_seen_at)}</div>
      <p class="snippet">${escapeHtml(doc.canonical_url || doc.normalized_url)}</p>
      <h3>Snapshots</h3>
      <div class="list compact">
        ${payload.snapshots.map((snap) => `<button class="secondary" data-snapshot="${escapeHtml(snap.id)}">${escapeHtml(snap.captured_at)} · ${escapeHtml(snap.extraction_method)}</button>`).join('') || '<span class="muted">No snapshots.</span>'}
      </div>
      <h3>Visits</h3>
      <pre class="code">${escapeHtml(JSON.stringify(payload.visits, null, 2))}</pre>
      <h3>Visit lifecycle events</h3>
      <pre class="code">${escapeHtml(JSON.stringify(payload.visit_events || [], null, 2))}</pre>
      <h3>Media artifacts</h3>
      <div class="list compact">${renderMediaArtifacts(payload.media_artifacts || [])}</div>
      <h3>Chunk snippets</h3>
      <div class="list compact">${payload.chunks.map((chunk) => `<p class="snippet">${escapeHtml(chunk.snippet)}</p>`).join('')}</div>
    </article>
  `;
}

function renderSnapshot(payload) {
  const snap = payload.snapshot;
  const doc = payload.document || {};
  els.results.classList.remove('muted');
  els.results.innerHTML = `
    <article class="item">
      <h3>${escapeHtml(doc.title || '(untitled snapshot)')}</h3>
      <div class="meta">${escapeHtml(doc.domain || '')} · ${escapeHtml(snap.captured_at)} · ${escapeHtml(snap.extraction_method)}</div>
      <div class="meta">privacy=${escapeHtml(snap.privacy_class)} · redactions=${escapeHtml(snap.redaction_count)} · truncated=${escapeHtml(payload.text_truncated)}</div>
      <h3>Media artifacts</h3>
      <div class="list compact">${renderMediaArtifacts(payload.media_artifacts || [])}</div>
      <pre class="code">${escapeHtml(payload.text)}</pre>
    </article>
  `;
}

function renderRules(rules) {
  els.policyRules.classList.remove('muted');
  if (!rules.length) {
    setMuted(els.policyRules, 'No policy rules.');
    return;
  }
  els.policyRules.innerHTML = rules.map((rule) => `
    <div class="item">
      <strong>${escapeHtml(rule.action)}</strong> ${escapeHtml(rule.rule_type)} ${escapeHtml(rule.pattern)}
      <div class="actions"><button class="danger" data-delete-rule="${escapeHtml(rule.id)}">Delete rule</button></div>
    </div>
  `).join('');
}

function normalizeUrlPrefix(input) {
  const url = new URL(input);
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error('URL-prefix block rules must use http or https.');
  }
  if (!url.pathname) url.pathname = '/';
  return url.toString();
}

function blockRuleFromInput(input) {
  const value = String(input || '').trim();
  if (!value) throw new Error('Block rule value is required.');
  if (/^https?:\/\//i.test(value)) {
    return {rule_type: 'url-prefix', pattern: normalizeUrlPrefix(value), action: 'block'};
  }
  if (/^[^/?#\s]+:\d+(?:\/.*)?$/.test(value)) {
    return {rule_type: 'url-prefix', pattern: normalizeUrlPrefix(`http://${value}`), action: 'block'};
  }
  return {rule_type: 'domain', pattern: value, action: 'block'};
}

async function refreshRecent() {
  setMuted(els.recent, 'Loading…');
  const payload = await api('/recent?limit=25');
  renderCaptureList(payload.results, {target: els.recent});
}

async function loadTimeline() {
  setMuted(els.timeline, 'Loading…');
  const date = els.timelineDate.value || new Date().toISOString().slice(0, 10);
  els.timelineDate.value = date;
  const payload = await api(`/timeline?date=${encodeURIComponent(date)}&limit=100`);
  renderCaptureList(payload.items, {target: els.timeline, empty: 'No captures for that date.'});
}

async function loadRules() {
  const payload = await api('/policy/rules');
  renderRules(payload.rules);
}

async function loadDoctor() {
  els.doctor.classList.remove('muted');
  els.doctor.textContent = 'Running…';
  const payload = await api('/doctor');
  els.doctor.textContent = JSON.stringify(payload, null, 2);
  els.doctor.classList.toggle('ok', Boolean(payload.ok));
  els.doctor.classList.toggle('danger-text', !payload.ok);
}

async function search(event) {
  event.preventDefault();
  const query = els.query.value.trim();
  if (!query) return;
  setMuted(els.results, 'Searching…');
  const payload = await api(`/search?q=${encodeURIComponent(query)}&limit=20`);
  renderSearchResults(payload.results || []);
}

async function blockDomain(domain) {
  const body = blockRuleFromInput(domain);
  const payload = await api('/policy/rules', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  els.blockDomain.value = '';
  await loadRules();
  els.results.innerHTML = `<pre class="code">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
}

async function forgetDomain(domain) {
  const ok = confirm(`Forget all stored browser memory for ${domain}? This deletes matching rows, FTS entries, clean-text blobs, and media blobs.`);
  if (!ok) return;
  const payload = await api('/forget', {method: 'POST', body: JSON.stringify({domain})});
  els.results.innerHTML = `<pre class="code">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
  await refreshRecent();
}

async function openMediaArtifact(artifactId) {
  const response = await fetch(`/media-artifacts/${encodeURIComponent(artifactId)}`, {
    headers: {authorization: `Bearer ${state.token}`},
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `media fetch failed: ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank', 'noopener');
}

async function handleDelegatedClick(event) {
  const button = event.target.closest('button');
  if (!button) return;
  try {
    if (button.dataset.doc) {
      const payload = await api(`/documents/${encodeURIComponent(button.dataset.doc)}`);
      renderDocument(payload);
    } else if (button.dataset.snapshot) {
      const payload = await api(`/snapshots/${encodeURIComponent(button.dataset.snapshot)}`);
      renderSnapshot(payload);
    } else if (button.dataset.forgetDomain) {
      await forgetDomain(button.dataset.forgetDomain);
    } else if (button.dataset.blockDomain) {
      await blockDomain(button.dataset.blockDomain);
    } else if (button.dataset.media) {
      await openMediaArtifact(button.dataset.media);
    } else if (button.dataset.deleteRule) {
      await api(`/policy/rules/${encodeURIComponent(button.dataset.deleteRule)}`, {method: 'DELETE'});
      await loadRules();
    }
  } catch (error) {
    els.results.innerHTML = `<pre class="code danger-text">${escapeHtml(error.message)}</pre>`;
  }
}

function wire() {
  els.token.value = state.token;
  if (els.tokenStatus) {
    if (state.tokenSource === 'daemon') {
      els.tokenStatus.textContent = `Loaded from this daemon · policy=${bootstrap.policy_mode || 'unknown'} · storage=${bootstrap.storage_root || 'unknown'} · blobs=${bootstrap.blob_root || bootstrap.storage_root || 'unknown'}`;
    } else if (state.tokenSource === 'localStorage') {
      els.tokenStatus.textContent = 'Loaded saved browser override. The daemon can provide the token automatically on refresh.';
    } else {
      els.tokenStatus.textContent = 'No token available from daemon; paste one only if this page is served from somewhere else.';
    }
  }
  els.saveToken.addEventListener('click', () => {
    state.token = els.token.value.trim();
    state.tokenSource = 'localStorage';
    localStorage.setItem('bmd.apiToken', state.token);
    setMuted(els.results, 'Token saved in this browser localStorage.');
    if (els.tokenStatus) els.tokenStatus.textContent = 'Saved browser override. Refresh to return to daemon-provided token.';
  });
  els.searchForm.addEventListener('submit', (event) => search(event).catch((error) => setMuted(els.results, error.message)));
  els.refreshRecent.addEventListener('click', () => refreshRecent().catch((error) => setMuted(els.recent, error.message)));
  els.loadTimeline.addEventListener('click', () => loadTimeline().catch((error) => setMuted(els.timeline, error.message)));
  els.loadDoctor.addEventListener('click', () => loadDoctor().catch((error) => { els.doctor.textContent = error.message; }));
  els.blockForm.addEventListener('submit', (event) => {
    event.preventDefault();
    blockDomain(els.blockDomain.value.trim()).catch((error) => setMuted(els.policyRules, error.message));
  });
  document.addEventListener('click', handleDelegatedClick);
}

function bootDashboard() {
  wire();
  if (!state.token) {
    setMuted(els.recent, 'No daemon token was embedded. Open this UI through http://127.0.0.1:8765/ui or paste a token override.');
    setMuted(els.timeline, 'No token available.');
    els.doctor.textContent = 'No token available.';
    return;
  }
  setMuted(els.results, state.tokenSource === 'daemon' ? 'Token loaded from local daemon. Dashboard is refreshing.' : 'Token loaded from browser storage. Dashboard is refreshing.');
  refreshRecent().catch((error) => setMuted(els.recent, error.message));
  loadTimeline().catch((error) => setMuted(els.timeline, error.message));
  loadRules().catch((error) => setMuted(els.policyRules, error.message));
  loadDoctor().catch((error) => { els.doctor.textContent = error.message; });
}

bootDashboard();
