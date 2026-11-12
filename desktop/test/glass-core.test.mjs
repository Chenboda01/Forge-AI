import assert from 'node:assert/strict';
import test from 'node:test';

import {
  GLASS_RAINBOW_STOPS,
  SPLASH_LOADER_LABEL,
  glassPerformanceTier,
  isSoftwareRenderer,
  pointerPercent,
  splashLoaderState,
} from '../src/glass-core.mjs';

function hue(hex) {
  const value = Number.parseInt(hex.slice(1), 16);
  const red = ((value >> 16) & 0xff) / 255;
  const green = ((value >> 8) & 0xff) / 255;
  const blue = (value & 0xff) / 255;
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const delta = max - min;
  let result = 0;

  if (delta === 0) return 0;
  if (max === red) result = ((green - blue) / delta) % 6;
  else if (max === green) result = (blue - red) / delta + 2;
  else result = (red - green) / delta + 4;

  return (result * 60 + 360) % 360;
}

test('rainbow stops run red to blue in the electric order', () => {
  assert.deepEqual(GLASS_RAINBOW_STOPS, [
    '#ff3b30',
    '#ff9500',
    '#ffd60a',
    '#34c759',
    '#32d6ff',
    '#0a84ff',
  ]);
});

test('rainbow stops exclude purple, pink, and violet hues', () => {
  for (const stop of GLASS_RAINBOW_STOPS) {
    assert.match(stop, /^#[0-9a-f]{6}$/);

    const value = hue(stop);
    const purpleBand = value >= 250 && value <= 340;

    assert.equal(purpleBand, false, `${stop} sits in the purple band`);
  }
});

test('splash loader label is explicit', () => {
  assert.equal(SPLASH_LOADER_LABEL, 'Starting Forge AI');
});

test('low-core machines use the flat glass tier', () => {
  assert.equal(glassPerformanceTier({ hardwareConcurrency: 2 }), 'low');
  assert.equal(glassPerformanceTier({ hardwareConcurrency: 4 }), 'low');
  assert.equal(
    glassPerformanceTier({
      hardwareConcurrency: 8,
      renderer: 'ANGLE (AMD Radeon 400 Series)',
    }),
    'high',
  );
  assert.equal(glassPerformanceTier({ hardwareConcurrency: 0 }), 'low');
  assert.equal(
    glassPerformanceTier({ hardwareConcurrency: Number.NaN }),
    'low',
  );
  assert.equal(glassPerformanceTier({}), 'low');
  assert.equal(
    glassPerformanceTier({ hardwareConcurrency: 12, renderer: '' }),
    'low',
  );
});

test('loader completes only when the terminal is ready', () => {
  assert.equal(splashLoaderState({ terminalReady: true }), 'ready');
  assert.equal(splashLoaderState({ terminalReady: false }), 'loading');
  assert.equal(splashLoaderState({}), 'loading');
});

test('software rendering forces the flat glass tier', () => {
  assert.equal(isSoftwareRenderer('SwiftShader Device (Subzero)'), true);
  assert.equal(isSoftwareRenderer('llvmpipe (LLVM 17.0.6, 256 bits)'), true);
  assert.equal(isSoftwareRenderer('ANGLE (AMD Radeon 400 Series)'), false);
  assert.equal(isSoftwareRenderer(''), false);
  assert.equal(isSoftwareRenderer(undefined), false);
  assert.equal(
    glassPerformanceTier({
      hardwareConcurrency: 12,
      renderer: 'llvmpipe (LLVM 17.0.6, 256 bits)',
    }),
    'low',
  );
  assert.equal(
    glassPerformanceTier({
      hardwareConcurrency: 12,
      renderer: 'ANGLE (AMD Radeon 400 Series)',
    }),
    'high',
  );
});

test('pointer positions clamp to the surface', () => {
  const rect = { left: 100, top: 50, width: 200, height: 100 };

  assert.deepEqual(pointerPercent({ clientX: 200, clientY: 100, rect }), {
    x: 50,
    y: 50,
  });
  assert.deepEqual(pointerPercent({ clientX: -500, clientY: 9999, rect }), {
    x: 0,
    y: 100,
  });
  assert.deepEqual(pointerPercent({ clientX: 1, clientY: 1 }), {
    x: 50,
    y: 50,
  });
  assert.deepEqual(pointerPercent({ clientX: Number.NaN, clientY: 1, rect }), {
    x: 50,
    y: 50,
  });
});
