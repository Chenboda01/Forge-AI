import path from 'node:path';

export const APP_ID = 'forge-ai-desktop';
export const DESKTOP_FILE = `${APP_ID}.desktop`;
export const SYSTEM_APPLICATIONS_DIR = '/usr/share/applications';
export const SYSTEM_DESKTOP_PATH = `${SYSTEM_APPLICATIONS_DIR}/${DESKTOP_FILE}`;
export const APP_IMAGE_DIRNAME = 'Applications';
export const APP_IMAGE_FILENAME = `${APP_ID}.AppImage`;

export const PIN_INSTRUCTIONS =
  'KDE controls taskbar pinning. Open the application launcher, ' +
  'right-click Forge AI Desktop, and choose Pin to Taskbar. ' +
  'Forge does not modify panel configuration.';

function hasControlChars(text) {
  for (const character of text) {
    const code = character.codePointAt(0);

    if (code < 0x20 || code === 0x7f) {
      return true;
    }
  }

  return false;
}

const REQUIRED_KEYS = [
  'Type',
  'Name',
  'Exec',
  'Icon',
  'StartupWMClass',
  'Categories',
];

export function quoteExecArg(value) {
  const text = String(value ?? '');

  if (!text) {
    throw new Error('Exec path is empty');
  }

  if (hasControlChars(text)) {
    throw new Error('Exec path contains control characters');
  }

  const escaped = text.replaceAll(/([\\"`$])/g, '\\$1');

  return `"${escaped}"`;
}

export function buildDesktopEntry({ exec, icon = APP_ID } = {}) {
  const command = String(exec ?? '');

  if (!command.trim()) {
    throw new Error('Exec is required');
  }

  if (hasControlChars(command)) {
    throw new Error('Exec contains control characters');
  }

  const iconName = String(icon ?? '').trim();

  if (!iconName) {
    throw new Error('Icon is required');
  }

  if (hasControlChars(iconName)) {
    throw new Error('Icon contains control characters');
  }

  return [
    '[Desktop Entry]',
    'Type=Application',
    'Name=Forge AI Desktop',
    'GenericName=Forge AI Desktop',
    'Comment=Desktop shell for the Forge AI coding agent.',
    `Exec=${command}`,
    `Icon=${iconName}`,
    'Terminal=false',
    'StartupNotify=true',
    `StartupWMClass=${APP_ID}`,
    'Categories=Development;',
    '',
  ].join('\n');
}

export function validateDesktopEntry(text, { expectedWmClass = APP_ID } = {}) {
  const source = String(text ?? '');
  const lines = source.split('\n');
  const errors = [];

  if (lines[0] !== '[Desktop Entry]') {
    errors.push('Entry must start with [Desktop Entry]');
  }

  if (hasControlChars(source.replaceAll('\n', ''))) {
    errors.push('Entry contains control characters');
  }

  const entries = new Map();

  for (const line of lines) {
    if (!line || line.startsWith('#') || line.startsWith('[')) {
      continue;
    }

    const separator = line.indexOf('=');

    if (separator <= 0) {
      errors.push(`Malformed line: ${line}`);

      continue;
    }

    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1);

    if (entries.has(key)) {
      errors.push(`Duplicate key: ${key}`);
    }

    entries.set(key, value);
  }

  for (const key of REQUIRED_KEYS) {
    if (!entries.get(key)?.trim()) {
      errors.push(`Missing ${key}`);
    }
  }

  if (entries.has('Type') && entries.get('Type') !== 'Application') {
    errors.push('Type must be Application');
  }

  if (
    entries.has('StartupWMClass') &&
    entries.get('StartupWMClass') !== expectedWmClass
  ) {
    errors.push(`StartupWMClass must be ${expectedWmClass}`);
  }

  if (
    entries.has('Categories') &&
    !entries.get('Categories').trim().endsWith(';')
  ) {
    errors.push('Categories must end with a semicolon');
  }

  return { ok: errors.length === 0, errors };
}

export function buildAppImageExec(appImagePath) {
  return `${quoteExecArg(appImagePath)} %U`;
}

export function buildPortableExec(execPath) {
  return `${quoteExecArg(execPath)} %U`;
}

export function userApplicationsDir(home) {
  return path.join(home, '.local', 'share', 'applications');
}

export function userDesktopEntryPath(home) {
  return path.join(userApplicationsDir(home), DESKTOP_FILE);
}

export function userAppImageDir(home) {
  return path.join(home, APP_IMAGE_DIRNAME);
}

export function userAppImagePath(home) {
  return path.join(userAppImageDir(home), APP_IMAGE_FILENAME);
}

export function userIconPath(home, size) {
  return path.join(
    home,
    '.local',
    'share',
    'icons',
    'hicolor',
    `${size}x${size}`,
    'apps',
    `${APP_ID}.png`,
  );
}

export function resolveShortcutPlan({
  platform,
  isPackaged,
  home,
  appImage,
  resourcesPath,
  execPath,
  systemEntryExists = false,
}) {
  const base = {
    supported: false,
    reason: '',
    kind: 'none',
    entryPath: userDesktopEntryPath(home),
    systemEntryPath: SYSTEM_DESKTOP_PATH,
    desktopEntry: '',
    iconSourceDir: '',
    appImageSource: '',
    appImageTarget: '',
    needsAppImageInstall: false,
  };

  if (platform !== 'linux') {
    return {
      ...base,
      reason: 'Taskbar shortcuts are only available on Linux.',
    };
  }

  if (!isPackaged) {
    return {
      ...base,
      reason: 'Run the packaged application to add a launcher shortcut.',
    };
  }

  const iconSourceDir = resourcesPath
    ? path.join(resourcesPath, 'app-icon')
    : '';

  if (appImage) {
    const appImagePath = String(appImage);

    if (!path.isAbsolute(appImagePath)) {
      return { ...base, reason: 'The AppImage path is not absolute.' };
    }

    const appImageSource = path.resolve(appImagePath);
    const appImageTarget = userAppImagePath(home);

    return {
      ...base,
      supported: true,
      kind: 'appimage',
      appImageSource,
      appImageTarget,
      needsAppImageInstall: appImageSource !== appImageTarget,
      desktopEntry: buildDesktopEntry({
        exec: buildAppImageExec(appImageTarget),
      }),
      iconSourceDir,
    };
  }

  if (systemEntryExists) {
    return {
      ...base,
      supported: true,
      kind: 'system',
      iconSourceDir,
    };
  }

  // A packaged tree that is not installed by a package manager (for example
  // an extracted electron-forge `package` output) needs its own entry.
  return {
    ...base,
    supported: true,
    kind: 'portable',
    desktopEntry: buildDesktopEntry({
      exec: buildPortableExec(execPath),
    }),
    iconSourceDir,
  };
}

export function taskbarStatus({
  plan,
  entryExists,
  entryMatches = true,
  appImageInstalled = false,
  systemEntryExists,
}) {
  if (!plan?.supported) {
    return {
      supported: false,
      installed: false,
      pinned: false,
      kind: 'none',
      entryPath: plan?.entryPath ?? '',
      systemEntryPath: plan?.systemEntryPath ?? '',
      appImagePath: '',
      appImageInstalled: false,
      needsAppImageInstall: false,
      entryStale: false,
      message: plan?.reason ?? 'Taskbar shortcuts are unavailable.',
    };
  }

  const entryStale = Boolean(entryExists && !entryMatches);
  const installed =
    plan.kind === 'system'
      ? Boolean(systemEntryExists)
      : plan.kind === 'appimage'
        ? Boolean(entryExists && entryMatches && appImageInstalled)
        : Boolean(entryExists);

  return {
    supported: true,
    installed,
    pinned: false,
    kind: plan.kind,
    entryPath: plan.entryPath,
    systemEntryPath: plan.systemEntryPath,
    appImagePath: plan.kind === 'appimage' ? plan.appImageTarget : '',
    appImageInstalled:
      plan.kind === 'appimage' ? Boolean(appImageInstalled) : false,
    needsAppImageInstall: Boolean(plan.needsAppImageInstall),
    entryStale,
    message: statusMessage(plan, {
      installed,
      entryExists: Boolean(entryExists),
      entryStale,
      appImageInstalled: Boolean(appImageInstalled),
    }),
  };
}

function statusMessage(
  plan,
  { installed, entryExists, entryStale, appImageInstalled },
) {
  if (plan.kind === 'appimage') {
    return appImageMessage(plan, {
      installed,
      entryExists,
      entryStale,
      appImageInstalled,
    });
  }

  return installed ? installedMessage(plan) : readyMessage(plan);
}

function appImageMessage(
  plan,
  { installed, entryExists, entryStale, appImageInstalled },
) {
  if (installed) {
    const refresh = plan.needsAppImageInstall
      ? ' Install again to refresh the stable copy from this build.'
      : '';

    return (
      `Shortcut installed at ${plan.entryPath}. It launches ` +
      `${plan.appImageTarget}.${refresh} ${PIN_INSTRUCTIONS}`
    );
  }

  if (entryStale) {
    return (
      `The shortcut points at an older AppImage. Install to repair it and ` +
      `copy this build to ${plan.appImageTarget}. ${PIN_INSTRUCTIONS}`
    );
  }

  if (entryExists && !appImageInstalled) {
    return (
      `The shortcut target is missing (${plan.appImageTarget}). Install to ` +
      `restore it. ${PIN_INSTRUCTIONS}`
    );
  }

  return (
    `Add Forge AI Desktop to your application launcher. This copies the ` +
    `running AppImage to ${plan.appImageTarget}. ${PIN_INSTRUCTIONS}`
  );
}

function installedMessage(plan) {
  if (plan.kind === 'system') {
    return (
      `Forge AI Desktop is registered in the system application menu ` +
      `(${SYSTEM_DESKTOP_PATH}). ${PIN_INSTRUCTIONS}`
    );
  }

  return `Shortcut installed at ${plan.entryPath}. ${PIN_INSTRUCTIONS}`;
}

function readyMessage(plan) {
  if (plan.kind === 'system') {
    return (
      `Forge AI Desktop is registered in the system application menu ` +
      `(${SYSTEM_DESKTOP_PATH}). ${PIN_INSTRUCTIONS}`
    );
  }

  return `Add Forge AI Desktop to your application launcher. ${PIN_INSTRUCTIONS}`;
}
