import { MakerSquirrel } from '@electron-forge/maker-squirrel';
import { MakerZIP } from '@electron-forge/maker-zip';
import { MakerDeb } from '@electron-forge/maker-deb';
import { MakerRpm } from '@electron-forge/maker-rpm';
import { MakerAppImage } from '@reforged/maker-appimage';
import { AutoUnpackNativesPlugin } from '@electron-forge/plugin-auto-unpack-natives';
import { VitePlugin } from '@electron-forge/plugin-vite';
import { FusesPlugin } from '@electron-forge/plugin-fuses';
import { FuseV1Options, FuseVersion } from '@electron/fuses';
import fs from 'node:fs';
import path from 'node:path';

import { appImageIconSet, linuxIconSet } from './build/icons.mjs';

const projectUrl = 'https://github.com/Chenboda01/Forge-AI';
// Pin the AppImage type-2 runtime instead of downloading it during the build.
// The build must not depend on network availability or an unpinned upstream
// artifact.
const appImageRuntime = path.resolve(
  import.meta.dirname,
  'vendor',
  'appimage-runtime-x86_64',
);
// Shared FreeDesktop entry for the deb/rpm makers. The upstream defaults set
// StartupWMClass to productName ("Forge AI Desktop"), but Electron derives the
// X11 WM_CLASS from the sanitized executable name. Using `name` keeps the
// launcher entry grouped with its window.
const desktopTemplate = path.resolve(
  import.meta.dirname,
  'build',
  'desktop.ejs',
);
// The AppImage maker generates a minimal desktop entry (raw binary name, no
// StartupWMClass). Supply the same entry the deb/rpm makers render so the
// AppImage launcher groups with its window.
const appImageDesktop = path.resolve(
  import.meta.dirname,
  'build',
  'forge-ai-desktop.desktop',
);

// node-pty ships sources and prebuilt binaries for every platform. Only the
// Linux N-API binary plus the JS wrapper are needed at runtime, so drop the
// rest after Electron Forge has rebuilt native dependencies and before the
// asar archive is created.
const pruneNodePty = async ({ buildPath }) => {
  const nodePty = path.join(buildPath, 'node_modules', 'node-pty');

  for (const entry of [
    'prebuilds',
    'deps',
    'third_party',
    'src',
    'scripts',
    'binding.gyp',
  ]) {
    fs.rmSync(path.join(nodePty, entry), {
      recursive: true,
      force: true,
    });
  }

  fs.rmSync(path.join(nodePty, 'build', 'Release', 'obj.target'), {
    recursive: true,
    force: true,
  });

  fs.rmSync(path.join(buildPath, 'node_modules', 'node-addon-api'), {
    recursive: true,
    force: true,
  });
};

const config = {
  packagerConfig: {
    name: 'forge-ai-desktop',
    asar: true,
    // Ship the self-contained Forge CLI payload (built by
    // scripts/build-forge-payload.sh) next to app.asar so the main process can
    // launch it from process.resourcesPath. The application icon set is
    // packaged so the taskbar shortcut can install launcher icons for
    // unpackaged trees and AppImages.
    extraResource: [
      path.resolve(import.meta.dirname, 'resources', 'forge'),
      path.resolve(import.meta.dirname, 'assets', 'app-icon'),
    ].filter((resource) => fs.existsSync(resource)),
    // The Vite plugin normally copies only the `.vite` output, which drops
    // every runtime dependency. Keep the Vite bundle plus the native module
    // tree that must exist at runtime (node-pty) and the header-only build
    // dependency Electron's rebuild step needs (node-addon-api).
    ignore: (file) => {
      if (!file) {
        return false;
      }

      return !(
        file === '/package.json' ||
        file.startsWith('/.vite') ||
        file === '/node_modules' ||
        file.startsWith('/node_modules/node-pty') ||
        file.startsWith('/node_modules/node-addon-api')
      );
    },
    afterCopy: [pruneNodePty],
  },
  rebuildConfig: {},
  makers: [
    new MakerSquirrel({}),
    new MakerZIP({}, ['darwin']),
    new MakerRpm({
      options: {
        desktopTemplate,
        icon: linuxIconSet,
        categories: ['Development'],
        homepage: projectUrl,
      },
    }),
    new MakerDeb({
      options: {
        desktopTemplate,
        icon: linuxIconSet,
        categories: ['Development'],
        maintainer: 'Boda Chen <chenboda01@users.noreply.github.com>',
        homepage: projectUrl,
      },
    }),
    new MakerAppImage({
      options: {
        icon: appImageIconSet,
        desktopFile: appImageDesktop,
        desktopName: 'forge-ai-desktop.desktop',
        runtime: appImageRuntime,
      },
    }),
  ],
  plugins: [
    new VitePlugin({
      // `build` can specify multiple entry builds, which can be Main process, Preload scripts, Worker process, etc.
      // If you are familiar with Vite configuration, it will look really familiar.
      build: [
        {
          // `entry` is just an alias for `build.lib.entry` in the corresponding file of `config`.
          entry: 'src/main.js',
          config: 'vite.main.config.mjs',
          target: 'main',
        },
        {
          entry: 'src/preload.js',
          config: 'vite.preload.config.mjs',
          target: 'preload',
        },
      ],
      renderer: [
        {
          name: 'main_window',
          config: 'vite.renderer.config.mjs',
        },
      ],
    }),
    // Unpack native `.node` binaries from the asar archive so they can be
    // loaded at runtime.
    new AutoUnpackNativesPlugin({}),
    // Fuses are used to enable/disable various Electron functionality
    // at package time, before code signing the application
    new FusesPlugin({
      version: FuseVersion.V1,
      [FuseV1Options.RunAsNode]: false,
      [FuseV1Options.EnableCookieEncryption]: true,
      [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,
      [FuseV1Options.EnableNodeCliInspectArguments]: false,
      [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: true,
      [FuseV1Options.OnlyLoadAppFromAsar]: true,
    }),
  ],
};

export default config;
