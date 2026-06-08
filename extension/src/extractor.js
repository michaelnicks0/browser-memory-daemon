(function () {
const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'OPTION']);
const SENSITIVE_URL_WORDS = new Set(['account', 'accounts', 'admin', 'auth', 'bank', 'bankofamerica', 'billing', 'card', 'chase', 'chat', 'checkout', 'discord', 'gmail', 'health', 'insurance', 'legal', 'login', 'mail', 'medical', 'mychart', 'oauth', 'outlook', 'password', 'patient', 'payment', 'paypal', 'profile', 'settings', 'signin', 'slack', 'tax', 'telegram', 'token']);

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

function shouldSkipElement(tagName, attrs = {}) {
  const tag = String(tagName || '').toUpperCase();
  if (SKIP_TAGS.has(tag)) return true;
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

function shouldBlockUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (!['http:', 'https:'].includes(url.protocol)) return true;
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (isPrivateHost(host)) return true;
    const words = `${host} ${url.pathname} ${url.search}`.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
    return words.some((word) => SENSITIVE_URL_WORDS.has(word));
  } catch (_) {
    return true;
  }
}

function extractTextFromTree(node) {
  if (!node) return '';
  if (typeof node === 'string') return collapseWhitespace(node);
  if (node.nodeType === 3) return collapseWhitespace(node.textContent || node.text || '');
  if (shouldSkipElement(node.tagName, node.attrs || node.attributes || {})) return '';
  const parts = [];
  if (node.text) parts.push(node.text);
  for (const child of node.children || []) {
    const childText = extractTextFromTree(child);
    if (childText) parts.push(childText);
  }
  return collapseWhitespace(parts.join(' '));
}

function extractTextFromDomNode(node) {
  if (!node) return '';
  if (node.nodeType === 3) return collapseWhitespace(node.textContent || '');
  if (node.nodeType !== 1 && node.nodeType !== 9 && node.nodeType !== 11) return '';
  const tag = String(node.tagName || '').toUpperCase();
  if (SKIP_TAGS.has(tag) || isEditableNode(node) || isHiddenNode(node)) return '';
  const parts = [];
  for (const child of Array.from(node.childNodes || [])) {
    const childText = extractTextFromDomNode(child);
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

function extractPageFromDocument(doc) {
  const metadata = metadataFromDocument(doc);
  if (shouldBlockUrl(metadata.url)) {
    return { ...metadata, text: '', blocked: true };
  }
  return {
    ...metadata,
    text: extractTextFromDomNode(doc.body)
  };
}

globalThis.extractPageFromDocument = extractPageFromDocument;
globalThis.shouldBlockBrowserMemoryUrl = shouldBlockUrl;

if (typeof module !== 'undefined') {
  module.exports = { shouldSkipElement, shouldBlockUrl, isPrivateHost, extractTextFromTree, extractTextFromDomNode, collapseWhitespace, metadataFromDocument, extractPageFromDocument };
}
})();
