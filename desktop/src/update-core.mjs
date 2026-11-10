// Pure update helpers with no Electron dependency. Kept separate so the
// release-state and allowlist logic can be tested with `node --test`.

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
    asset: asset
      ? {
          id: asset.id,
          name: asset.name,
          size: asset.size,
          url: asset.browser_download_url,
          digest: asset.digest || null,
        }
      : null,
    message: 'Update available',
  };
}
