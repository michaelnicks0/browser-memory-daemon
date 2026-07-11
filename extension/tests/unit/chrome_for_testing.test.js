const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const modulePath = path.resolve(__dirname, '../../../scripts/chrome-for-testing.mjs');
const releaseLock = require('../../../scripts/chrome-for-testing-lock.json');

function sha256(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function fixtureLock(executable) {
  return {
    schema_version: 1,
    version: '150.0.7871.115',
    platform: 'win64',
    url: 'https://storage.googleapis.com/chrome-for-testing-public/150.0.7871.115/win64/chrome-win64.zip',
    archive_size: 1,
    archive_sha256: sha256(Buffer.from('x')),
    executable_size: executable.length,
    executable_sha256: sha256(executable)
  };
}

test('release Chrome for Testing lock is pinned and checksum-complete', async () => {
  const { validateChromeForTestingLock } = await import(modulePath);
  assert.equal(validateChromeForTestingLock(releaseLock), releaseLock);
  assert.equal(releaseLock.version, '150.0.7871.115');
  assert.match(releaseLock.archive_sha256, /^[0-9a-f]{64}$/);
  assert.match(releaseLock.executable_sha256, /^[0-9a-f]{64}$/);
});

test('cached pinned Chrome is verified without network or download permission', async () => {
  const { ensurePinnedChromeForTesting } = await import(modulePath);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'bmd-chrome-lock-'));
  const executable = Buffer.from('verified chrome fixture');
  const lock = fixtureLock(executable);
  const executablePath = path.join(root, lock.version, 'chrome-win64', 'chrome.exe');
  fs.mkdirSync(path.dirname(executablePath), { recursive: true });
  fs.writeFileSync(executablePath, executable, { mode: 0o755 });

  try {
    const selected = await ensurePinnedChromeForTesting({ lock, cacheRoot: root, allowDownload: false });
    assert.equal(selected, executablePath);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('missing or corrupt pinned Chrome fails closed when download is not explicitly allowed', async () => {
  const { ensurePinnedChromeForTesting } = await import(modulePath);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'bmd-chrome-lock-'));
  const expected = Buffer.from('expected chrome fixture');
  const lock = fixtureLock(expected);
  const executablePath = path.join(root, lock.version, 'chrome-win64', 'chrome.exe');

  try {
    await assert.rejects(
      ensurePinnedChromeForTesting({ lock, cacheRoot: root, allowDownload: false }),
      /is not cached/
    );
    fs.mkdirSync(path.dirname(executablePath), { recursive: true });
    fs.writeFileSync(executablePath, Buffer.from('corrupt'), { mode: 0o755 });
    await assert.rejects(
      ensurePinnedChromeForTesting({ lock, cacheRoot: root, allowDownload: false }),
      /size mismatch|SHA-256 mismatch/
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
