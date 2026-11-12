// Pure update helpers with no Electron dependency. Kept separate so the
// release-state, signature, and allowlist logic can be tested with
// `node --test`.

import crypto from 'node:crypto';

import { RELEASE_PUBLIC_KEY_PEM } from './release-key.mjs';

export const OWNER = 'Chenboda01';
export const REPO = 'Forge-AI';
export const API = `https://api.github.com/repos/${OWNER}/${REPO}`;
export const RELEASES_URL = `https://github.com/${OWNER}/${REPO}/releases`;

// Release tags are `desktop-v<version>`; accept a plain `v1.2.3` or `1.2.3`
// too so a manually created release still compares correctly.
const VERSION_PATTERN = /^(?:desktop-)?v?(\d+)\.(\d+)\.(\d+)$/i;

const DOWNLOAD_PATH_PREFIX =
  `/${OWNER}/${REPO}/releases/download/`.toLowerCase();

export const MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024;

// Releases must publish a detached Ed25519 signature over a SHA-256 manifest.
// Both files are ordinary GitHub release assets so the existing URL allowlist
// applies to them as well.
export const MANIFEST_ASSET_NAME = 'SHA256SUMS';
export const SIGNATURE_ASSET_NAME = 'SHA256SUMS.sig';
export const MAX_MANIFEST_BYTES = 256 * 1024;
export const MAX_SIGNATURE_BYTES = 8 * 1024;
export const ED25519_SIGNATURE_BYTES = 64;

const SHA256_HEX_PATTERN = /^[a-f0-9]{64}$/;

export function parseVersion(value) {
  const match = String(value ?? '')
    .trim()
    .match(VERSION_PATTERN);

  if (!match) return null;
  return match.slice(1).map(Number);
}

export function compareVersions(a, b) {
  const left = parseVersion(a);
  const right = parseVersion(b);

  if (!left || !right) return null;

  for (let i = 0; i < 3; i++) {
    if (left[i] > right[i]) return 1;
    if (left[i] < right[i]) return -1;
  }

  return 0;
}

export function selectLinuxAsset(
  assets = [],
  platform = process.platform,
  arch = process.arch,
) {
  if (platform !== 'linux' || !Array.isArray(assets)) return null;

  const candidates = assets.filter((asset) => {
    if (!asset || typeof asset.name !== 'string') return false;

    const name = asset.name.toLowerCase();

    if (!name.endsWith('.appimage')) return false;

    if (arch === 'x64') {
      return /x86_64|amd64|x64/i.test(name) || !/arm64|aarch64/i.test(name);
    }

    if (arch === 'arm64') {
      return /arm64|aarch64/i.test(name);
    }

    return false;
  });

  return candidates[0] ?? null;
}

// GitHub owner/repo path segments are case-insensitive, and the API returns
// the canonical `Chenboda01` spelling even when the repository is requested
// with different casing. Compare case-insensitively or every real download is
// rejected.
export function isAllowedDownloadUrl(value) {
  try {
    const url = new URL(String(value));

    return (
      url.protocol === 'https:' &&
      url.hostname.toLowerCase() === 'github.com' &&
      url.pathname.toLowerCase().startsWith(DOWNLOAD_PATH_PREFIX)
    );
  } catch {
    return false;
  }
}

export function safeFilename(name) {
  return String(name ?? '')
    .split(/[\\/]/)
    .pop()
    .replace(/[^a-zA-Z0-9._-]/g, '_');
}

function normalizeDigest(value) {
  const digest = String(value ?? '')
    .trim()
    .toLowerCase();

  return SHA256_HEX_PATTERN.test(digest) ? digest : null;
}

// Parses `<sha256>  <filename>` lines as produced by `sha256sum`. A leading
// `*` (binary marker) is tolerated. Anything unexpected fails closed so a
// malformed manifest can never silently verify only part of a release.
export function parseChecksumManifest(text) {
  const entries = new Map();

  for (const line of String(text ?? '').split(/\r?\n/)) {
    const trimmed = line.trim();

    if (!trimmed) continue;

    const match = trimmed.match(/^([a-fA-F0-9]{64})[ \t]+\*?(.+)$/);

    if (!match) {
      throw new Error('Malformed checksum manifest');
    }

    const digest = normalizeDigest(match[1]);
    const filename = safeFilename(match[2].trim());

    if (!digest || !filename) {
      throw new Error('Malformed checksum manifest');
    }

    if (entries.has(filename)) {
      throw new Error('Duplicate checksum manifest entry');
    }

    entries.set(filename, digest);
  }

  if (entries.size === 0) {
    throw new Error('Checksum manifest is empty');
  }

  return entries;
}

