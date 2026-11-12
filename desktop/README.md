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

### Taskbar shortcut

The header's **Taskbar** button installs a FreeDesktop launcher entry for the
current user at `~/.local/share/applications/forge-ai-desktop.desktop`. For
AppImages and unpackaged trees it also copies the application icon set from
`assets/app-icon/` into `~/.local/share/icons/hicolor/`. Installed `.deb`/`.rpm`
builds already own a system-wide entry, so the button reports that entry
instead of writing a duplicate.

For AppImages, the button also installs the running AppImage at
`~/Applications/forge-ai-desktop.AppImage` and points the launcher at that
stable path. The copy is written to a temporary file, made executable, and
renamed into place, so rebuilding `out/make/` or moving a downloaded AppImage
does not break an existing launcher. Run a newer AppImage and press
**Taskbar** again to replace the stable copy; the launcher and icons are
refreshed in place.

If an existing launcher points at a deleted build (for example an older
`out/make/.../forge-ai-desktop-1.0.0-x64.AppImage`), run the current AppImage
and press **Taskbar** once. Forge copies this build to `~/Applications` and
rewrites the entry. If KDE still launches the cached command, refresh its
service cache or unpin and re-pin:

```bash
kbuildsycoca6   # KF6; kbuildsycoca5 on KF5
```

Desktop-entry writes are confined to `~/.local/share`; the AppImage copy is
confined to `~/Applications`. Both use a temporary file renamed into place and
fail closed on invalid paths or entries. Forge does not edit KDE panel
configuration and does not claim the application is pinned. After installing
the shortcut, open the application launcher, right-click **Forge AI Desktop**,
and choose **Pin to Taskbar** yourself.

### Replacing the application icon

The launcher, window, and package icons all come from `assets/app-icon/`
(`icon-16.png` through `icon-512.png`, plus `icon.svg`). Regenerate every size
from the same source artwork and keep the set in a single directory; `build/icons.mjs`
maps the sizes for the `.deb`, `.rpm`, and AppImage makers, and the same folder
is copied into `resources/app-icon` for the Taskbar button.

KDE caches icons by path, so an already-pinned launcher can keep showing the
old artwork after an update. Refresh the caches and re-pin if needed:

```bash
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor   # if available
kbuildsycoca6                                              # KF6
kbuildsycoca5                                              # KF5 fallback
```

If the pinned entry still shows the old icon, unpin and pin **Forge AI Desktop**
again. A fresh install, or running the Taskbar button after the cache refresh,
picks up the new files without touching the panel configuration.

## Versioning and updates

The displayed version is read from `package.json` at runtime, so the header
always matches the packaged build. Releases are tagged `desktop-v<version>`;
the first stable public release targets `1.1.0` and is gated on packaging,
security review, and clean-install testing.

"Check for updates" asks the GitHub Releases API for the newest stable
`desktop-v*` release and, when a newer version exists, exposes a button that
opens its release page in the default browser. The check is manual, read-only,
and never downloads or installs anything automatically.

A release is only offered for in-app download when it publishes
`SHA256SUMS` and a detached Ed25519 signature `SHA256SUMS.sig`. Forge verifies
the signature against the pinned release key, confirms the downloaded AppImage
is listed in the signed manifest, and checks its SHA-256 before saving it.
Unsigned, tampered, or mismatched releases are rejected. Installation remains
manual.

The V1.1 development build pins the development key
`forge-desktop-dev-2026-11` (SHA-256 fingerprint
`e5bca27ba85dc1b45c6cd59836c57d84f7c9f74c79bf3b26e585fbe58ba47589`). The
private key is not in this repository. Production key provisioning and
rotation are follow-up hardening work.

Release artifacts are signed with `scripts/sign-release.mjs`, which reads a
mode-`600` private key from outside the repository and writes the manifest and
signature next to the packages.

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
