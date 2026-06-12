(function () {
const DEFAULT_CDP_RECORDER_DOMAINS = ['x.com', 'twitter.com', 'mobile.twitter.com'];
const DEFAULT_CDP_MEDIA_HOSTS = ['video.twimg.com'];
const CDP_VIDEO_SUFFIXES = ['.mp4', '.m4s', '.ts', '.m3u8', '.webm', '.mov'];
const HLS_MIME_TYPES = new Set(['application/x-mpegurl', 'application/vnd.apple.mpegurl']);

function stableHash(text) {
  let hash = 2166136261;
  for (const char of String(text || '')) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function normalizeDomains(value, fallback = DEFAULT_CDP_RECORDER_DOMAINS) {
  const source = Array.isArray(value) ? value : String(value || '').split(',');
  const domains = source
    .map((item) => String(item || '').trim().toLowerCase().replace(/^\*\./, '').replace(/^\./, ''))
    .filter(Boolean);
  return domains.length ? Array.from(new Set(domains)) : fallback.slice();
}

function hostnameMatches(hostname, domains) {
  const host = String(hostname || '').toLowerCase().replace(/^www\./, '');
  return normalizeDomains(domains).some((domain) => host === domain || host.endsWith(`.${domain}`));
}

function shouldRecordTabUrl(tabUrl, domains = DEFAULT_CDP_RECORDER_DOMAINS) {
  try {
    const url = new URL(tabUrl || '');
    return ['http:', 'https:'].includes(url.protocol) && hostnameMatches(url.hostname, domains);
  } catch (_) {
    return false;
  }
}

function headerValue(headers, name) {
  const target = String(name || '').toLowerCase();
  for (const [key, value] of Object.entries(headers || {})) {
    if (String(key).toLowerCase() === target) return String(value || '');
  }
  return '';
}

function contentTypeMime(headersOrContentType) {
  const raw = typeof headersOrContentType === 'string' ? headersOrContentType : headerValue(headersOrContentType, 'content-type');
  return String(raw || '').split(';', 1)[0].trim().toLowerCase();
}

function inferMimeFromUrl(url, explicit = '') {
  const mime = contentTypeMime(explicit);
  if (mime && mime !== 'application/octet-stream') return mime;
  let path = '';
  try {
    path = new URL(url || '').pathname.toLowerCase();
  } catch (_) {}
  if (path.endsWith('.m3u8')) return 'application/x-mpegURL';
  if (path.endsWith('.m4s') || path.endsWith('.mp4')) return 'video/mp4';
  if (path.endsWith('.ts')) return 'video/mp2t';
  if (path.endsWith('.webm')) return 'video/webm';
  if (path.endsWith('.mov')) return 'video/quicktime';
  return mime;
}

function isHlsManifestUrl(url) {
  try {
    return new URL(url || '').pathname.toLowerCase().endsWith('.m3u8');
  } catch (_) {
    return false;
  }
}

function isHlsManifestMime(mimeType) {
  return HLS_MIME_TYPES.has(contentTypeMime(mimeType));
}

function isVideoLikeUrl(url) {
  try {
    const path = new URL(url || '').pathname.toLowerCase();
    return CDP_VIDEO_SUFFIXES.some((suffix) => path.endsWith(suffix));
  } catch (_) {
    return false;
  }
}

function cdpMediaCandidate(response = {}, resourceType = '', mediaHosts = DEFAULT_CDP_MEDIA_HOSTS) {
  const sourceUrl = String(response.url || '');
  let parsed;
  try {
    parsed = new URL(sourceUrl);
  } catch (_) {
    return null;
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) return null;
  if (!hostnameMatches(parsed.hostname, mediaHosts)) return null;
  const mimeType = inferMimeFromUrl(sourceUrl, response.mimeType || headerValue(response.headers, 'content-type'));
  const isManifest = isHlsManifestUrl(sourceUrl) || isHlsManifestMime(mimeType);
  const videoLike = isVideoLikeUrl(sourceUrl) || mimeType.startsWith('video/') || isManifest;
  if (!videoLike) return null;
  return {
    source_url: sourceUrl,
    media_type: 'video',
    role: isManifest ? 'cdp-manifest' : 'cdp-segment',
    mime_type: mimeType,
    is_manifest: isManifest,
    resource_type: String(resourceType || ''),
    status: Number(response.status || 0) || null,
    encoded_data_length: Number(response.encodedDataLength || 0) || null
  };
}

function cdpArtifactId(snapshotId, sourceUrl) {
  const seed = `${snapshotId || ''}|${sourceUrl || ''}`;
  return `media_cdp_${stableHash(seed)}${stableHash(`cdp|${seed}`)}`;
}

function cdpMediaArtifactPayload(context, candidate, extra = {}) {
  if (!context || !context.document_id || !context.snapshot_id) throw new Error('missing CDP capture context');
  return {
    artifact_id: cdpArtifactId(context.snapshot_id, candidate.source_url),
    document_id: context.document_id,
    snapshot_id: context.snapshot_id,
    visit_id: context.visit_id || '',
    page_url: context.page_url || context.url || '',
    media_type: candidate.media_type || 'video',
    role: candidate.role || 'cdp-segment',
    source_url: candidate.source_url,
    mime_type: candidate.mime_type || '',
    capture_status: extra.capture_status || 'referenced',
    status_reason: extra.status_reason || '',
    metadata: {
      ...(extra.metadata || {}),
      cdp_recorder: true,
      cdp_resource_type: candidate.resource_type || '',
      cdp_response_status: candidate.status || null,
      cdp_encoded_data_length: candidate.encoded_data_length || null,
      cdp_is_manifest: Boolean(candidate.is_manifest)
    }
  };
}

function approxBase64Bytes(body) {
  const text = String(body || '').replace(/\s+/g, '');
  if (!text) return 0;
  const padding = text.endsWith('==') ? 2 : text.endsWith('=') ? 1 : 0;
  return Math.max(0, Math.floor((text.length * 3) / 4) - padding);
}

function bytesFromBase64(body) {
  const clean = String(body || '').replace(/\s+/g, '');
  const binary = atob(clean);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function cdpBodyToBlob(bodyResult, mimeType = '') {
  const body = bodyResult && typeof bodyResult.body === 'string' ? bodyResult.body : '';
  if (bodyResult && bodyResult.base64Encoded) {
    return new Blob([bytesFromBase64(body)], { type: mimeType || 'application/octet-stream' });
  }
  return new Blob([body], { type: mimeType || 'text/plain' });
}

const api = {
  DEFAULT_CDP_RECORDER_DOMAINS,
  DEFAULT_CDP_MEDIA_HOSTS,
  normalizeDomains,
  hostnameMatches,
  shouldRecordTabUrl,
  headerValue,
  contentTypeMime,
  inferMimeFromUrl,
  isHlsManifestUrl,
  isHlsManifestMime,
  isVideoLikeUrl,
  cdpMediaCandidate,
  cdpArtifactId,
  cdpMediaArtifactPayload,
  approxBase64Bytes,
  cdpBodyToBlob
};

globalThis.BrowserMemoryCdpRecorder = api;
if (typeof module !== 'undefined') module.exports = api;
})();
