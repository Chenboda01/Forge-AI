#!/usr/bin/env node
// Generates SHA256SUMS and its detached Ed25519 signature for release files.
//
// Usage:
//   FORGE_RELEASE_KEY=~/.config/forge-release/dev-ed25519.pem \
//     node scripts/sign-release.mjs --out dist/signed out/make/**/*.AppImage
//
// The private key must live outside the repository with mode 600. This script
// never prints key material and refuses group/world-readable keys.

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

import {
  MANIFEST_ASSET_NAME,
  SIGNATURE_ASSET_NAME,
} from '../src/update-core.mjs';

function fail(message) {
  console.error(`sign-release: ${message}`);
  process.exit(1);
}

function parseArguments(argv) {
  const files = [];
  let keyPath = process.env.FORGE_RELEASE_KEY ?? null;
  let outDir = process.cwd();

  for (let index = 0; index < argv.length; index++) {
    const argument = argv[index];

    if (argument === '--key') {
      keyPath = argv[++index] ?? null;
    } else if (argument === '--out') {
      outDir = argv[++index] ?? null;
    } else if (argument === '--help' || argument === '-h') {
      console.log(
        'usage: sign-release.mjs --key <private-key.pem> [--out <dir>] <files...>',
      );
      process.exit(0);
    } else if (argument.startsWith('--')) {
      fail(`unknown option: ${argument}`);
    } else {
      files.push(argument);
    }
  }

  if (!keyPath) {
    fail('missing private key (--key or FORGE_RELEASE_KEY)');
  }

  if (!outDir) {
    fail('missing output directory');
  }

  if (files.length === 0) {
    fail('no release files to sign');
  }

  return { keyPath, outDir, files };
}

function loadPrivateKey(keyPath) {
  let stats;

  try {
    stats = fs.statSync(keyPath);
  } catch {
    fail('private key file is not readable');
  }

  if (!stats.isFile()) {
    fail('private key path must be a regular file');
  }

  if ((stats.mode & 0o077) !== 0) {
    fail('private key permissions are too open; run chmod 600 on the key');
  }

  let key;

  try {
    key = crypto.createPrivateKey(fs.readFileSync(keyPath));
  } catch {
    fail('private key is not a valid PEM key');
  }

  if (key.asymmetricKeyType !== 'ed25519') {
    fail('private key must be Ed25519');
  }

  return key;
}

function hashFile(filePath) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha256');
    const stream = fs.createReadStream(filePath);

    stream.on('error', reject);
    stream.on('data', (chunk) => hash.update(chunk));
    stream.on('end', () => resolve(hash.digest('hex')));
  });
}

function writeAtomic(destination, contents) {
  const temporary = `${destination}.${process.pid}.tmp`;

  fs.writeFileSync(temporary, contents, { mode: 0o644 });
  fs.renameSync(temporary, destination);
}

async function main() {
  const { keyPath, outDir, files } = parseArguments(process.argv.slice(2));
  const privateKey = loadPrivateKey(keyPath);
  const entries = [];

  for (const file of files) {
    const absolute = path.resolve(file);
    const name = path.basename(absolute);

    if (name === MANIFEST_ASSET_NAME || name === SIGNATURE_ASSET_NAME) {
      fail(`refusing to sign metadata file: ${name}`);
    }

    let stats;

    try {
      stats = fs.statSync(absolute);
    } catch {
      fail(`release file is not readable: ${name}`);
    }

    if (!stats.isFile()) {
      fail(`release path is not a regular file: ${name}`);
    }

    entries.push({ name, digest: await hashFile(absolute) });
  }

  entries.sort((left, right) => left.name.localeCompare(right.name));

  const manifest = entries
    .map((entry) => `${entry.digest}  ${entry.name}\n`)
    .join('');
  const signature = crypto
    .sign(null, Buffer.from(manifest, 'utf8'), privateKey)
    .toString('base64');

  fs.mkdirSync(outDir, { recursive: true });

  writeAtomic(path.join(outDir, MANIFEST_ASSET_NAME), manifest);
  writeAtomic(path.join(outDir, SIGNATURE_ASSET_NAME), `${signature}\n`);

  for (const entry of entries) {
    console.log(`${entry.digest}  ${entry.name}`);
  }

  console.log(`wrote ${MANIFEST_ASSET_NAME} and ${SIGNATURE_ASSET_NAME}`);
}

main().catch((error) => fail(error.message));
