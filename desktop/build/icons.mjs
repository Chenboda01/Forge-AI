import path from 'node:path';

const appIconDir = path.resolve(
  import.meta.dirname,
  '..',
  'assets',
  'app-icon',
);

const png = (size) => path.join(appIconDir, `icon-${size}.png`);

// hicolor size map consumed by electron-installer-debian and
// electron-installer-redhat. `scalable` must point at an SVG.
export const linuxIconSet = {
  '16x16': png(16),
  '24x24': png(24),
  '32x32': png(32),
  '48x48': png(48),
  '64x64': png(64),
  '128x128': png(128),
  '256x256': png(256),
  '512x512': png(512),
  scalable: path.join(appIconDir, 'icon.svg'),
};

// AppImage IconSet: reuse the hicolor map but keep the 512px PNG as the
// AppImage `.DirIcon` instead of the SVG.
export const appImageIconSet = {
  ...linuxIconSet,
  default: '512x512',
};

export { appIconDir };
