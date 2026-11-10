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

const iconPath = path.resolve(import.meta.dirname, 'assets', 'icon.png');
const projectUrl = 'https://github.com/Chenboda01/Forge-AI';
// Pin the AppImage type-2 runtime instead of downloading it during the build.
// The build must not depend on network availability or an unpinned upstream
// artifact.
const appImageRuntime = path.resolve(
  import.meta.dirname,
  'vendor',
  'appimage-runtime-x86_64',
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
    // launch it from process.resourcesPath.
    extraResource: fs.existsSync(
      path.resolve(import.meta.dirname, 'resources', 'forge'),
    )
      ? [path.resolve(import.meta.dirname, 'resources', 'forge')]
      : [],
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
        icon: iconPath,
        categories: ['Development', 'Utility'],
        homepage: projectUrl,
      },
    }),
    new MakerDeb({
      options: {
        icon: iconPath,
        categories: ['Development', 'Utility'],
        maintainer: 'Boda Chen <chenboda01@users.noreply.github.com>',
        homepage: projectUrl,
      },
    }),
    new MakerAppImage({
      options: {
        icon: iconPath,
        categories: ['Development', 'Utility'],
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
