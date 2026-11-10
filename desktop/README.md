# Forge AI Desktop

Electron shell that runs the Forge AI coding agent (`forge chat`) inside a
native desktop window backed by `node-pty` and `xterm.js`.

The desktop app does not replace the CLI. It bundles a self-contained copy of
the Python engine so end users do not need Python, pip, Node.js, or Electron
installed.

## Requirements (build)

- Node.js 22+ and npm
- `uv` and the Forge Python project (the repository root by default)
- Linux packaging tools: `mksquashfs` (squashfs-tools), `dpkg-deb`, `rpmbuild`

## Build

```bash
# 1. Build the bundled Python engine into resources/forge/
./scripts/build-forge-payload.sh

# 2. Package and create installers
npm ci
npm run make
```

Artifacts are written to `out/make/` (AppImage, .deb, .rpm). The packaged
application itself is produced by `npm run package` in `out/`.

## Development

```bash
npm start
```

In development the app launches the locally installed `forge` CLI
(`~/.local/bin/forge`). In packaged builds it launches the bundled engine from
`process.resourcesPath/forge/forge`.

Environment overrides:

- `FORGE_BIN` — path to a Forge executable
- `FORGE_WORKSPACE` — directory the agent should treat as the workspace
  (defaults to the user's home directory in packaged builds)

## Linux notes

- AppImage requires FUSE. On distributions that do not ship `libfuse2`
  (for example Ubuntu 24.04), run the AppImage with `--appimage-extract-and-run`
  or install the compatibility package.
- The `.deb` targets Debian/Ubuntu; the `.rpm` targets Fedora-family systems.
- Credentials are stored through the OS keyring (`forge auth login`). The
  bundled engine never ships API keys, configuration, or session data.

## Versioning and updates

The displayed version is read from `package.json` at runtime, so the header
always matches the packaged build. Releases are tagged `desktop-v<version>`;
the first stable public release targets `1.0.0` and is gated on packaging,
security review, and clean-install testing.

"Check for updates" asks the GitHub Releases API for the newest stable
`desktop-v*` release and, when a newer version exists, exposes a button that
opens its release page in the default browser. The check is manual, read-only,
and never downloads or installs anything automatically.

## Tests

```bash
npm test
npm run lint
```

### Design Attribution

Forge AI Desktop features an original glass-inspired interface built using HTML, CSS, and JavaScript.

The visual design uses standard web technologies, including backdrop filters, gradients, translucency, and animated highlights.

Forge AI Desktop is an independent open-source project and is not affiliated with, endorsed by, or sponsored by Apple Inc.

"Apple" and "Liquid Glass" are trademarks or designations associated with Apple Inc. All respective trademarks belong to their owners.

**License:** MIT License.

Copyright © 2026 Boda Chen.

### 💎 Forge Crystal UI

Forge AI Desktop features **Forge Crystal UI**, a glass-inspired interface with translucent panels, dynamic reflections, and animated progress indicators.

The interface is independently implemented using standard web technologies.

Forge AI Desktop is not affiliated with or endorsed by Apple Inc.

**License:** MIT — see [DESIGN-LICENSE.md](DESIGN-LICENSE.md).
