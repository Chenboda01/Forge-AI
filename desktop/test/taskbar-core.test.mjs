import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  APP_ID,
  PIN_INSTRUCTIONS,
  SYSTEM_DESKTOP_PATH,
  buildAppImageExec,
  buildDesktopEntry,
  buildPortableExec,
  quoteExecArg,
  resolveShortcutPlan,
  taskbarStatus,
  userDesktopEntryPath,
  userAppImagePath,
  userIconPath,
  validateDesktopEntry,
} from '../src/taskbar-core.mjs';

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8');

const home = '/home/tester';

const packaged = {
  platform: 'linux',
  isPackaged: true,
  home,
  resourcesPath: '/opt/forge/resources',
  execPath: '/opt/forge/forge-ai-desktop',
  appImage: undefined,
  systemEntryExists: false,
};

test('quoteExecArg wraps a path and escapes shell-significant characters', () => {
  assert.equal(
    quoteExecArg('/opt/My App/forge "$x" `y` \\z'),
    '"/opt/My App/forge \\"\\$x\\" \\`y\\` \\\\z"',
  );
});

test('quoteExecArg rejects empty paths and control characters', () => {
  assert.throws(() => quoteExecArg(''), /empty/);
  assert.throws(() => quoteExecArg('/tmp/a\nb'), /control characters/);
  assert.throws(() => quoteExecArg('/tmp/a\u0000b'), /control characters/);
});

test('buildDesktopEntry emits every key required for the launcher', () => {
  const entry = buildDesktopEntry({
    exec: buildAppImageExec('/tmp/Forge.AppImage'),
  });

  assert.match(entry, /^\[Desktop Entry\]$/m);
  assert.match(entry, /^Type=Application$/m);
  assert.match(entry, /^Name=Forge AI Desktop$/m);
  assert.match(entry, /^Exec="\/tmp\/Forge\.AppImage" %U$/m);
  assert.match(entry, new RegExp(`^Icon=${APP_ID}$`, 'm'));
  assert.match(entry, new RegExp(`^StartupWMClass=${APP_ID}$`, 'm'));
  assert.match(entry, /^Categories=Development;$/m);
});

test('buildDesktopEntry rejects newline injection in Exec', () => {
  assert.throws(
    () => buildDesktopEntry({ exec: '"/tmp/a"\nExec=evil' }),
    /control characters/,
  );
});

test('validateDesktopEntry accepts the entry the service writes', () => {
  const entry = buildDesktopEntry({
    exec: buildPortableExec(packaged.execPath),
  });

  assert.deepEqual(validateDesktopEntry(entry), { ok: true, errors: [] });
});

test('validateDesktopEntry reports missing keys and wrong identity', () => {
  const entry = buildDesktopEntry({
    exec: buildPortableExec(packaged.execPath),
  });

  assert.equal(
    validateDesktopEntry(entry.replace(/^Exec=.*\n/m, '')).ok,
    false,
  );
  assert.equal(
    validateDesktopEntry(
      entry.replace(
        `StartupWMClass=${APP_ID}`,
        'StartupWMClass=Forge AI Desktop',
      ),
    ).ok,
    false,
  );
  assert.equal(
    validateDesktopEntry(
      entry.replace('Categories=Development;', 'Categories=Development'),
    ).ok,
    false,
  );
});

test('validateDesktopEntry rejects duplicate keys', () => {
  const entry = `${buildDesktopEntry({
    exec: buildPortableExec(packaged.execPath),
  })}Name=Second\n`;

  const { ok, errors } = validateDesktopEntry(entry);

  assert.equal(ok, false);
  assert.ok(errors.some((error) => error.includes('Duplicate key: Name')));
});

test('shortcut plans are unsupported outside packaged Linux builds', () => {
  assert.equal(
    resolveShortcutPlan({ ...packaged, platform: 'darwin' }).supported,
    false,
  );
  assert.equal(
    resolveShortcutPlan({ ...packaged, isPackaged: false }).supported,
    false,
  );
});

test('AppImage plans install to a stable ~/Applications path', () => {
  const source =
    '/home/tester/Forge-Artifacts/v1.1.0/forge-ai-desktop-1.1.0-x64.AppImage';
  const plan = resolveShortcutPlan({ ...packaged, appImage: source });

  assert.equal(plan.supported, true);
  assert.equal(plan.kind, 'appimage');
  assert.equal(plan.appImageSource, source);
  assert.equal(
    plan.appImageTarget,
    '/home/tester/Applications/forge-ai-desktop.AppImage',
  );
  assert.equal(plan.needsAppImageInstall, true);
  assert.ok(plan.desktopEntry.includes(`Exec="${plan.appImageTarget}" %U`));
  assert.doesNotMatch(plan.desktopEntry, /Forge-Artifacts/);
  assert.equal(plan.iconSourceDir, '/opt/forge/resources/app-icon');
  assert.equal(plan.entryPath, userDesktopEntryPath(home));
});

test('AppImage plans skip copying when already installed at the stable path', () => {
  const stable = userAppImagePath(home);
  const plan = resolveShortcutPlan({ ...packaged, appImage: stable });

  assert.equal(plan.needsAppImageInstall, false);
  assert.equal(
    plan.desktopEntry,
    buildDesktopEntry({ exec: buildAppImageExec(stable) }),
  );
});

