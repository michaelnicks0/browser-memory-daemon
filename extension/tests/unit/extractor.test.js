const test = require('node:test');
const assert = require('node:assert/strict');
const { shouldSkipElement, shouldBlockUrl, isRenderedElement, extractTextFromTree, extractMediaFromDocument, extractPageFromDocument, collapseWhitespace } = require('../../src/extractor.js');

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

test('all mode still skips hidden/form/editable/script/style/no-script extraction surfaces', () => {
  assert.equal(shouldSkipElement('input', { type: 'text' }, { policyMode: 'all' }), true);
  assert.equal(shouldSkipElement('textarea', {}, { policyMode: 'all' }), true);
  assert.equal(shouldSkipElement('div', { contenteditable: 'true' }, { policyMode: 'all' }), true);
  assert.equal(shouldSkipElement('script', {}, { policyMode: 'all' }), true);
  assert.equal(shouldSkipElement('style', {}, { policyMode: 'all' }), true);
  assert.equal(shouldSkipElement('noscript', {}, { policyMode: 'all' }), true);
});

test('strict mode skips form and editable elements', () => {
  assert.equal(shouldSkipElement('input', { type: 'text' }, { policyMode: 'strict' }), true);
  assert.equal(shouldSkipElement('textarea', {}, { policyMode: 'strict' }), true);
  assert.equal(shouldSkipElement('div', { contenteditable: 'true' }, { policyMode: 'strict' }), true);
  assert.equal(shouldSkipElement('article', {}, { policyMode: 'strict' }), false);
});

test('URL policy modes are adjustable', () => {
  assert.equal(shouldBlockUrl('https://example.com/account/settings'), false);
  assert.equal(shouldBlockUrl('http://127.0.0.1:3000/private'), false);
  assert.equal(shouldBlockUrl('chrome://settings'), false);

  assert.equal(shouldBlockUrl('https://example.com/account/settings', { policyMode: 'strict' }), true);
  assert.equal(shouldBlockUrl('http://127.0.0.1:3000/private', { policyMode: 'strict' }), true);
  assert.equal(shouldBlockUrl('http://10.0.0.1/status', { policyMode: 'strict' }), true);
  assert.equal(shouldBlockUrl('http://192.168.1.1/status', { policyMode: 'strict' }), true);
  assert.equal(shouldBlockUrl('http://[::1]/status', { policyMode: 'strict' }), true);
  assert.equal(shouldBlockUrl('https://discord.com/channels/@me', { policyMode: 'strict' }), true);
  assert.equal(shouldBlockUrl('https://www.chase.com/', { policyMode: 'strict' }), true);
  assert.equal(shouldBlockUrl('https://developer.chrome.com/docs/extensions/', { policyMode: 'strict' }), false);

  assert.equal(shouldBlockUrl('https://example.com/account/settings', { policyMode: 'balanced' }), false);
  assert.equal(shouldBlockUrl('https://www.chase.com/', { policyMode: 'balanced' }), true);
  assert.equal(shouldBlockUrl('https://www.chase.com/', { policyMode: 'recall' }), false);
});

test('all mode extracts readable tree text without URL filters but skips form/editable text', () => {
  const tree = {
    tagName: 'ARTICLE',
    children: [
      { tagName: 'H1', text: 'Stirling Engines' },
      { tagName: 'P', text: 'Useful heat engine article.' },
      { tagName: 'INPUT', attrs: { type: 'password' }, text: 'do-not-capture' },
      { tagName: 'DIV', attrs: { contenteditable: 'true' }, text: 'private draft' }
    ]
  };
  const text = extractTextFromTree(tree, { policyMode: 'all' });
  assert.match(text, /Stirling Engines/);
  assert.match(text, /Useful heat engine/);
  assert.doesNotMatch(text, /do-not-capture/);
  assert.doesNotMatch(text, /private draft/);
});

test('strict mode extracts readable tree text without form secrets', () => {
  const tree = {
    tagName: 'ARTICLE',
    children: [
      { tagName: 'H1', text: 'Stirling Engines' },
      { tagName: 'P', text: 'Useful heat engine article.' },
      { tagName: 'INPUT', attrs: { type: 'password' }, text: 'do-not-capture' },
      { tagName: 'DIV', attrs: { contenteditable: 'true' }, text: 'private draft' }
    ]
  };
  const text = extractTextFromTree(tree, { policyMode: 'strict' });
  assert.match(text, /Stirling Engines/);
  assert.match(text, /Useful heat engine/);
  assert.doesNotMatch(text, /do-not-capture/);
  assert.doesNotMatch(text, /private draft/);
});

