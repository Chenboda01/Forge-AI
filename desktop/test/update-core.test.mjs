import assert from 'node:assert/strict';
import test from 'node:test';

import {
  MAX_DOWNLOAD_BYTES,
  compareVersions,
  isAllowedDownloadUrl,
  parseVersion,
  resolveUpdateState,
  safeFilename,
  selectLinuxAsset,
} from '../src/update-core.mjs';

const asset = (name, extra = {}) => ({
  id: 1,
  name,
  size: 123,
  browser_download_url: `https://github.com/Chenboda01/Forge-AI/releases/download/desktop-v1.2.0/${name}`,
  ...extra,
});

const signedAssets = (name = 'Forge-AI-Desktop-1.2.0-x86_64.AppImage') => [
  asset(name),
  asset('SHA256SUMS', { id: 20 }),
  asset('SHA256SUMS.sig', { id: 21 }),
];

const release = (version, options = {}) => ({
  tag_name: `desktop-v${version}`,
  name: `Forge AI Desktop ${version}`,
  body: 'Release notes',
  html_url: `https://github.com/Chenboda01/Forge-AI/releases/tag/desktop-v${version}`,
  assets: signedAssets(),
  ...options,
});

test('parseVersion accepts desktop tags and plain versions', () => {
  assert.deepEqual(parseVersion('desktop-v1.2.3'), [1, 2, 3]);
  assert.deepEqual(parseVersion('v0.0.1'), [0, 0, 1]);
  assert.deepEqual(parseVersion('1.10.0'), [1, 10, 0]);
  assert.deepEqual(parseVersion('Desktop-V2.0.0'), [2, 0, 0]);
});

test('parseVersion rejects unsupported tags', () => {
  assert.equal(parseVersion('desktop-v1.2'), null);
  assert.equal(parseVersion('desktop-v1.2.3-rc1'), null);
  assert.equal(parseVersion('nightly'), null);
  assert.equal(parseVersion(undefined), null);
});

test('compareVersions orders numeric segments', () => {
  assert.equal(compareVersions('1.0.0', '1.0.0'), 0);
  assert.equal(compareVersions('1.0.1', '1.0.0'), 1);
  assert.equal(compareVersions('0.9.9', '1.0.0'), -1);
  assert.equal(compareVersions('1.10.0', '1.9.0'), 1);
  assert.equal(compareVersions('desktop-v1.2.0', '1.2.0'), 0);
  assert.equal(compareVersions('invalid', '1.0.0'), null);
});

test('isAllowedDownloadUrl accepts GitHub release assets case-insensitively', () => {
  assert.equal(
    isAllowedDownloadUrl(
      'https://github.com/Chenboda01/Forge-AI/releases/download/desktop-v1.0.0/app.AppImage',
    ),
    true,
  );
  assert.equal(
    isAllowedDownloadUrl(
      'https://github.com/chenboda01/forge-ai/releases/download/desktop-v1.0.0/app.AppImage',
    ),
    true,
  );
});

test('isAllowedDownloadUrl rejects unrelated and insecure URLs', () => {
  assert.equal(
    isAllowedDownloadUrl(
      'http://github.com/Chenboda01/Forge-AI/releases/download/v1/app.AppImage',
    ),
    false,
  );
  assert.equal(
    isAllowedDownloadUrl(
      'https://evil.example/Chenboda01/Forge-AI/releases/download/v1/app.AppImage',
    ),
    false,
  );
  assert.equal(
    isAllowedDownloadUrl(
      'https://github.com/Chenboda01/Forge-AI/releases/tag/v1',
    ),
    false,
  );
  assert.equal(
    isAllowedDownloadUrl(
      'https://github.com/Chenboda01/Forge-AI/releases/download/../../../etc/passwd',
    ),
    false,
  );
  assert.equal(
    isAllowedDownloadUrl(
      'https://github.com/Chenboda01/Forge-AI/releases/downloader/v1/app',
    ),
    false,
  );
  assert.equal(isAllowedDownloadUrl(null), false);
});

test('safeFilename strips path traversal and unsafe characters', () => {
  assert.equal(safeFilename('../../etc/passwd'), 'passwd');
  assert.equal(safeFilename('..\\..\\x.AppImage'), 'x.AppImage');
  assert.equal(safeFilename('app 1.0.AppImage'), 'app_1.0.AppImage');
  assert.equal(safeFilename(undefined), '');
});

