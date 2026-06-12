const test = require('node:test');
const assert = require('node:assert/strict');
const {
  shouldRecordTabUrl,
  cdpMediaCandidate,
  cdpMediaArtifactPayload,
  cdpArtifactId,
  approxBase64Bytes
} = require('../../src/cdp_recorder.js');

test('CDP recorder only attaches to configured X/Twitter page domains', () => {
  assert.equal(shouldRecordTabUrl('https://x.com/home', ['x.com', 'twitter.com']), true);
  assert.equal(shouldRecordTabUrl('https://mobile.twitter.com/home', ['x.com', 'twitter.com']), true);
  assert.equal(shouldRecordTabUrl('https://github.com/example/repo', ['x.com', 'twitter.com']), false);
  assert.equal(shouldRecordTabUrl('chrome://extensions', ['x.com', 'twitter.com']), false);
});

test('CDP recorder recognizes X video segment and HLS manifest responses', () => {
  const segment = cdpMediaCandidate({
    url: 'https://video.twimg.com/amplify_video/1/vid/avc1/0/3000/1920x1080/seg.m4s',
    mimeType: 'video/mp4',
    status: 200
  }, 'Media');
  assert.equal(segment.media_type, 'video');
  assert.equal(segment.role, 'cdp-segment');
  assert.equal(segment.mime_type, 'video/mp4');
  assert.equal(segment.is_manifest, false);

  const manifest = cdpMediaCandidate({
    url: 'https://video.twimg.com/amplify_video/1/pl/avc1/640x360/playlist.m3u8',
    mimeType: 'application/vnd.apple.mpegurl',
    status: 200
  }, 'XHR');
  assert.equal(manifest.role, 'cdp-manifest');
  assert.equal(manifest.is_manifest, true);

  assert.equal(cdpMediaCandidate({ url: 'https://pbs.twimg.com/media/example.jpg', mimeType: 'image/jpeg' }, 'Image'), null);
  assert.equal(cdpMediaCandidate({ url: 'https://evil.example/video.m4s', mimeType: 'video/mp4' }, 'Media'), null);
});

test('CDP recorder builds stable artifact metadata without cookies or headers', () => {
  const context = { document_id: 'doc1', snapshot_id: 'snap1', visit_id: 'visit1', page_url: 'https://x.com/home' };
  const candidate = cdpMediaCandidate({
    url: 'https://video.twimg.com/amplify_video/1/vid/avc1/0/3000/1920x1080/seg.m4s',
    mimeType: 'video/mp4',
    status: 206,
    encodedDataLength: 1234
  }, 'Media');
  const payload = cdpMediaArtifactPayload(context, candidate);
  assert.equal(payload.artifact_id, cdpArtifactId('snap1', candidate.source_url));
  assert.equal(payload.document_id, 'doc1');
  assert.equal(payload.snapshot_id, 'snap1');
  assert.equal(payload.source_url, candidate.source_url);
  assert.equal(payload.capture_status, 'referenced');
  assert.equal(payload.metadata.cdp_recorder, true);
  assert.equal(payload.metadata.cdp_response_status, 206);
  assert.equal(Object.prototype.hasOwnProperty.call(payload.metadata, 'cookie'), false);
});

test('CDP base64 byte estimate handles padding', () => {
  assert.equal(approxBase64Bytes(Buffer.from('abc').toString('base64')), 3);
  assert.equal(approxBase64Bytes(Buffer.from('abcd').toString('base64')), 4);
});
