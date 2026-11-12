import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import test from 'node:test';

import {
  parseChecksumManifest,
  releaseKeyFingerprint,
  selectManifestAssets,
  verifyChecksumManifest,
  verifyDownloadDigest,
} from '../src/update-core.mjs';
import {
  RELEASE_KEY_FINGERPRINT_SHA256,
  RELEASE_PUBLIC_KEY_PEM,
} from '../src/release-key.mjs';

const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
const testPublicKeyPem = publicKey.export({ type: 'spki', format: 'pem' });

const sha256 = (value) =>
  crypto.createHash('sha256').update(value).digest('hex');

const sign = (text, key = privateKey) =>
  crypto.sign(null, Buffer.from(text, 'utf8'), key).toString('base64');

const manifestLine = (filename, digest) => `${digest}  ${filename}`;

test('the pinned release key matches the published fingerprint', () => {
  assert.equal(
    releaseKeyFingerprint(RELEASE_PUBLIC_KEY_PEM),
    RELEASE_KEY_FINGERPRINT_SHA256,
  );
});

test('parseChecksumManifest accepts sha256sum output', () => {
  const digest = sha256('forge');
  const entries = parseChecksumManifest(
    [`${digest}  Forge.AppImage`, `${digest} *other.deb`].join('\r\n'),
  );

  assert.equal(entries.get('Forge.AppImage'), digest);
  assert.equal(entries.get('other.deb'), digest);
});

test('parseChecksumManifest rejects malformed input', () => {
  assert.throws(() => parseChecksumManifest(''), /empty/);
  assert.throws(() => parseChecksumManifest('not a manifest'), /Malformed/);
  assert.throws(
    () => parseChecksumManifest(`${sha256('a')}  a\n${sha256('a')}  a`),
    /Duplicate/,
  );
});

test('verifyChecksumManifest accepts a valid signature', () => {
  const text = manifestLine('Forge.AppImage', sha256('binary'));
  const entries = verifyChecksumManifest({
    manifestText: text,
    signature: sign(text),
    publicKeyPem: testPublicKeyPem,
  });

  assert.equal(entries.get('Forge.AppImage'), sha256('binary'));
});

test('verifyChecksumManifest rejects a tampered manifest', () => {
  const original = manifestLine('Forge.AppImage', sha256('binary'));
  const tampered = manifestLine('Forge.AppImage', sha256('evil'));

  assert.throws(
    () =>
      verifyChecksumManifest({
        manifestText: tampered,
        signature: sign(original),
        publicKeyPem: testPublicKeyPem,
      }),
    /signature verification failed/,
  );
});

test('verifyChecksumManifest rejects a signature from another key', () => {
  const text = manifestLine('Forge.AppImage', sha256('binary'));
  const other = crypto.generateKeyPairSync('ed25519');

  assert.throws(
    () =>
      verifyChecksumManifest({
        manifestText: text,
        signature: sign(text, other.privateKey),
        publicKeyPem: testPublicKeyPem,
      }),
    /signature verification failed/,
  );
});

test('verifyChecksumManifest rejects missing or malformed signatures', () => {
  const text = manifestLine('Forge.AppImage', sha256('binary'));

  assert.throws(
    () =>
      verifyChecksumManifest({
        manifestText: text,
        signature: '',
        publicKeyPem: testPublicKeyPem,
      }),
    /Missing manifest signature/,
  );

  assert.throws(
    () =>
      verifyChecksumManifest({
        manifestText: text,
        signature: 'AAAA',
        publicKeyPem: testPublicKeyPem,
      }),
    /Invalid manifest signature/,
  );

  assert.throws(
    () =>
      verifyChecksumManifest({
        manifestText: '',
        signature: sign(text),
        publicKeyPem: testPublicKeyPem,
      }),
    /Missing checksum manifest/,
  );
});

test('verifyDownloadDigest compares complete SHA-256 values', () => {
  const digest = sha256('binary');

  assert.equal(verifyDownloadDigest(digest.toUpperCase(), digest), true);
  assert.equal(verifyDownloadDigest(sha256('other'), digest), false);
  assert.equal(verifyDownloadDigest('abc', digest), false);
  assert.equal(verifyDownloadDigest(undefined, digest), false);
});

test('selectManifestAssets requires both metadata files', () => {
  const manifest = { id: 1, name: 'SHA256SUMS' };
  const signature = { id: 2, name: 'SHA256SUMS.sig' };

  assert.deepEqual(
    selectManifestAssets([
      { id: 9, name: 'Forge.AppImage' },
      manifest,
      signature,
    ]),
    { manifest, signature },
  );

  assert.deepEqual(
    selectManifestAssets([{ id: 3, name: 'sha256sums' }, signature]),
    { manifest: { id: 3, name: 'sha256sums' }, signature },
  );

  assert.equal(selectManifestAssets([manifest]), null);
  assert.equal(selectManifestAssets([signature]), null);
  assert.equal(selectManifestAssets([]), null);
});
