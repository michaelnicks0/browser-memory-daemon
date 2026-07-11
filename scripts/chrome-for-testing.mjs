import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { access, mkdir, rename, rm, stat } from 'node:fs/promises';
import { constants as fsConstants } from 'node:fs';
import path from 'node:path';

function fail(message) {
  throw new Error(message);
}

export function validateChromeForTestingLock(lock) {
  if (!lock || lock.schema_version !== 1) fail('Chrome for Testing lock schema_version must be 1');
  if (!/^\d+\.\d+\.\d+\.\d+$/.test(lock.version || '')) fail('Chrome for Testing lock has an invalid version');
  if (lock.platform !== 'win64') fail('Chrome for Testing lock platform must be win64');
  const expectedUrl = `https://storage.googleapis.com/chrome-for-testing-public/${lock.version}/win64/chrome-win64.zip`;
  if (lock.url !== expectedUrl) fail(`Chrome for Testing lock URL must be ${expectedUrl}`);
  for (const field of ['archive_size', 'executable_size']) {
    if (!Number.isSafeInteger(lock[field]) || lock[field] <= 0) fail(`Chrome for Testing lock ${field} must be a positive safe integer`);
  }
  for (const field of ['archive_sha256', 'executable_sha256']) {
    if (!/^[0-9a-f]{64}$/.test(lock[field] || '')) fail(`Chrome for Testing lock ${field} must be lowercase SHA-256`);
  }
  return lock;
}

export async function sha256File(filePath) {
  return await new Promise((resolve, reject) => {
    const hash = createHash('sha256');
    const stream = createReadStream(filePath);
    stream.on('error', reject);
    stream.on('data', (chunk) => hash.update(chunk));
    stream.on('end', () => resolve(hash.digest('hex')));
  });
}

async function verifyFile(filePath, expectedSize, expectedSha256, label) {
  let fileStat;
  try {
    fileStat = await stat(filePath);
  } catch (error) {
    fail(`${label} is missing: ${filePath}: ${error.message || error}`);
  }
  if (!fileStat.isFile() || fileStat.size !== expectedSize) {
    fail(`${label} size mismatch at ${filePath}: expected ${expectedSize}, got ${fileStat.size}`);
  }
  const actualSha256 = await sha256File(filePath);
  if (actualSha256 !== expectedSha256) {
    fail(`${label} SHA-256 mismatch at ${filePath}: expected ${expectedSha256}, got ${actualSha256}`);
  }
}

async function isExecutable(filePath) {
  try {
    await access(filePath, fsConstants.X_OK);
    return true;
  } catch (_) {
    return false;
  }
}

export async function ensurePinnedChromeForTesting({ lock: rawLock, cacheRoot, allowDownload = false, logger = () => {} }) {
  const lock = validateChromeForTestingLock(rawLock);
  const versionRoot = path.join(cacheRoot, lock.version);
  const executable = path.join(versionRoot, 'chrome-win64', 'chrome.exe');

  if (await isExecutable(executable)) {
    await verifyFile(executable, lock.executable_size, lock.executable_sha256, `Chrome for Testing ${lock.version} executable`);
    logger(`using verified cached Chrome for Testing ${lock.version}: ${executable}`);
    return executable;
  }
  if (!allowDownload) {
    fail(`pinned Chrome for Testing ${lock.version} is not cached at ${executable}; set BMD_REAL_CHROME_ALLOW_DOWNLOAD=1 for an explicit verified download or set BMD_CHROME_EXE`);
  }

  await mkdir(versionRoot, { recursive: true });
  const archive = path.join(versionRoot, 'chrome-win64.zip');
  const archiveStage = `${archive}.stage-${process.pid}`;
  await rm(archiveStage, { force: true });
  try {
    logger(`downloading pinned Chrome for Testing ${lock.version} win64`);
    let result = spawnSync('curl', ['-L', '--fail', '--retry', '3', '-o', archiveStage, lock.url], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe']
    });
    if (result.status !== 0) fail(`curl Chrome for Testing failed: ${result.stderr || result.stdout}`);
    await verifyFile(archiveStage, lock.archive_size, lock.archive_sha256, `Chrome for Testing ${lock.version} archive`);
    await rename(archiveStage, archive);
    result = spawnSync('unzip', ['-q', '-o', archive, '-d', versionRoot], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe']
    });
    if (result.status !== 0) fail(`unzip Chrome for Testing failed: ${result.stderr || result.stdout}`);
    await verifyFile(executable, lock.executable_size, lock.executable_sha256, `Chrome for Testing ${lock.version} executable`);
  } finally {
    await rm(archiveStage, { force: true });
  }
  logger(`installed verified Chrome for Testing ${lock.version}: ${executable}`);
  return executable;
}