test('selectLinuxAsset picks the matching architecture', () => {
  const assets = [
    asset('Forge-AI-Desktop-1.2.0-aarch64.AppImage'),
    asset('Forge-AI-Desktop-1.2.0-x86_64.AppImage'),
    asset('Forge-AI-Desktop-1.2.0-x86_64.deb'),
  ];

  assert.equal(
    selectLinuxAsset(assets, 'linux', 'x64').name,
    'Forge-AI-Desktop-1.2.0-x86_64.AppImage',
  );
  assert.equal(
    selectLinuxAsset(assets, 'linux', 'arm64').name,
    'Forge-AI-Desktop-1.2.0-aarch64.AppImage',
  );
  assert.equal(selectLinuxAsset(assets, 'darwin', 'x64'), null);
  assert.equal(selectLinuxAsset([], 'linux', 'x64'), null);
});

test('resolveUpdateState reports no release', () => {
  assert.deepEqual(resolveUpdateState(null, '1.0.0'), {
    status: 'no-release',
    currentVersion: '1.0.0',
    releasesUrl: 'https://github.com/Chenboda01/Forge-AI/releases',
    message: 'No stable release published yet.',
  });
});

test('resolveUpdateState reports up to date for equal or older releases', () => {
  const equal = resolveUpdateState(release('1.0.0'), '1.0.0');

  assert.equal(equal.status, 'up-to-date');
  assert.equal(equal.latestVersion, 'desktop-v1.0.0');
  assert.equal(equal.message, "No update found, you're up to date");

  const older = resolveUpdateState(release('0.9.0'), '1.0.0');

  assert.equal(older.status, 'up-to-date');
  assert.equal(older.latestVersion, 'desktop-v0.9.0');
});

test('resolveUpdateState reports an available update with asset metadata', () => {
  const state = resolveUpdateState(
    release('1.2.0', {
      body: 'x'.repeat(4000),
      assets: [
        asset('Forge-AI-Desktop-1.2.0-x86_64.AppImage', { id: 9 }),
        asset('SHA256SUMS', { id: 20 }),
        asset('SHA256SUMS.sig', { id: 21 }),
      ],
    }),
    '1.0.0',
  );

  assert.equal(state.status, 'update-available');
  assert.equal(state.latestVersion, 'desktop-v1.2.0');
  assert.equal(state.releaseName, 'Forge AI Desktop 1.2.0');
  assert.equal(state.releaseNotes.length, 3000);
  assert.equal(
    state.releasesUrl,
    'https://github.com/Chenboda01/Forge-AI/releases/tag/desktop-v1.2.0',
  );
  assert.equal(state.asset.id, 9);
  assert.equal(state.asset.name, 'Forge-AI-Desktop-1.2.0-x86_64.AppImage');
  assert.equal(state.assetError, null);
  assert.equal(state.asset.manifest.name, 'SHA256SUMS');
  assert.equal(state.asset.signature.name, 'SHA256SUMS.sig');
  assert.equal(
    state.asset.url,
    'https://github.com/Chenboda01/Forge-AI/releases/download/desktop-v1.2.0/Forge-AI-Desktop-1.2.0-x86_64.AppImage',
  );
});

test('resolveUpdateState refuses to download unsigned releases', () => {
  const state = resolveUpdateState(
    release('1.2.0', {
      assets: [asset('Forge-AI-Desktop-1.2.0-x86_64.AppImage')],
    }),
    '1.0.0',
  );

  assert.equal(state.status, 'update-available');
  assert.equal(state.asset, null);
  assert.equal(state.assetError, 'missing-signature');
});

test('resolveUpdateState requires both manifest and signature', () => {
  const state = resolveUpdateState(
    release('1.2.0', {
      assets: [
        asset('Forge-AI-Desktop-1.2.0-x86_64.AppImage'),
        asset('SHA256SUMS'),
      ],
    }),
    '1.0.0',
  );

  assert.equal(state.asset, null);
  assert.equal(state.assetError, 'missing-signature');
});

test('resolveUpdateState allows an update with no Linux asset', () => {
  const state = resolveUpdateState(
    release('1.2.0', { assets: [asset('Forge-AI-Desktop-1.2.0-x86_64.deb')] }),
    '1.0.0',
  );

  assert.equal(state.status, 'update-available');
  assert.equal(state.asset, null);
  assert.equal(state.assetError, 'no-compatible-asset');
});

test('resolveUpdateState rejects uncomparable versions', () => {
  assert.throws(
    () => resolveUpdateState({ tag_name: 'nightly' }, '1.0.0'),
    /Cannot compare installed and GitHub versions/,
  );
});

test('MAX_DOWNLOAD_BYTES is a bounded limit', () => {
  assert.equal(Number.isInteger(MAX_DOWNLOAD_BYTES), true);
  assert.ok(MAX_DOWNLOAD_BYTES > 0);
  assert.ok(MAX_DOWNLOAD_BYTES <= 1024 * 1024 * 1024);
});