test('real document extraction in all mode still skips hidden/form/editable surfaces', () => {
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
  const payload = extractPageFromDocument(doc, { policyMode: 'all' });
  assert.match(payload.text, /Safe heading/);
  assert.match(payload.text, /Visible paragraph/);
  assert.doesNotMatch(payload.text, /private text area/);
  assert.doesNotMatch(payload.text, /private draft/);
  assert.doesNotMatch(payload.text, /hidden text/);
  assert.doesNotMatch(payload.text, /aria hidden text/);
  assert.doesNotMatch(payload.text, /style hidden text/);
});

test('real document extraction uses strict skip traversal', () => {
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
  const payload = extractPageFromDocument(doc, { policyMode: 'strict' });
  assert.match(payload.text, /Safe heading/);
  assert.match(payload.text, /Visible paragraph/);
  assert.doesNotMatch(payload.text, /private text area/);
  assert.doesNotMatch(payload.text, /private draft/);
  assert.doesNotMatch(payload.text, /hidden text/);
  assert.doesNotMatch(payload.text, /aria hidden text/);
  assert.doesNotMatch(payload.text, /style hidden text/);
});

test('computed rendered visibility excludes class, responsive, and ancestor-hidden content', () => {
  const doc = {
    defaultView: {
      getComputedStyle(node) {
        return { display: 'block', visibility: 'visible', contentVisibility: 'visible', opacity: '1', ...(node.computedStyle || {}) };
      }
    }
  };
  const ancestor = { nodeType: 1, ownerDocument: doc, computedStyle: { display: 'none' }, getAttribute() { return null; } };
  const descendant = { nodeType: 1, ownerDocument: doc, parentElement: ancestor, computedStyle: { display: 'block' }, getAttribute() { return null; } };
  const responsive = { nodeType: 1, ownerDocument: doc, computedStyle: { display: 'none' }, getAttribute() { return null; } };
  const transparent = { nodeType: 1, ownerDocument: doc, computedStyle: { opacity: '0' }, getAttribute() { return null; } };
  const visible = { nodeType: 1, ownerDocument: doc, computedStyle: { display: 'contents' }, getAttribute() { return null; } };
  assert.equal(isRenderedElement(descendant), false);
  assert.equal(isRenderedElement(responsive), false);
  assert.equal(isRenderedElement(transparent), false);
  assert.equal(isRenderedElement(visible), true);
});

test('document traversal excludes computed-hidden subtrees and does not cross shadow roots', () => {
  const visible = elem('P', [textNode('Visible rendered paragraph')]);
  const classHidden = elem('DIV', [textNode('class hidden secret')]);
  classHidden.computedStyle = { display: 'none' };
  const ancestorHidden = elem('SECTION', [elem('P', [textNode('ancestor hidden secret')])]);
  ancestorHidden.computedStyle = { visibility: 'hidden' };
  const shadowHost = elem('DIV', [textNode('Light DOM text')]);
  shadowHost.shadowRoot = { nodeType: 11, childNodes: [elem('P', [textNode('open shadow secret')])] };
  const body = elem('BODY', [visible, classHidden, ancestorHidden, shadowHost]);
  const doc = {
    title: 'Rendered contract',
    location: { href: 'https://example.test/rendered' },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    defaultView: {
      getComputedStyle(node) {
        return { display: 'block', visibility: 'visible', contentVisibility: 'visible', opacity: '1', ...(node.computedStyle || {}) };
      }
    },
    body
  };
  function connect(node, parent = null) {
    if (!node || node.nodeType !== 1) return;
    node.ownerDocument = doc;
    node.parentElement = parent;
    for (const child of node.childNodes || []) connect(child, node);
  }
  connect(body);
  const payload = extractPageFromDocument(doc, { policyMode: 'all' });
  assert.equal(payload.extraction_method, 'dom-all-rendered-text-v2');
  assert.match(payload.text, /Visible rendered paragraph/);
  assert.match(payload.text, /Light DOM text/);
  assert.doesNotMatch(payload.text, /class hidden secret/);
  assert.doesNotMatch(payload.text, /ancestor hidden secret/);
  assert.doesNotMatch(payload.text, /open shadow secret/);
});

