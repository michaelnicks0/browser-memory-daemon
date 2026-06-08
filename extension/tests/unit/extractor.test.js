const test = require('node:test');
const assert = require('node:assert/strict');
const { shouldSkipElement, shouldBlockUrl, extractTextFromTree, extractPageFromDocument, collapseWhitespace } = require('../../src/extractor.js');

function textNode(text) {
  return { nodeType: 3, textContent: text };
}

function elem(tagName, children = [], attrs = {}) {
  return {
    nodeType: 1,
    tagName,
    childNodes: children,
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null; }
  };
}

test('skip form and editable elements', () => {
  assert.equal(shouldSkipElement('input', { type: 'text' }), true);
  assert.equal(shouldSkipElement('textarea', {}), true);
  assert.equal(shouldSkipElement('div', { contenteditable: 'true' }), true);
  assert.equal(shouldSkipElement('article', {}), false);
});

test('blocks sensitive URLs before extraction', () => {
  assert.equal(shouldBlockUrl('https://example.com/account/settings'), true);
  assert.equal(shouldBlockUrl('http://127.0.0.1:3000/private'), true);
  assert.equal(shouldBlockUrl('http://10.0.0.1/status'), true);
  assert.equal(shouldBlockUrl('http://192.168.1.1/status'), true);
  assert.equal(shouldBlockUrl('http://[::1]/status'), true);
  assert.equal(shouldBlockUrl('https://discord.com/channels/@me'), true);
  assert.equal(shouldBlockUrl('https://www.chase.com/'), true);
  assert.equal(shouldBlockUrl('https://example.com/payment'), true);
  assert.equal(shouldBlockUrl('https://developer.chrome.com/docs/extensions/'), false);
});

test('extracts readable tree text without form secrets', () => {
  const tree = {
    tagName: 'ARTICLE',
    children: [
      { tagName: 'H1', text: 'Stirling Engines' },
      { tagName: 'P', text: 'Useful heat engine article.' },
      { tagName: 'INPUT', attrs: { type: 'password' }, text: 'do-not-capture' },
      { tagName: 'DIV', attrs: { contenteditable: 'true' }, text: 'private draft' }
    ]
  };
  const text = extractTextFromTree(tree);
  assert.match(text, /Stirling Engines/);
  assert.match(text, /Useful heat engine/);
  assert.doesNotMatch(text, /do-not-capture/);
  assert.doesNotMatch(text, /private draft/);
});

test('real document extraction uses skip traversal', () => {
  const doc = {
    title: 'Doc',
    location: { href: 'https://developer.chrome.com/docs/extensions/' },
    querySelector() { return null; },
    body: elem('BODY', [
      elem('H1', [textNode('Safe heading')]),
      elem('TEXTAREA', [textNode('private text area')]),
      elem('DIV', [textNode('private draft')], { contenteditable: 'true' }),
      elem('DIV', [textNode('hidden text')], { hidden: '' }),
      elem('DIV', [textNode('aria hidden text')], { 'aria-hidden': 'true' }),
      elem('DIV', [textNode('style hidden text')], { style: 'display: none' }),
      elem('P', [textNode('Visible paragraph')])
    ])
  };
  const payload = extractPageFromDocument(doc);
  assert.match(payload.text, /Safe heading/);
  assert.match(payload.text, /Visible paragraph/);
  assert.doesNotMatch(payload.text, /private text area/);
  assert.doesNotMatch(payload.text, /private draft/);
  assert.doesNotMatch(payload.text, /hidden text/);
  assert.doesNotMatch(payload.text, /aria hidden text/);
  assert.doesNotMatch(payload.text, /style hidden text/);
});

test('collapses whitespace', () => {
  assert.equal(collapseWhitespace(' a\n\t b   c '), 'a b c');
});
