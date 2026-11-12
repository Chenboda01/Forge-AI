import { app, shell } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import https from 'node:https';
import crypto from 'node:crypto';

import {
  API,
  MAX_DOWNLOAD_BYTES,
  MAX_MANIFEST_BYTES,
  MAX_SIGNATURE_BYTES,
  RELEASES_URL,
  isAllowedDownloadUrl,
  resolveUpdateState,
  safeFilename,
  verifyChecksumManifest,
  verifyDownloadDigest,
} from './update-core.mjs';
import { RELEASE_KEY_FINGERPRINT_SHA256 } from './release-key.mjs';

function requestJson(url) {
  return new Promise((resolve, reject) => {
    const request = https.get(
      url,
      {
        headers: {
          'User-Agent': 'Forge-AI-Desktop',
          Accept: 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
        },
        timeout: 15000,
      },
      (response) => {
        let body = '';

        response.setEncoding('utf8');

        response.on('data', (chunk) => {
          body += chunk;

          if (body.length > 2_000_000) {
            response.destroy(new Error('GitHub response too large'));
          }
        });

        response.on('end', () => {
          if (response.statusCode === 404) {
            resolve(null);
            return;
          }

          if (response.statusCode !== 200) {
            reject(new Error(`GitHub returned HTTP ${response.statusCode}`));
            return;
          }

          try {
            resolve(JSON.parse(body));
          } catch {
            reject(new Error('Invalid GitHub response'));
          }
        });
      },
    );

    request.on('timeout', () => {
      request.destroy(new Error('GitHub request timed out'));
    });

    request.on('error', reject);
  });
}

export function getInstalledVersion() {
  return app.getVersion();
}

// Downloads small release metadata (manifest or signature) into memory. Kept
// separate from downloadFile so a hostile server cannot stream an unbounded
// response while Forge is only trying to read a signature.
function fetchAssetBuffer(url, maxBytes, redirects = 0) {
  if (redirects > 5) {
    return Promise.reject(new Error('Too many redirects'));
  }

  return new Promise((resolve, reject) => {
    const parsed = new URL(url);

    if (parsed.protocol !== 'https:') {
      reject(new Error('Only HTTPS downloads are allowed'));
      return;
    }

    const request = https.get(
      parsed,
      {
        headers: {
          'User-Agent': 'Forge-AI-Desktop',
          Accept: 'application/octet-stream',
        },
        timeout: 15000,
      },
      (response) => {
        if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
          const location = response.headers.location;
          response.resume();

          if (!location) {
            reject(new Error('Missing redirect URL'));
            return;
          }

          const next = new URL(location, parsed).toString();

          fetchAssetBuffer(next, maxBytes, redirects + 1).then(resolve, reject);

          return;
        }

        if (response.statusCode !== 200) {
          response.resume();
          reject(new Error(`Download failed: HTTP ${response.statusCode}`));
          return;
        }

        const total = Number(response.headers['content-length'] || 0);

        if (total > maxBytes) {
          response.resume();
          reject(new Error('Release metadata is too large'));
          return;
        }

        const chunks = [];
        let received = 0;

        response.on('data', (chunk) => {
          received += chunk.length;

          if (received > maxBytes) {
            response.destroy(new Error('Release metadata is too large'));
            return;
          }

          chunks.push(chunk);
        });

        response.on('error', reject);
        response.on('end', () => resolve(Buffer.concat(chunks)));
      },
    );

    request.on('timeout', () => {
      request.destroy(new Error('Request timed out'));
    });

    request.on('error', reject);
  });
}

export async function checkForUpdates(onProgress) {
  const report = (percent, message) => {
    onProgress?.({
      percent,
      message,
    });
  };

  report(0, 'Connecting to GitHub...');

  const currentVersion = getInstalledVersion();

  report(20, 'Reading installed version...');

  const release = await requestJson(`${API}/releases/latest`);

  report(65, 'Comparing release versions...');

  const state = resolveUpdateState(release, currentVersion);

  report(100, 'Check completed');

  return state;
}