test('moved AppImages keep one launcher target and need a refresh', () => {
  const first = resolveShortcutPlan({
    ...packaged,
    appImage: '/home/tester/Downloads/forge-ai-desktop-1.1.0-x64.AppImage',
  });
  const moved = resolveShortcutPlan({
    ...packaged,
    appImage:
      '/home/tester/Forge-Artifacts/v1.1.0/forge-ai-desktop-1.1.0-x64.AppImage',
  });

  assert.equal(first.appImageTarget, moved.appImageTarget);
  assert.equal(first.desktopEntry, moved.desktopEntry);
  assert.equal(first.needsAppImageInstall, true);
  assert.equal(moved.needsAppImageInstall, true);

  const status = taskbarStatus({
    plan: moved,
    entryExists: true,
    entryMatches: true,
    appImageInstalled: true,
    systemEntryExists: false,
  });

  assert.equal(status.installed, true);
  assert.equal(status.needsAppImageInstall, true);
  assert.match(status.message, /refresh the stable copy/);
  assert.doesNotMatch(status.message, /not been copied/);
});

test('missing AppImage targets are reported as broken and repairable', () => {
  const plan = resolveShortcutPlan({
    ...packaged,
    appImage: userAppImagePath(home),
  });
  const status = taskbarStatus({
    plan,
    entryExists: true,
    entryMatches: true,
    appImageInstalled: false,
    systemEntryExists: false,
  });

  assert.equal(status.installed, false);
  assert.equal(status.appImagePath, userAppImagePath(home));
  assert.match(status.message, /target is missing/);
});

test('stale launchers pointing at an older build are repaired', () => {
  const plan = resolveShortcutPlan({
    ...packaged,
    appImage: userAppImagePath(home),
  });
  const stale = buildDesktopEntry({
    exec: buildAppImageExec(
      '/home/tester/Forge/Forge-AI-session-recovery/desktop/out/make/' +
        'AppImage/x64/forge-ai-desktop-1.0.0-x64.AppImage',
    ),
  });

  const status = taskbarStatus({
    plan,
    entryExists: true,
    entryMatches: stale === plan.desktopEntry,
    appImageInstalled: true,
    systemEntryExists: false,
  });

  assert.equal(status.entryStale, true);
  assert.equal(status.installed, false);
  assert.match(status.message, /older AppImage/);
});

test('replaced AppImages stay installed at the stable target', () => {
  const plan = resolveShortcutPlan({
    ...packaged,
    appImage: userAppImagePath(home),
  });
  const status = taskbarStatus({
    plan,
    entryExists: true,
    entryMatches: true,
    appImageInstalled: true,
    systemEntryExists: false,
  });

  assert.equal(status.installed, true);
  assert.equal(status.needsAppImageInstall, false);
  assert.match(status.message, /It launches/);
});

test('AppImage plans reject a relative APPIMAGE path', () => {
  const plan = resolveShortcutPlan({
    ...packaged,
    appImage: 'Forge.AppImage',
  });

  assert.equal(plan.supported, false);
  assert.match(plan.reason, /not absolute/);
});

test('installed system entries are reused instead of overwritten', () => {
  const plan = resolveShortcutPlan({
    ...packaged,
    systemEntryExists: true,
  });

  assert.equal(plan.kind, 'system');
  assert.equal(plan.desktopEntry, '');

  const status = taskbarStatus({
    plan,
    entryExists: false,
    systemEntryExists: true,
  });

  assert.equal(status.installed, true);
  assert.equal(status.pinned, false);
  assert.equal(status.systemEntryPath, SYSTEM_DESKTOP_PATH);
});

test('portable plans target the running packaged binary', () => {
  const plan = resolveShortcutPlan(packaged);

  assert.equal(plan.kind, 'portable');
  assert.ok(plan.desktopEntry.includes(`Exec="${packaged.execPath}" %U`));
});

test('status never reports the application as pinned', () => {
  const plan = resolveShortcutPlan(packaged);

  for (const entryExists of [false, true]) {
    const status = taskbarStatus({
      plan,
      entryExists,
      systemEntryExists: false,
    });

    assert.equal(status.pinned, false);
    assert.equal(status.installed, entryExists);
  }

  assert.match(PIN_INSTRUCTIONS, /KDE controls taskbar pinning/);
  assert.match(PIN_INSTRUCTIONS, /Pin to Taskbar/);
  assert.match(PIN_INSTRUCTIONS, /does not modify panel configuration/);
});

test('user icon paths use the hicolor app icon layout', () => {
  assert.equal(
    userIconPath(home, 512),
    '/home/tester/.local/share/icons/hicolor/512x512/apps/forge-ai-desktop.png',
  );
});

test('build config packages the app icon set for shortcut installs', () => {
  const config = read('../forge.config.mjs');

  assert.match(config, /'assets',\s*'app-icon'/);
  assert.match(config, /extraResource:\s*\[/);
});

test('main process exposes guarded taskbar IPC handlers', () => {
  const main = read('../src/main.js');

  assert.match(main, /ipcMain\.handle\('taskbar:status'/);
  assert.match(main, /ipcMain\.handle\('taskbar:install'/);
  assert.match(
    main,
    /import\s*\{\s*getTaskbarStatus,\s*installTaskbarShortcut,?\s*\}\s*from '\.\/taskbar-service\.js'/s,
  );
});
