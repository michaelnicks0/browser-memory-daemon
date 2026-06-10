(function () {
const STRICT_SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'OPTION']);
const ALL_MODE_SKIP_TAGS = STRICT_SKIP_TAGS;
const SENSITIVE_URL_WORDS = new Set(['account', 'accounts', 'admin', 'auth', 'bank', 'bankofamerica', 'billing', 'card', 'chase', 'chat', 'checkout', 'discord', 'gmail', 'health', 'insurance', 'legal', 'login', 'mail', 'medical', 'mychart', 'oauth', 'outlook', 'password', 'patient', 'payment', 'paypal', 'profile', 'settings', 'signin', 'slack', 'tax', 'telegram', 'token']);
const BLOCKED_DOMAIN_SUFFIXES = new Set(['accounts.google.com', 'bankofamerica.com', 'capitalone.com', 'chase.com', 'mail.google.com', 'outlook.live.com', 'outlook.office.com', 'paypal.com', 'wellsfargo.com']);
const BALANCED_QUERY_KEYS = new Set(['access_token', 'api_key', 'password', 'refresh_token', 'session', 'sessionid', 'sid', 'token']);
const STRICT_QUERY_KEYS = new Set(['access_token', 'api_key', 'auth', 'code', 'key', 'magic', 'password', 'refresh_token', 'session', 'sessionid', 'sid', 'state', 'token']);
const MAX_MEDIA_REFS = 50;
const MAX_DATA_URL_REF_CHARS = 1_000_000;

function normalizePolicyMode(policyMode) {
  const mode = String(policyMode || 'all').toLowerCase();
  return ['all', 'recall', 'balanced', 'strict'].includes(mode) ? mode : 'all';
}

function isAllMode(options = {}) {
  return normalizePolicyMode(options.policyMode) === 'all';
}

function attrValue(node, name) {
  if (!node) return undefined;
  if (node.attrs && Object.prototype.hasOwnProperty.call(node.attrs, name)) return node.attrs[name];
  if (typeof node.getAttribute === 'function') {
    const value = node.getAttribute(name);
    return value === null ? undefined : value;
  }
  if (node.attributes && Object.prototype.hasOwnProperty.call(node.attributes, name)) {
    const value = node.attributes[name];
    return value && typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, 'value') ? value.value : value;
  }
  return undefined;
}

function formValue(node) {
  if (!node) return '';
  const values = [];
  for (const key of ['value', 'checked', 'selected', 'placeholder', 'aria-label']) {
    const value = node[key] !== undefined ? node[key] : attrValue(node, key);
    if (value !== undefined && value !== null && String(value).trim()) values.push(String(value));
  }
  return collapseWhitespace(values.join(' '));
}

function isEditableNode(node) {
  const editable = attrValue(node, 'contenteditable') ?? attrValue(node, 'contentEditable');
  return editable === true || editable === 'true' || editable === '';
}

function isHiddenNode(node) {
  if (attrValue(node, 'hidden') !== undefined) return true;
  if (String(attrValue(node, 'aria-hidden') || '').toLowerCase() === 'true') return true;
  const style = String(attrValue(node, 'style') || '').toLowerCase().replace(/\s+/g, '');
  return style.includes('display:none') || style.includes('visibility:hidden');
}

function shouldSkipElement(tagName, attrs = {}, options = {}) {
  const tag = String(tagName || '').toUpperCase();
  if (isAllMode(options)) {
    if (ALL_MODE_SKIP_TAGS.has(tag)) return true;
    const editable = attrs.contenteditable ?? attrs.contentEditable;
    return editable === true || editable === 'true' || editable === '';
  }
  if (STRICT_SKIP_TAGS.has(tag)) return true;
  const editable = attrs.contenteditable ?? attrs.contentEditable;
  if (editable === true || editable === 'true' || editable === '') return true;
  const type = String(attrs.type || '').toLowerCase();
  if (tag === 'INPUT' || type === 'password') return true;
  return false;
}

