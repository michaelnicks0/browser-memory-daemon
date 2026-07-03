import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '../../..');
const appScript = fs.readFileSync(path.join(root, 'ui/app.js'), 'utf8');

class ClassList {
  constructor(initial = []) {
    this.values = new Set(initial);
  }
  add(name) {
    this.values.add(name);
  }
  remove(name) {
    this.values.delete(name);
  }
  toggle(name, force) {
    const enabled = force === undefined ? !this.values.has(name) : Boolean(force);
    if (enabled) this.values.add(name);
    else this.values.delete(name);
    return enabled;
  }
  contains(name) {
    return this.values.has(name);
  }
}

class Element {
  constructor(id, {textContent = '', value = '', classes = []} = {}) {
    this.id = id;
    this.textContent = textContent;
    this.innerHTML = '';
    this.value = value;
    this.dataset = {};
    this.listeners = new Map();
    this.classList = new ClassList(classes);
  }
  addEventListener(type, callback) {
    this.listeners.set(type, callback);
  }
  closest() {
    return null;
  }
}

function makeResponse(payload, {ok = true, status = 200, statusText = 'OK'} = {}) {
  return {
    ok,
    status,
    statusText,
    text: async () => JSON.stringify(payload),
    blob: async () => ({size: 0}),
  };
}

function makeDom({bootstrapPayload = null, localToken = '', fetchImpl}) {
  const elements = new Map();
  const selectorIds = [
    'token',
    'token-status',
    'save-token',
    'search-form',
    'query',
    'recent',
    'refresh-recent',
    'timeline-date',
    'load-timeline',
    'timeline',
    'results',
    'block-form',
    'block-domain',
    'policy-rules',
    'load-doctor',
    'doctor',
  ];
  for (const id of selectorIds) {
    const classes = ['recent', 'timeline', 'results', 'policy-rules'].includes(id) ? ['muted'] : [];
    elements.set(`#${id}`, new Element(id, {classes}));
  }
  if (bootstrapPayload !== null) {
    elements.set('#bmd-bootstrap', new Element('bmd-bootstrap', {textContent: JSON.stringify(bootstrapPayload)}));
  }
  const documentListeners = new Map();
  const localStorageData = new Map(localToken ? [['bmd.apiToken', localToken]] : []);
  const context = {
    console,
    setTimeout,
    clearTimeout,
    URL,
    window: {open: () => null},
    confirm: () => true,
    fetch: fetchImpl,
    localStorage: {
      getItem: (key) => localStorageData.get(key) || null,
      setItem: (key, value) => localStorageData.set(key, String(value)),
    },
    document: {
      querySelector: (selector) => elements.get(selector) || null,
      addEventListener: (type, callback) => documentListeners.set(type, callback),
    },
    __elements: elements,
    __documentListeners: documentListeners,
  };
  context.window.document = context.document;
  context.window.localStorage = context.localStorage;
  return vm.createContext(context);
}

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function runScenario(name, context) {
  vm.runInContext(appScript, context, {filename: 'ui/app.js'});
  await settle();
  return context.__elements;
}

async function testDaemonBootstrapInitialEmptyState() {
  const calls = [];
  const context = makeDom({
    bootstrapPayload: {
      api_token: 'test-token',
      policy_mode: 'all',
      storage_root: '/tmp/bmd-ui-smoke',
    },
    fetchImpl: async (url, options = {}) => {
      calls.push({url, headers: options.headers || {}});
      assert.equal(options.headers?.authorization, 'Bearer test-token');
      if (url.startsWith('/recent')) return makeResponse({results: []});
      if (url.startsWith('/timeline')) return makeResponse({count: 0, items: []});
      if (url === '/policy/rules') return makeResponse({rules: []});
      if (url === '/doctor') return makeResponse({ok: true, database: {counts: {}}, storage: {}});
      throw new Error(`unexpected API call: ${url}`);
    },
  });

  const elements = await runScenario('daemon bootstrap initial empty state', context);

  assert.equal(elements.get('#token').value, 'test-token');
  assert.match(elements.get('#token-status').textContent, /Loaded from this daemon/);
  assert.match(elements.get('#token-status').textContent, /policy=all/);
  assert.equal(elements.get('#recent').textContent, 'No captures.');
  assert.equal(elements.get('#timeline').textContent, 'No captures for that date.');
  assert.equal(elements.get('#policy-rules').textContent, 'No policy rules.');
  assert.match(elements.get('#doctor').textContent, /"ok": true/);
  assert.match(elements.get('#results').textContent, /Token loaded from local daemon/);
  assert.deepEqual(calls.map((call) => call.url).sort(), ['/doctor', '/policy/rules', '/recent?limit=25', calls.find((call) => call.url.startsWith('/timeline?date='))?.url].sort());
}

async function testNoTokenStateDoesNotCallApi() {
  const calls = [];
  const context = makeDom({
    bootstrapPayload: null,
    fetchImpl: async (url) => {
      calls.push({url});
      return makeResponse({});
    },
  });

  const elements = await runScenario('no token state', context);

  assert.equal(calls.length, 0);
  assert.match(elements.get('#token-status').textContent, /No token available/);
  assert.match(elements.get('#recent').textContent, /No daemon token was embedded/);
  assert.equal(elements.get('#timeline').textContent, 'No token available.');
  assert.equal(elements.get('#doctor').textContent, 'No token available.');
}

async function testInitialApiErrorRendersPanelErrorState() {
  const calls = [];
  const context = makeDom({
    bootstrapPayload: {
      api_token: 'test-token',
      policy_mode: 'all',
      storage_root: '/tmp/bmd-ui-smoke',
    },
    fetchImpl: async (url, options = {}) => {
      calls.push({url, headers: options.headers || {}});
      assert.equal(options.headers?.authorization, 'Bearer test-token');
      if (url.startsWith('/recent')) return makeResponse({error: 'daemon unavailable'}, {ok: false, status: 503, statusText: 'Unavailable'});
      if (url.startsWith('/timeline')) return makeResponse({count: 0, items: []});
      if (url === '/policy/rules') return makeResponse({rules: []});
      if (url === '/doctor') return makeResponse({ok: true});
      throw new Error(`unexpected API call: ${url}`);
    },
  });

  const elements = await runScenario('API error panel state', context);

  assert.ok(calls.some((call) => call.url.startsWith('/recent')));
  assert.equal(elements.get('#recent').textContent, 'daemon unavailable');
  assert.equal(elements.get('#timeline').textContent, 'No captures for that date.');
  assert.equal(elements.get('#policy-rules').textContent, 'No policy rules.');
}

await testDaemonBootstrapInitialEmptyState();
await testNoTokenStateDoesNotCallApi();
await testInitialApiErrorRendersPanelErrorState();
console.log('ui dashboard smoke runner passed');