export function decodeManifestSignature(value) {
  const compact = String(value ?? '').replace(/\s+/g, '');

  if (!compact) {
    throw new Error('Missing manifest signature');
  }

  const signature = Buffer.from(compact, 'base64');

  if (signature.length !== ED25519_SIGNATURE_BYTES) {
    throw new Error('Invalid manifest signature');
  }

  // Reject non-canonical base64 that decodes to the same bytes.
  const canonical = signature.toString('base64').replace(/=+$/, '');

  if (canonical !== compact.replace(/=+$/, '')) {
    throw new Error('Invalid manifest signature');
  }

  return signature;
}

export function verifyManifestSignature(
  manifestText,
  signatureValue,
  publicKeyPem = RELEASE_PUBLIC_KEY_PEM,
) {
  const manifest = Buffer.from(String(manifestText ?? ''), 'utf8');

  if (manifest.length === 0) {
    throw new Error('Missing checksum manifest');
  }

  let publicKey;

  try {
    publicKey = crypto.createPublicKey(publicKeyPem);
  } catch {
    throw new Error('Release public key is invalid');
  }

  if (publicKey.asymmetricKeyType !== 'ed25519') {
    throw new Error('Release public key is not Ed25519');
  }

  const signature = decodeManifestSignature(signatureValue);

  let valid = false;

  try {
    valid = crypto.verify(null, manifest, publicKey, signature);
  } catch {
    valid = false;
  }

  if (!valid) {
    throw new Error('Manifest signature verification failed');
  }

  return manifest;
}

export function verifyChecksumManifest({
  manifestText,
  signature,
  publicKeyPem = RELEASE_PUBLIC_KEY_PEM,
}) {
  verifyManifestSignature(manifestText, signature, publicKeyPem);

  return parseChecksumManifest(manifestText);
}

export function verifyDownloadDigest(actual, expected) {
  const left = normalizeDigest(actual);
  const right = normalizeDigest(expected);

  if (!left || !right) return false;

  return crypto.timingSafeEqual(
    Buffer.from(left, 'hex'),
    Buffer.from(right, 'hex'),
  );
}

export function releaseKeyFingerprint(publicKeyPem = RELEASE_PUBLIC_KEY_PEM) {
  const key = crypto.createPublicKey(publicKeyPem);
  const der = key.export({ type: 'spki', format: 'der' });

  return crypto.createHash('sha256').update(der).digest('hex');
}

function findAssetByName(assets, name) {
  if (!Array.isArray(assets)) return null;

  const target = name.toLowerCase();

  return (
    assets.find(
      (asset) =>
        typeof asset?.name === 'string' && asset.name.toLowerCase() === target,
    ) ?? null
  );
}

// A downloadable update requires BOTH the manifest and its detached
// signature. Requiring them here keeps the "download" button from appearing
// for releases Forge would refuse to verify later.
export function selectManifestAssets(assets = []) {
  const manifest = findAssetByName(assets, MANIFEST_ASSET_NAME);
  const signature = findAssetByName(assets, SIGNATURE_ASSET_NAME);

  if (!manifest || !signature) return null;

  return { manifest, signature };
}

function describeAsset(asset) {
  return {
    id: asset.id,
    name: asset.name,
    size: asset.size,
    url: asset.browser_download_url,
  };
}

export function resolveUpdateState(release, currentVersion) {
  if (!release) {
    return {
      status: 'no-release',
      currentVersion,
      releasesUrl: RELEASES_URL,
      message: 'No stable release published yet.',
    };
  }

  const latestVersion = release.tag_name;
  const comparison = compareVersions(latestVersion, currentVersion);

  if (comparison === null) {
    throw new Error('Cannot compare installed and GitHub versions.');
  }

  const asset = selectLinuxAsset(release.assets);
  const signing = selectManifestAssets(release.assets);

  let downloadable = null;
  let assetError = null;

  if (!asset) {
    assetError = 'no-compatible-asset';
  } else if (!signing) {
    assetError = 'missing-signature';
  } else {
    downloadable = {
      ...describeAsset(asset),
      digest: asset.digest || null,
      manifest: describeAsset(signing.manifest),
      signature: describeAsset(signing.signature),
    };
  }

  if (comparison <= 0) {
    return {
      status: 'up-to-date',
      currentVersion,
      latestVersion,
      releasesUrl: RELEASES_URL,
      message: "No update found, you're up to date",
    };
  }

  return {
    status: 'update-available',
    currentVersion,
    latestVersion,
    releaseName: release.name || latestVersion,
    releaseNotes: String(release.body || '').slice(0, 3000),
    releasesUrl: release.html_url || RELEASES_URL,
    asset: downloadable,
    assetError,
    message: 'Update available',
  };
}