function collapseWhitespace(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function isPrivateHost(host) {
  const clean = String(host || '').toLowerCase().replace(/[\[\]]/g, '').replace(/\.$/, '');
  if (clean === 'localhost' || clean.endsWith('.localhost') || clean === '::1' || clean.startsWith('127.')) return true;
  if (clean.startsWith('10.') || clean.startsWith('192.168.') || clean.startsWith('169.254.')) return true;
  const match172 = clean.match(/^172\.(\d+)\./);
  if (match172) {
    const second = Number(match172[1]);
    if (second >= 16 && second <= 31) return true;
  }
  return clean.startsWith('fc') || clean.startsWith('fd') || clean.startsWith('fe80:');
}

function hostMatchesSuffix(host, suffix) {
  return host === suffix || host.endsWith(`.${suffix}`);
}

function shouldBlockUrl(rawUrl, options = {}) {
  const mode = normalizePolicyMode(options.policyMode);
  if (mode === 'all') return false;
  try {
    const url = new URL(rawUrl);
    if (!['http:', 'https:'].includes(url.protocol)) return true;
    if (mode === 'recall') return false;
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (isPrivateHost(host)) return true;
    for (const suffix of BLOCKED_DOMAIN_SUFFIXES) {
      if (hostMatchesSuffix(host, suffix)) return true;
    }
    const queryKeys = Array.from(url.searchParams.keys()).map((key) => key.toLowerCase());
    const blockedQueryKeys = mode === 'strict' ? STRICT_QUERY_KEYS : BALANCED_QUERY_KEYS;
    if (queryKeys.some((key) => blockedQueryKeys.has(key))) return true;
    if (mode === 'balanced') return false;
    const words = `${host} ${url.pathname} ${url.search}`.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
    return words.some((word) => SENSITIVE_URL_WORDS.has(word));
  } catch (_) {
    return mode !== 'all';
  }
}

function extractTextFromTree(node, options = {}) {
  if (!node) return '';
  if (typeof node === 'string') return collapseWhitespace(node);
  if (node.nodeType === 3) return collapseWhitespace(node.textContent || node.text || '');
  if (shouldSkipElement(node.tagName, node.attrs || node.attributes || {}, options)) return '';
  const parts = [];
  const tag = String(node.tagName || '').toUpperCase();
  if (isAllMode(options) && ['INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'BUTTON'].includes(tag)) {
    const value = formValue(node);
    if (value) parts.push(value);
  }
  if (node.text) parts.push(node.text);
  for (const child of node.children || []) {
    const childText = extractTextFromTree(child, options);
    if (childText) parts.push(childText);
  }
  return collapseWhitespace(parts.join(' '));
}

function extractTextFromDomNode(node, options = {}) {
  if (!node) return '';
  if (node.nodeType === 3) return collapseWhitespace(node.textContent || '');
  if (node.nodeType !== 1 && node.nodeType !== 9 && node.nodeType !== 11) return '';
  const tag = String(node.tagName || '').toUpperCase();
  if (shouldSkipElement(tag, {}, options)) return '';
  if (isEditableNode(node) || isHiddenNode(node)) return '';
  const parts = [];
  if (isAllMode(options) && ['INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'BUTTON'].includes(tag)) {
    const value = formValue(node);
    if (value) parts.push(value);
  }
  for (const child of Array.from(node.childNodes || [])) {
    const childText = extractTextFromDomNode(child, options);
    if (childText) parts.push(childText);
  }
  return collapseWhitespace(parts.join(' '));
}

function metadataFromDocument(doc) {
  const canonical = doc.querySelector?.('link[rel="canonical"]')?.href || '';
  return {
    title: doc.title || '',
    url: doc.location?.href || '',
    canonical_url: canonical,
    captured_at: new Date().toISOString(),
    extraction_method: 'dom-visible-text-v1'
  };
}

function absoluteMediaUrl(value, doc) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (raw.startsWith('data:') && raw.length > MAX_DATA_URL_REF_CHARS) return '';
  try {
    return new URL(raw, doc.location?.href || undefined).href;
  } catch (_) {
    return raw;
  }
}

function isDocumentUrlFallback(sourceUrl, doc) {
  const pageUrl = String(doc.location?.href || '').trim();
  if (!sourceUrl || !pageUrl) return false;
  try {
    return new URL(sourceUrl, pageUrl).href === new URL(pageUrl).href;
  } catch (_) {
    return String(sourceUrl).trim() === pageUrl;
  }
}

function mediaDimensions(element) {
  const width = Number(element.naturalWidth || element.videoWidth || element.width || element.clientWidth || 0);
  const height = Number(element.naturalHeight || element.videoHeight || element.height || element.clientHeight || 0);
  return { width: Number.isFinite(width) ? Math.max(0, Math.round(width)) : 0, height: Number.isFinite(height) ? Math.max(0, Math.round(height)) : 0 };
}

function isLikelyTrackingMedia(element) {
  const { width, height } = mediaDimensions(element);
  return width > 0 && height > 0 && width <= 1 && height <= 1;
}

function pushMediaRef(refs, seen, ref) {
  if (!ref || !ref.source_url || refs.length >= MAX_MEDIA_REFS) return;
  const key = [ref.media_type, ref.role || 'content', ref.source_url].join('|');
  if (seen.has(key)) return;
  seen.add(key);
  refs.push(ref);
}

function extractMediaFromDocument(doc) {
  const refs = [];
  const seen = new Set();
  const images = Array.from(doc.querySelectorAll?.('img, picture source[srcset]') || []);
  for (const image of images) {
    if (isHiddenNode(image) || isLikelyTrackingMedia(image)) continue;
    const source = image.currentSrc || image.src || image.srcset?.split(',')[0]?.trim()?.split(/\s+/)[0] || image.getAttribute?.('src') || image.getAttribute?.('srcset')?.split(',')[0]?.trim()?.split(/\s+/)[0] || '';
    const sourceUrl = absoluteMediaUrl(source, doc);
    if (!sourceUrl || isDocumentUrlFallback(sourceUrl, doc)) continue;
    const dims = mediaDimensions(image);
    pushMediaRef(refs, seen, {
      media_type: 'image',
      role: 'content',
      source_url: sourceUrl,
      alt_text: image.alt || image.getAttribute?.('alt') || '',
      title: image.title || image.getAttribute?.('title') || '',
      mime_type: image.type || image.getAttribute?.('type') || '',
      width: dims.width,
      height: dims.height,
      metadata: { tag: String(image.tagName || '').toLowerCase() }
    });
  }
  const videos = Array.from(doc.querySelectorAll?.('video') || []);
  for (const video of videos) {
    if (isHiddenNode(video)) continue;
    const dims = mediaDimensions(video);
    const poster = absoluteMediaUrl(video.poster || video.getAttribute?.('poster') || '', doc);
    if (poster) {
      pushMediaRef(refs, seen, {
        media_type: 'image',
        role: 'poster',
        source_url: poster,
        alt_text: video.getAttribute?.('aria-label') || '',
        title: video.title || video.getAttribute?.('title') || '',
        width: dims.width,
        height: dims.height,
        metadata: { tag: 'video', source: 'poster' }
      });
    }
    const source = video.currentSrc || video.src || video.querySelector?.('source[src]')?.src || video.querySelector?.('source[src]')?.getAttribute?.('src') || '';
    const sourceUrl = absoluteMediaUrl(source, doc);
    if (!sourceUrl) continue;
    pushMediaRef(refs, seen, {
      media_type: 'video',
      role: 'content',
      source_url: sourceUrl,
      alt_text: video.getAttribute?.('aria-label') || '',
      title: video.title || video.getAttribute?.('title') || '',
      mime_type: video.querySelector?.('source[src]')?.type || video.querySelector?.('source[src]')?.getAttribute?.('type') || '',
      width: dims.width,
      height: dims.height,
      duration_seconds: Number.isFinite(video.duration) ? video.duration : undefined,
      metadata: { tag: 'video' }
    });
  }
  return refs;
}

function extractPageFromDocument(doc, options = {}) {
  const mode = normalizePolicyMode(options.policyMode);
  const metadata = metadataFromDocument(doc);
  if (shouldBlockUrl(metadata.url, { policyMode: mode })) {
    return { ...metadata, text: '', blocked: true, policy_mode: mode };
  }
  return {
    ...metadata,
    extraction_method: mode === 'all' ? 'dom-all-text-v1' : metadata.extraction_method,
    policy_mode: mode,
    text: extractTextFromDomNode(doc.body, { policyMode: mode }),
    media_artifacts: extractMediaFromDocument(doc)
  };
}

globalThis.extractPageFromDocument = extractPageFromDocument;
globalThis.extractMediaFromDocument = extractMediaFromDocument;
globalThis.shouldBlockBrowserMemoryUrl = shouldBlockUrl;
globalThis.normalizeBrowserMemoryPolicyMode = normalizePolicyMode;

if (typeof module !== 'undefined') {
  module.exports = { shouldSkipElement, shouldBlockUrl, isPrivateHost, extractTextFromTree, extractTextFromDomNode, collapseWhitespace, metadataFromDocument, extractMediaFromDocument, extractPageFromDocument, normalizePolicyMode };
}
})();
