import { app } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import { randomBytes } from 'node:crypto';

import {
  APP_IMAGE_DIRNAME,
  PIN_INSTRUCTIONS,
  SYSTEM_DESKTOP_PATH,
  resolveShortcutPlan,
  taskbarStatus,
  userIconPath,
  validateDesktopEntry,
} from './taskbar-core.mjs';
import { installAppImageFile } from './taskbar-install.mjs';

const ICON_SIZES = [512, 256, 128, 64, 48, 32, 24, 16];

function currentPlan() {
  return resolveShortcutPlan({
    platform: process.platform,
    isPackaged: app.isPackaged,
    home: app.getPath('home'),
    appImage: process.env.APPIMAGE,
    resourcesPath: process.resourcesPath,
    execPath: process.execPath,
    systemEntryExists: fs.existsSync(SYSTEM_DESKTOP_PATH),
  });
}

function exists(target) {
  try {
    return fs.existsSync(target);
  } catch {
    return false;
  }
}

function assertInsideUserData(target) {
  const base = path.join(app.getPath('home'), '.local', 'share');
  const resolved = path.resolve(target);

  if (resolved !== base && !resolved.startsWith(`${base}${path.sep}`)) {
    throw new Error('Refusing to write outside the user data directory');
  }
}

function writeFileAtomic(target, contents, mode = 0o644) {
  assertInsideUserData(target);

  const directory = path.dirname(target);

  fs.mkdirSync(directory, { recursive: true, mode: 0o755 });

  const temporary = path.join(
    directory,
    `.${path.basename(target)}.${randomBytes(6).toString('hex')}.tmp`,
  );

  try {
    fs.writeFileSync(temporary, contents, { encoding: 'utf8', mode });

    fs.chmodSync(temporary, mode);
    fs.renameSync(temporary, target);
  } catch (error) {
    try {
      fs.rmSync(temporary, { force: true });
    } catch {
      // The temporary file is best-effort cleanup; the original error matters.
    }

    throw error;
  }
}

export function getTaskbarStatus() {
  const plan = currentPlan();
  const entryExists = exists(plan.entryPath);
  const entryText = entryExists ? readText(plan.entryPath) : null;

  return taskbarStatus({
    plan,
    entryExists,
    entryMatches: entryText === plan.desktopEntry,
    appImageInstalled:
      plan.kind === 'appimage' ? exists(plan.appImageTarget) : false,
    systemEntryExists: exists(SYSTEM_DESKTOP_PATH),
  });
}

function readText(target) {
  try {
    return fs.readFileSync(target, 'utf8');
  } catch {
    return null;
  }
}

function installAppImage(plan) {
  if (
    plan.kind !== 'appimage' ||
    !plan.appImageSource ||
    !plan.appImageTarget
  ) {
    return { copied: false, path: '' };
  }

  return installAppImageFile({
    source: plan.appImageSource,
    target: plan.appImageTarget,
    applicationsDir: path.join(app.getPath('home'), APP_IMAGE_DIRNAME),
  });
}

function installIcons(plan) {
  if (!plan.iconSourceDir) {
    return [];
  }

  const installed = [];

  for (const size of ICON_SIZES) {
    const source = path.join(plan.iconSourceDir, `icon-${size}.png`);

    if (!exists(source)) {
      continue;
    }

    const destination = userIconPath(app.getPath('home'), size);

    writeFileAtomic(destination, fs.readFileSync(source), 0o644);
    installed.push(destination);
  }

  return installed;
}

export function installTaskbarShortcut() {
  const plan = currentPlan();

  if (!plan.supported) {
    throw new Error(plan.reason);
  }

  if (plan.kind === 'system') {
    return {
      created: false,
      updated: false,
      installed: true,
      pinned: false,
      path: SYSTEM_DESKTOP_PATH,
      icons: [],
      copied: false,
      appImagePath: '',
      message: `Forge AI Desktop is already registered in the system application menu. ${PIN_INSTRUCTIONS}`,
    };
  }

  const validation = validateDesktopEntry(plan.desktopEntry);

  if (!validation.ok) {
    throw new Error(
      `Refusing to install an invalid desktop entry: ${validation.errors.join(
        '; ',
      )}`,
    );
  }

  const appImage =
    plan.kind === 'appimage'
      ? installAppImage(plan)
      : { copied: false, path: '' };

  const existed = exists(plan.entryPath);
  const previous = existed ? fs.readFileSync(plan.entryPath, 'utf8') : null;
  const updated = previous !== plan.desktopEntry;

  if (updated) {
    writeFileAtomic(plan.entryPath, plan.desktopEntry);
  }

  const icons = installIcons(plan);
  const action = !existed ? 'installed' : updated ? 'updated' : 'unchanged';

  return {
    created: !existed,
    updated,
    installed: true,
    pinned: false,
    path: plan.entryPath,
    icons,
    copied: appImage.copied,
    appImagePath: appImage.path,
    message:
      plan.kind === 'appimage'
        ? `${appImage.copied ? 'AppImage copied to' : 'Launcher already uses'} ` +
          `${appImage.path}. Shortcut ${action} at ${plan.entryPath}. ` +
          `${PIN_INSTRUCTIONS}`
        : `Shortcut ${action} at ${plan.entryPath}. ${PIN_INSTRUCTIONS}`,
  };
}