function downloadFile(url, destination, onProgress, redirects = 0) {
  if (redirects > 5) {
    return Promise.reject(new Error('Too many download redirects'));
  }

  return new Promise((resolve, reject) => {
    const parsed = new URL(url);

    if (parsed.protocol !== 'https:') {
      reject(new Error('Only HTTPS downloads are allowed'));
      return;
    }

    const request = https.get(
      parsed,
      {
        headers: {
          'User-Agent': 'Forge-AI-Desktop',
          Accept: 'application/octet-stream',
        },
        timeout: 30000,
      },
      (response) => {
        if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
          const location = response.headers.location;
          response.resume();

          if (!location) {
            reject(new Error('Missing redirect URL'));
            return;
          }

          const next = new URL(location, parsed).toString();

          downloadFile(next, destination, onProgress, redirects + 1).then(
            resolve,
            reject,
          );

          return;
        }

        if (response.statusCode !== 200) {
          response.resume();
          reject(new Error(`Download failed: HTTP ${response.statusCode}`));
          return;
        }

        const total = Number(response.headers['content-length'] || 0);

        if (total > MAX_DOWNLOAD_BYTES) {
          response.resume();
          reject(new Error('Download is too large'));
          return;
        }

        let received = 0;
        const hash = crypto.createHash('sha256');
        const output = fs.createWriteStream(destination);

        response.on('data', (chunk) => {
          received += chunk.length;
          hash.update(chunk);

          if (received > MAX_DOWNLOAD_BYTES) {
            response.destroy(new Error('Download is too large'));
            return;
          }

          if (total > 0) {
            const percent = Math.min(100, Math.floor((received / total) * 100));

            onProgress?.({
              percent,
              received,
              total,
            });
          } else {
            onProgress?.({
              percent: null,
              received,
              total: null,
            });
          }
        });

        response.on('error', (error) => {
          output.destroy(error);
        });

        output.on('error', reject);

        output.on('finish', () => {
          if (total > 0 && received !== total) {
            reject(new Error('Incomplete download'));
            return;
          }

          resolve({
            received,
            sha256: hash.digest('hex'),
          });
        });

        response.pipe(output);
      },
    );

    request.on('timeout', () => {
      request.destroy(new Error('Download timed out'));
    });

    request.on('error', reject);
  });
}

export async function downloadUpdate(asset, onProgress) {
  if (!asset?.url || !asset?.name) {
    throw new Error('No compatible update download available');
  }

  if (!isAllowedDownloadUrl(asset.url)) {
    throw new Error('Unexpected release download URL');
  }

  const manifestAsset = asset.manifest;
  const signatureAsset = asset.signature;

  if (!manifestAsset?.url || !signatureAsset?.url) {
    throw new Error('Release is not signed; refusing to download');
  }

  if (
    !isAllowedDownloadUrl(manifestAsset.url) ||
    !isAllowedDownloadUrl(signatureAsset.url)
  ) {
    throw new Error('Unexpected release metadata URL');
  }

  const manifestBuffer = await fetchAssetBuffer(
    manifestAsset.url,
    MAX_MANIFEST_BYTES,
  );
  const signatureBuffer = await fetchAssetBuffer(
    signatureAsset.url,
    MAX_SIGNATURE_BYTES,
  );

  const manifest = verifyChecksumManifest({
    manifestText: manifestBuffer.toString('utf8'),
    signature: signatureBuffer.toString('utf8'),
  });

  const filename = safeFilename(asset.name);

  if (!filename) {
    throw new Error('Release asset name is invalid');
  }

  const expected = manifest.get(filename);

  if (!expected) {
    throw new Error('Signed manifest does not list this release asset');
  }

  if (asset.digest && asset.digest.startsWith('sha256:')) {
    if (!verifyDownloadDigest(asset.digest.slice(7), expected)) {
      throw new Error('Release metadata does not match the signed manifest');
    }
  }

  const downloads = path.join(os.homedir(), 'Downloads');

  fs.mkdirSync(downloads, { recursive: true });

  const destination = path.join(downloads, filename);

  const temporary = path.join(
    downloads,
    `.${filename}.${crypto.randomBytes(8).toString('hex')}.part`,
  );

  try {
    const result = await downloadFile(asset.url, temporary, onProgress);

    if (!verifyDownloadDigest(result.sha256, expected)) {
      throw new Error('SHA-256 verification failed');
    }

    if (asset.size > 0 && result.received !== asset.size) {
      throw new Error('Downloaded size does not match the release metadata');
    }

    fs.renameSync(temporary, destination);

    return {
      path: destination,
      bytes: result.received,
      sha256: result.sha256,
      keyFingerprint: RELEASE_KEY_FINGERPRINT_SHA256,
    };
  } catch (error) {
    try {
      fs.rmSync(temporary, { force: true });
    } catch {
      // Ignore cleanup errors.
    }

    throw error;
  }
}

export function openReleasePage() {
  return shell.openExternal(RELEASES_URL);
}

export function openDownloadsFolder() {
  return shell.openPath(path.join(os.homedir(), 'Downloads'));
}
