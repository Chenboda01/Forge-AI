import assert from 'node:assert/strict';
import { existsSync, readFileSync, statSync } from 'node:fs';
import test from 'node:test';

import {
  SPLASH_FADE_MS,
  SPLASH_MAX_VISIBLE_MS,
  SPLASH_MIN_VISIBLE_MS,
  SPLASH_TEXT,
  shouldDismissSplash,
} from '../src/splash-core.mjs';

const startupArt = new URL('../src/assets/forge-startup.png', import.meta.url);

test('splash copy is exact', () => {
  assert.equal(SPLASH_TEXT, 'Welcome to Forge Desktop Edition');
});

test('splash timing constants are ordered', () => {
  assert.ok(0 < SPLASH_MIN_VISIBLE_MS);
  assert.ok(SPLASH_MIN_VISIBLE_MS < SPLASH_MAX_VISIBLE_MS);
  assert.ok(0 < SPLASH_FADE_MS);
  assert.ok(SPLASH_FADE_MS < SPLASH_MIN_VISIBLE_MS);
});

test('splash remains visible before minimum time', () => {
  assert.equal(
    shouldDismissSplash({ elapsedMs: 0, terminalReady: false }),
    false,
  );
  assert.equal(
    shouldDismissSplash({
      elapsedMs: SPLASH_MIN_VISIBLE_MS - 1,
      terminalReady: true,
    }),
    false,
  );
});

test('ready terminal dismisses at minimum time', () => {
  assert.equal(
    shouldDismissSplash({
      elapsedMs: SPLASH_MIN_VISIBLE_MS,
      terminalReady: true,
    }),
    true,
  );
});

test('unready terminal remains visible between minimum and maximum time', () => {
  assert.equal(
    shouldDismissSplash({
      elapsedMs: SPLASH_MIN_VISIBLE_MS,
      terminalReady: false,
    }),
    false,
  );
});

test('maximum time dismisses regardless of terminal readiness', () => {
  assert.equal(
    shouldDismissSplash({
      elapsedMs: SPLASH_MAX_VISIBLE_MS,
      terminalReady: false,
    }),
    true,
  );
  assert.equal(
    shouldDismissSplash({
      elapsedMs: SPLASH_MAX_VISIBLE_MS + 1,
      terminalReady: false,
    }),
    true,
  );
});

test('invalid elapsed time fails safe', () => {
  assert.equal(
    shouldDismissSplash({ elapsedMs: Number.NaN, terminalReady: false }),
    true,
  );
  assert.equal(
    shouldDismissSplash({ elapsedMs: -1, terminalReady: false }),
    true,
  );
});

test('startup art is a bounded 640px PNG', () => {
  assert.equal(existsSync(startupArt), true);

  const size = statSync(startupArt).size;
  const image = readFileSync(startupArt);

  assert.ok(size >= 1);
  assert.ok(size <= 1024 * 1024);
  assert.deepEqual(
    [...image.subarray(0, 8)],
    [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
  );
  assert.equal(image.toString('ascii', 12, 16), 'IHDR');
  assert.equal(image.readUInt32BE(16), 640);
  assert.equal(image.readUInt32BE(20), 640);
  assert.equal(image[24], 8);
  assert.equal(image[25], 6);
});
