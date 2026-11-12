import assert from 'node:assert/strict';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { installAppImageFile } from '../src/taskbar-install.mjs';
import {
  resolveShortcutPlan,
  validateDesktopEntry,
} from '../src/taskbar-core.mjs';

function sandbox(t) {
  const root = mkdtempSync(path.join(os.tmpdir(), 'forge-taskbar-'));
  const home = path.join(root, 'home');
  const applicationsDir = path.join(home, 'Applications');
  const target = path.join(applicationsDir, 'forge-ai-desktop.AppImage');

  t.after(() => rmSync(root, { recursive: true, force: true }));

  return { root, home, applicationsDir, target };
}

const mode = (file) => statSync(file).mode & 0o777;

test('missing source AppImages fail without touching an existing target', (t) => {
  const { root, applicationsDir, target } = sandbox(t);

  mkdirSync(applicationsDir, { recursive: true });
  writeFileSync(target, 'working-build');

  assert.throws(
    () =>
      installAppImageFile({
        source: path.join(root, 'missing.AppImage'),
        target,
        applicationsDir,
      }),
    /missing/,
  );

  assert.equal(readFileSync(target, 'utf8'), 'working-build');
});

test('a moved AppImage is copied to the stable target atomically', (t) => {
  const { root, applicationsDir, target } = sandbox(t);
  const source = path.join(
    root,
    'Forge-Artifacts',
    'forge-ai-desktop-1.1.0.AppImage',
  );

  mkdirSync(path.dirname(source), { recursive: true });
  writeFileSync(source, 'build-1.1.0');

  const result = installAppImageFile({ source, target, applicationsDir });

  assert.deepEqual(result, { copied: true, path: target });
  assert.equal(readFileSync(target, 'utf8'), 'build-1.1.0');
  assert.equal(mode(target), 0o755);
  assert.deepEqual(readdirSync(applicationsDir), ['forge-ai-desktop.AppImage']);
});

test('a replaced AppImage overwrites the stable copy', (t) => {
  const { root, applicationsDir, target } = sandbox(t);
  const source = path.join(root, 'forge-ai-desktop-1.1.0.AppImage');

  mkdirSync(applicationsDir, { recursive: true });
  writeFileSync(target, 'build-1.0.0');
  writeFileSync(source, 'build-1.1.0');

  const result = installAppImageFile({ source, target, applicationsDir });

  assert.equal(result.copied, true);
  assert.equal(readFileSync(target, 'utf8'), 'build-1.1.0');
  assert.deepEqual(readdirSync(applicationsDir), ['forge-ai-desktop.AppImage']);
});

test('an AppImage already at the stable path is not copied again', (t) => {
  const { applicationsDir, target } = sandbox(t);

  mkdirSync(applicationsDir, { recursive: true });
  writeFileSync(target, 'same-build', { mode: 0o644 });

  const result = installAppImageFile({
    source: target,
    target,
    applicationsDir,
  });

  assert.equal(result.copied, false);
  assert.equal(mode(target), 0o755);
});

test('targets outside ~/Applications are refused', (t) => {
  const { root, applicationsDir } = sandbox(t);
  const source = path.join(root, 'source.AppImage');

  writeFileSync(source, 'build');

  assert.throws(
    () =>
      installAppImageFile({
        source,
        target: path.join(root, 'evil.AppImage'),
        applicationsDir,
      }),
    /outside/,
  );
  assert.throws(
    () =>
      installAppImageFile({
        source,
        target: path.join(applicationsDir, 'nested', 'evil.AppImage'),
        applicationsDir,
      }),
    /outside/,
  );
  assert.equal(existsSync(path.join(root, 'evil.AppImage')), false);
});

test('planning, copying, and writing the entry work end to end', (t) => {
  const { root, home, applicationsDir, target } = sandbox(t);
  const source = path.join(
    root,
    'Forge-Artifacts',
    'forge-ai-desktop-1.1.0.AppImage',
  );

  mkdirSync(path.dirname(source), { recursive: true });
  writeFileSync(source, 'build-1.1.0');

  const plan = resolveShortcutPlan({
    platform: 'linux',
    isPackaged: true,
    home,
    appImage: source,
    resourcesPath: '',
    execPath: '',
    systemEntryExists: false,
  });

  assert.equal(plan.appImageTarget, target);

  const result = installAppImageFile({
    source: plan.appImageSource,
    target: plan.appImageTarget,
    applicationsDir,
  });

  assert.equal(result.path, target);
  assert.equal(readFileSync(target, 'utf8'), 'build-1.1.0');
  assert.equal(validateDesktopEntry(plan.desktopEntry).ok, true);
  assert.match(plan.desktopEntry, new RegExp(`^Exec="${target}" %U$`, 'm'));
});
