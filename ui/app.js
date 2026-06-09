const els = {
  token: document.querySelector('#token'),
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

const state = {
  token: localStorage.getItem('bmd.apiToken') || '',
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
      <div class="meta">${escapeHtml(item.domain)} · ${escapeHtml(item.captured_at)} · ${escapeHtml(item.browser_profile || '')}</div>
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
      <div class="meta">${escapeHtml(item.domain)} · ${escapeHtml(item.captured_at)} · score ${Number(item.score || 0).toFixed(3)}</div>
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
  const payload = await api('/policy/rules', {
    method: 'POST',
    body: JSON.stringify({rule_type: 'domain', pattern: domain, action: 'block'}),
  });
  els.blockDomain.value = '';
  await loadRules();
  els.results.innerHTML = `<pre class="code">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
}

async function forgetDomain(domain) {
  const ok = confirm(`Forget all stored browser memory for ${domain}? This deletes matching rows, FTS entries, and clean-text blobs.`);
  if (!ok) return;
  const payload = await api('/forget', {method: 'POST', body: JSON.stringify({domain})});
  els.results.innerHTML = `<pre class="code">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
  await refreshRecent();
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
  els.saveToken.addEventListener('click', () => {
    state.token = els.token.value.trim();
    localStorage.setItem('bmd.apiToken', state.token);
    setMuted(els.results, 'Token saved in this browser localStorage.');
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

wire();
if (state.token) {
  refreshRecent().catch((error) => setMuted(els.recent, error.message));
  loadRules().catch((error) => setMuted(els.policyRules, error.message));
}