test('real document extraction records image and video artifacts without adding media text', () => {
  const image = {
    tagName: 'IMG',
    currentSrc: '/hero.png',
    alt: 'Hero image',
    title: 'Hero title',
    naturalWidth: 640,
    naturalHeight: 360,
    getAttribute(name) { return name === 'src' ? '/hero.png' : null; }
  };
  const poster = 'data:image/png;base64,aGVsbG8=';
  const video = {
    tagName: 'VIDEO',
    currentSrc: '/clip.webm',
    poster,
    title: 'Clip title',
    videoWidth: 1280,
    videoHeight: 720,
    duration: 12.5,
    getAttribute(name) { return name === 'poster' ? poster : null; },
    querySelector() { return { src: '/clip.webm', type: 'video/webm', getAttribute(name) { return name === 'type' ? 'video/webm' : null; } }; }
  };
  const doc = {
    title: 'Media Doc',
    location: { href: 'https://example.com/read' },
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector === 'img, picture source[srcset]') return [image];
      if (selector === 'video') return [video];
      return [];
    },
    body: elem('BODY', [elem('P', [textNode('Visible article text')])])
  };
  const media = extractMediaFromDocument(doc);
  assert.equal(media.length, 3);
  assert.deepEqual(media.map((item) => `${item.media_type}:${item.role}`).sort(), ['image:content', 'image:poster', 'video:content']);
  assert.equal(media.find((item) => item.role === 'content' && item.media_type === 'image').source_url, 'https://example.com/hero.png');
  const payload = extractPageFromDocument(doc, { policyMode: 'all' });
  assert.equal(payload.media_artifacts.length, 3);
  assert.match(payload.text, /Visible article text/);
  assert.doesNotMatch(payload.text, /Hero image/);
});

test('image extraction ignores empty-src document URL fallbacks', () => {
  const pageUrl = 'https://www.youtube.com/watch?v=abc123';
  const image = {
    tagName: 'IMG',
    currentSrc: pageUrl,
    src: pageUrl,
    alt: 'Fallback image',
    naturalWidth: 640,
    naturalHeight: 360,
    getAttribute(name) { return name === 'src' ? '' : null; }
  };
  const doc = {
    title: 'Fallback Doc',
    location: { href: pageUrl },
    querySelectorAll(selector) {
      if (selector === 'img, picture source[srcset]') return [image];
      if (selector === 'video') return [];
      return [];
    }
  };
  assert.deepEqual(extractMediaFromDocument(doc), []);
});

test('performance video resources are preserved even when image refs fill the cap', () => {
  const images = Array.from({ length: 60 }, (_, index) => ({
    tagName: 'IMG',
    currentSrc: `/image-${index}.png`,
    naturalWidth: 640,
    naturalHeight: 360,
    getAttribute(name) { return name === 'src' ? `/image-${index}.png` : null; }
  }));
  const doc = {
    title: 'Video Perf Doc',
    location: { href: 'https://x.com/example/status/1' },
    defaultView: {
      performance: {
        getEntriesByType(type) {
          if (type !== 'resource') return [];
          return [{ name: 'https://video.twimg.com/tweet_video/example.mp4', initiatorType: 'video', transferSize: 1234, encodedBodySize: 1234 }];
        }
      }
    },
    querySelectorAll(selector) {
      if (selector === 'img, picture source[srcset]') return images;
      if (selector === 'video') return [];
      return [];
    }
  };
  const media = extractMediaFromDocument(doc);
  assert.equal(media.length, 50);
  assert.equal(media.filter((item) => item.media_type === 'video').length, 1);
  const video = media.find((item) => item.media_type === 'video');
  assert.equal(video.source_url, 'https://video.twimg.com/tweet_video/example.mp4');
  assert.equal(video.mime_type, 'video/mp4');
});

test('collapses whitespace', () => {
  assert.equal(collapseWhitespace(' a\n\t b   c '), 'a b c');
});
