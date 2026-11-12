import assert from 'node:assert/strict';
import { readFileSync, statSync } from 'node:fs';
import test from 'node:test';

import { appIconDir, appImageIconSet, linuxIconSet } from '../build/icons.mjs';

const SIZES = [16, 24, 32, 48, 64, 128, 256, 512];

const pngHeader = (file) => {
  const buf = readFileSync(file);
  assert.equal(buf.toString('ascii', 1, 4), 'PNG');

  return {
    width: buf.readUInt32BE(16),
    height: buf.readUInt32BE(20),
    // PNG IHDR color type 6 is RGBA, so the icon keeps its transparency.
    colorType: buf.readUInt8(25),
  };
};

test('hicolor icon set covers every size plus a scalable SVG', () => {
  for (const size of SIZES) {
    const file = linuxIconSet[`${size}x${size}`];
    assert.ok(file, `missing ${size}x${size} entry`);
    assert.ok(statSync(file).isFile(), `${file} is not a file`);
    assert.deepEqual(pngHeader(file), {
      width: size,
      height: size,
      colorType: 6,
    });
  }

  assert.match(linuxIconSet.scalable, /icon\.svg$/);
  assert.ok(statSync(linuxIconSet.scalable).isFile());
});

test('AppImage icon set defaults to the 512px PNG', () => {
  assert.equal(appImageIconSet.default, '512x512');
  assert.equal(appImageIconSet['512x512'], linuxIconSet['512x512']);
  assert.equal(appImageIconSet.scalable, linuxIconSet.scalable);
});

test('scalable SVG wraps the 512px artwork as a data URI', () => {
  const svg = readFileSync(linuxIconSet.scalable, 'utf8');
  assert.match(svg, /width="512"/);
  assert.match(svg, /height="512"/);
  assert.match(svg, /href="data:image\/png;base64,/);
});

test('forge config consumes the application icon sets', () => {
  const config = readFileSync(
    new URL('../forge.config.mjs', import.meta.url),
    'utf8',
  );

  assert.match(config, /icon: linuxIconSet/);
  assert.match(config, /icon: appImageIconSet/);
  assert.doesNotMatch(config, /const iconPath/);
});

test('legacy blue/purple assets remain in place', () => {
  assert.ok(statSync(new URL('../assets/icon.png', import.meta.url)).isFile());
  assert.ok(statSync(new URL('../assets/icon.svg', import.meta.url)).isFile());
});

test('application icons live under assets/app-icon', () => {
  assert.match(appIconDir, /assets[\\/]app-icon$/);
});
