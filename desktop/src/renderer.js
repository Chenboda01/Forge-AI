import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import startupArt from './assets/forge-startup.png';
import {
  SPLASH_FADE_MS,
  SPLASH_MAX_VISIBLE_MS,
  SPLASH_MIN_VISIBLE_MS,
  SPLASH_TEXT,
  shouldDismissSplash,
} from './splash-core.mjs';
import {
  SPLASH_LOADER_LABEL,
  glassPerformanceTier,
  pointerPercent,
  splashLoaderState,
} from './glass-core.mjs';
import './index.css';

function webglRenderer() {
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl');

    if (!gl) return '';

    const info = gl.getExtension('WEBGL_debug_renderer_info');

    return info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : '';
  } catch {
    return '';
  }
}

document.documentElement.dataset.glassPerf = glassPerformanceTier({
  hardwareConcurrency: navigator.hardwareConcurrency,
  renderer: webglRenderer(),
});

const api = window.forgeDesktop;
const updater = api.updater;
const $ = (selector) => document.querySelector(selector);

document.querySelector('#app').innerHTML = `
  <div id="splash" class="splash" role="status">
    <div class="splash-content">
      <img
        class="splash-art"
        src="${startupArt}"
        alt=""
        width="640"
        height="640"
        draggable="false"
      >
      <p class="splash-title">${SPLASH_TEXT}</p>
      <div
        id="splash-loader"
        class="splash-loader"
        role="progressbar"
        aria-label="${SPLASH_LOADER_LABEL}"
        aria-valuetext="Starting"
      >
        <div class="splash-loader__fill"></div>
      </div>
    </div>
  </div>

  <div class="app">
    <header class="header glass-interactive">
      <div class="branding">
        <div class="logo">F</div>
        <div>
          <h1>Forge AI</h1>
          <p id="app-version">Desktop Edition</p>
        </div>
      </div>

      <div class="controls">
        <span id="session-count">0 sessions</span>
        <button id="update-button" class="update-button">
          ✦ Check for Updates
        </button>
        <button
          id="taskbar-button"
          class="taskbar-button glass-interactive"
          title="Add Forge to your application launcher"
        >
          ⌖ Taskbar
        </button>
        <button id="restart" class="glass-interactive">↻ Restart</button>
      </div>
    </header>

    <nav class="tabbar glass-interactive" aria-label="Forge sessions">
      <div id="tabs" role="tablist"></div>
      <button id="new-tab" class="glass-interactive">+ New Tab</button>
    </nav>

    <main class="workspace">
      <div class="terminal-header">
        <span id="active-title">Forge Terminal</span>
        <span id="active-status">Starting...</span>
      </div>
      <div id="terminal-host"></div>
    </main>

    <footer class="footer">
      <span>Forge AI · Independent agent sessions</span>
      <span id="terminal-size">-- × --</span>
    </footer>

    <div id="update-overlay" class="update-overlay hidden">
      <section
        id="glass-panel"
        class="glass-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-title"
        tabindex="-1"
      >
        <div class="glass-shine"></div>

        <div class="glass-top">
          <div class="glass-icon">✦</div>
          <button
            id="close-update"
            class="close-glass"
            aria-label="Close updater"
          >×</button>
        </div>

        <h2 id="update-title">Forge AI Updater</h2>
        <p id="update-message" class="update-message">
          Ready to check GitHub Releases.
        </p>

        <div class="version-row">
          <span>Installed version</span>
          <strong id="installed-version">...</strong>
        </div>

        <div class="version-row">
          <span>Latest release</span>
          <strong id="latest-version">...</strong>
        </div>

        <div id="check-section" class="progress-section">
          <div class="progress-heading">
            <span>Checking GitHub</span>
            <strong id="check-percent">0%</strong>
          </div>

          <div
            id="check-track"
            class="progress-track aqua"
            role="progressbar"
            aria-label="Update check progress"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow="0"
          >
            <div id="check-fill" class="progress-fill"></div>
          </div>

          <p id="check-detail" class="progress-detail">
            Waiting...
          </p>
        </div>

        <div
          id="download-section"
          class="progress-section hidden"
        >
          <div class="progress-heading">
            <span>Downloading update</span>
            <strong id="download-percent">0%</strong>
          </div>

          <div
            id="download-track"
            class="progress-track scarlet"
            role="progressbar"
            aria-label="Update download progress"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow="0"
          >
            <div id="download-fill" class="progress-fill"></div>
          </div>

          <p id="download-detail" class="progress-detail">
            Waiting...
          </p>
        </div>

        <div
          id="update-result"
          class="update-result"
          role="status"
          aria-live="polite"
        ></div>

        <div class="glass-actions">
          <button
            id="download-button"
            class="scarlet-button hidden"
          >
            Download Update
          </button>

          <button
            id="releases-button"
            class="secondary-button hidden"
          >
            View GitHub Releases
          </button>

          <button
            id="downloads-button"
            class="secondary-button hidden"
          >
            Open Downloads
          </button>
        </div>
      </section>
    </div>

    <div id="taskbar-overlay" class="update-overlay hidden">
      <section
        id="taskbar-panel"
        class="glass-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="taskbar-title"
        tabindex="-1"
      >
        <div class="glass-shine"></div>

        <div class="glass-top">
          <div class="glass-icon">⌖</div>
          <button
            id="close-taskbar"
            class="close-glass"
            aria-label="Close taskbar setup"
          >×</button>
        </div>

        <h2 id="taskbar-title">Taskbar Shortcut</h2>
        <p id="taskbar-message" class="update-message">
          Checking shortcut status...
        </p>

        <div class="version-row">
          <span>Shortcut file</span>
          <strong id="taskbar-path">...</strong>
        </div>

        <div id="taskbar-appimage-row" class="version-row hidden">
          <span>AppImage</span>
          <strong id="taskbar-appimage">...</strong>
        </div>

        <div
          id="taskbar-result"
          class="update-result"
          role="status"
          aria-live="polite"
        ></div>

        <ol class="taskbar-steps">
          <li>Install the shortcut for this user.</li>
          <li>Open the application launcher.</li>
          <li>
            Right-click <strong>Forge AI Desktop</strong> and choose
            <strong>Pin to Taskbar</strong>.
          </li>
        </ol>

        <p class="taskbar-note">
          AppImages are copied to ~/Applications so rebuilds and updates keep
          the launcher working. KDE controls taskbar pinning. Forge never edits
          panel configuration or reports the application as pinned until you
          pin it yourself.
        </p>

        <div class="glass-actions">
          <button id="taskbar-install" class="scarlet-button">
            Install Shortcut
          </button>

          <button id="taskbar-close" class="secondary-button">
            Close
          </button>
        </div>
      </section>
    </div>
  </div>
`;

for (const element of document.querySelectorAll(
  '.update-button, .secondary-button, .scarlet-button, .close-glass',
)) {
  element.classList.add('glass-interactive');
}

const splash = $('#splash');
const splashShownAt = performance.now();
let terminalReady = false;
let splashDismissed = false;
let splashHideTimer = null;

function clearSplashCheckTimers() {
  window.clearTimeout(splashMinimumTimer);
  window.clearTimeout(splashMaximumTimer);
}

function finishSplashDismissal() {
  splash.classList.add('hidden');
  splash.setAttribute('aria-hidden', 'true');
  performance.mark('forge:splash-hidden');
}

function dismissSplash() {
  if (splashDismissed) return;

  splashDismissed = true;
  clearSplashCheckTimers();
  splash.classList.add('splash-leaving');
  splashHideTimer = window.setTimeout(finishSplashDismissal, SPLASH_FADE_MS);
}

function hideSplashImmediately() {
  splashDismissed = true;
  clearSplashCheckTimers();

  if (splashHideTimer !== null) {
    window.clearTimeout(splashHideTimer);
  }

  splash.classList.add('splash-leaving', 'hidden');
  splash.setAttribute('aria-hidden', 'true');
}

function checkSplashDismissal() {
  if (
    shouldDismissSplash({
      elapsedMs: performance.now() - splashShownAt,
      terminalReady,
    })
  ) {
    dismissSplash();
  }
}

function markSplashReady() {
  const loader = $('#splash-loader');

  if (!loader) return;

  loader.dataset.state = splashLoaderState({ terminalReady: true });
  loader.setAttribute('aria-valuetext', 'Ready');
}

const splashMinimumTimer = window.setTimeout(
  checkSplashDismissal,
  SPLASH_MIN_VISIBLE_MS,
);
const splashMaximumTimer = window.setTimeout(
  dismissSplash,
  SPLASH_MAX_VISIBLE_MS,
);

// --------------------------------------------------
// MULTIPLE FORGE TERMINAL TABS
// --------------------------------------------------

const sessions = new Map();
const host = $('#terminal-host');

let activeId = null;
let creating = false;
let resizeFrame = null;

function createTerminal() {
  const terminal = new Terminal({
    cursorBlink: true,
    fontSize: 15,
    lineHeight: 1.15,
    fontFamily: '"DejaVu Sans Mono", "Liberation Mono", monospace',
    scrollback: 5000,
    convertEol: false,
    theme: {
      background: '#0b1020',
      foreground: '#e5e7eb',
      cursor: '#38bdf8',
      selectionBackground: '#334155',
      black: '#111827',
      red: '#f87171',
      green: '#4ade80',
      yellow: '#facc15',
      blue: '#60a5fa',
      magenta: '#c084fc',
      cyan: '#22d3ee',
      white: '#f8fafc',
    },
  });

  const fit = new FitAddon();
  terminal.loadAddon(fit);

  return { terminal, fit };
}

function updateTabs() {
  const tabs = $('#tabs');
  tabs.replaceChildren();

  for (const session of sessions.values()) {
    const button = document.createElement('button');
    button.className =
      'tab glass-interactive' + (session.id === activeId ? ' active' : '');
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-selected', String(session.id === activeId));

    const dot = document.createElement('span');
    dot.className = 'tab-dot' + (session.running ? ' running' : '');

    const label = document.createElement('span');
    label.className = 'tab-label';
    label.textContent = session.title;

    const close = document.createElement('span');
    close.className = 'tab-close';
    close.textContent = '×';
    close.title = 'Close tab';

    close.addEventListener('click', (event) => {
      event.stopPropagation();
      closeTab(session.id);
    });

    button.append(dot, label, close);
    button.addEventListener('click', () => {
      activateTab(session.id);
    });

    tabs.appendChild(button);
  }

  const count = sessions.size;
  $('#session-count').textContent = `${count} session${count === 1 ? '' : 's'}`;

  const active = sessions.get(activeId);

  $('#active-title').textContent = active
    ? `❯ ${active.title}`
    : 'Forge Terminal';

  $('#active-status').textContent = active
    ? active.running
      ? '● Running'
      : '○ Stopped'
    : 'No active session';

  $('#active-status').className = active?.running ? 'running-text' : '';

  $('#restart').disabled = !active;
}

function resizeActive() {
  const session = sessions.get(activeId);
  if (!session) return;

  if (host.clientWidth < 20 || host.clientHeight < 20) {
    return;
  }

  try {
    session.fit.fit();

    const cols = session.terminal.cols;
    const rows = session.terminal.rows;

    if (cols < 2 || rows < 2) return;

    if (session.cols !== cols || session.rows !== rows) {
      session.cols = cols;
      session.rows = rows;

      api.resize(session.id, cols, rows);
    }

    $('#terminal-size').textContent = `${cols} × ${rows}`;
    session.terminal.refresh(0, rows - 1);
  } catch (error) {
    console.error('Terminal resize failed:', error);
  }
}

function scheduleResize() {
  if (resizeFrame !== null) {
    cancelAnimationFrame(resizeFrame);
  }

  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = null;
    resizeActive();
  });
}

function activateTab(id) {
  const session = sessions.get(id);
  if (!session) return;

  activeId = id;

  for (const item of sessions.values()) {
    item.element.classList.toggle('visible', item.id === id);
  }

  updateTabs();
  scheduleResize();

  requestAnimationFrame(() => {
    session.terminal.focus();
  });
}

async function newTab() {
  if (creating) return;

  creating = true;
  $('#new-tab').disabled = true;

  let createdId = null;

  try {
    const previous = sessions.get(activeId);

    const info = await api.create(previous?.cols || 100, previous?.rows || 30);

    if (!info) {
      throw new Error('Cannot create Forge session');
    }

    createdId = info.id;

    const { terminal, fit } = createTerminal();
    const element = document.createElement('div');

    element.className = 'terminal-pane';
    host.appendChild(element);
    terminal.open(element);

    const session = {
      id: info.id,
      title: info.title,
      terminal,
      fit,
      element,
      running: false,
      cols: info.cols,
      rows: info.rows,
    };

    sessions.set(info.id, session);

    terminal.onData((data) => {
      api.write(session.id, data);
    });

    activateTab(info.id);

    // Fit before starting Textual.
    await new Promise((resolve) => {
      requestAnimationFrame(() => {
        resizeActive();
        resolve();
      });
    });

    const started = await api.start(info.id);

    if (!started) {
      throw new Error('Could not launch Forge AI');
    }

    session.running = true;
    terminalReady = true;
    performance.mark('forge:terminal-ready');
    markSplashReady();
    checkSplashDismissal();
    updateTabs();

    // Redraw after the PTY has started.
    scheduleResize();
  } catch (error) {
    console.error('New tab error:', error);

    if (createdId) {
      const session = sessions.get(createdId);

      if (session) {
        session.terminal.dispose();
        session.element.remove();
        sessions.delete(createdId);
      }

      await api.close(createdId);
    }

    activeId = null;
    const first = sessions.keys().next().value;

    if (first) activateTab(first);
    else updateTabs();

    hideSplashImmediately();
    window.alert(error.message);
  } finally {
    creating = false;
    $('#new-tab').disabled = false;
  }
}

async function closeTab(id) {
  const session = sessions.get(id);
  if (!session) return;

  const ids = [...sessions.keys()];
  const index = ids.indexOf(id);

  sessions.delete(id);

  await api.close(id);

  session.terminal.dispose();
  session.element.remove();

  if (activeId === id) {
    const next = ids[index + 1] || ids[index - 1];
    activeId = null;

    if (next && sessions.has(next)) {
      activateTab(next);
    } else {
      $('#terminal-size').textContent = '-- × --';
      updateTabs();
    }
  } else {
    updateTabs();
  }
}

const unsubscribeData = api.onData(({ id, data }) => {
  sessions.get(id)?.terminal.write(data);
});

const unsubscribeStatus = api.onStatus(({ id, running }) => {
  const session = sessions.get(id);
  if (!session) return;

  session.running = running;
  updateTabs();
});

$('#new-tab').addEventListener('click', newTab);

$('#restart').addEventListener('click', async () => {
  const session = sessions.get(activeId);
  if (!session) return;

  session.terminal.reset();
  session.terminal.writeln('Restarting Forge AI...');

  session.running = false;
  updateTabs();

  try {
    session.running = Boolean(await api.restart(session.id));
    updateTabs();
    session.terminal.focus();
  } catch (error) {
    session.terminal.writeln(`Restart failed: ${error.message}`);
  }
});

const resizeObserver = new ResizeObserver(scheduleResize);
resizeObserver.observe(host);

window.addEventListener('resize', scheduleResize);

window.addEventListener('keydown', (event) => {
  if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 't') {
    event.preventDefault();
    newTab();
  }
});

// --------------------------------------------------
// LIQUID GLASS UPDATER
// --------------------------------------------------

let updateBusy = false;

function setProgress(type, percent, detail = '') {
  const fill = $(`#${type}-fill`);
  const label = $(`#${type}-percent`);
  const track = $(`#${type}-track`);

  if (percent === null || percent === undefined) {
    label.textContent = '...';
    fill.style.width = '100%';
    fill.classList.add('indeterminate');
    track.removeAttribute('aria-valuenow');
  } else {
    const value = Math.max(0, Math.min(100, Math.round(percent)));

    label.textContent = `${value}%`;
    fill.style.width = `${value}%`;
    fill.classList.remove('indeterminate');
    track.setAttribute('aria-valuenow', String(value));
  }

  $(`#${type}-detail`).textContent = detail;
}

function setResult(message, type = '') {
  const element = $('#update-result');
  element.className = `update-result ${type}`;
  element.textContent = message;
}

function showUpdater() {
  $('#update-overlay').classList.remove('hidden');
  $('#glass-panel').focus();
}

function hideUpdater() {
  if (updateBusy) return;
  $('#update-overlay').classList.add('hidden');
  $('#update-button').focus();
}

function setBusy(busy) {
  updateBusy = busy;
  $('#update-button').disabled = busy;
  $('#close-update').disabled = busy;
  $('#download-button').disabled = busy;
}

$('#close-update').addEventListener('click', hideUpdater);

$('#update-overlay').addEventListener('click', (event) => {
  if (event.target === $('#update-overlay')) {
    hideUpdater();
  }
});

window.addEventListener('keydown', (event) => {
  if (
    event.key === 'Escape' &&
    !$('#update-overlay').classList.contains('hidden')
  ) {
    event.preventDefault();
    hideUpdater();
  }
});

let glassPointerFrame = 0;
let glassPointerTarget = null;
let glassPointerX = 0;
let glassPointerY = 0;

document.addEventListener(
  'pointermove',
  (event) => {
    const target = event.target.closest?.('.glass-interactive, .glass-panel');

    if (!target) return;

    glassPointerTarget = target;
    glassPointerX = event.clientX;
    glassPointerY = event.clientY;

    if (glassPointerFrame !== 0) return;

    glassPointerFrame = requestAnimationFrame(() => {
      glassPointerFrame = 0;

      if (!glassPointerTarget) return;

      const { x, y } = pointerPercent({
        clientX: glassPointerX,
        clientY: glassPointerY,
        rect: glassPointerTarget.getBoundingClientRect(),
      });

      glassPointerTarget.style.setProperty('--gx', `${x}%`);
      glassPointerTarget.style.setProperty('--gy', `${y}%`);
      glassPointerTarget.style.setProperty('--x', `${x}%`);
      glassPointerTarget.style.setProperty('--y', `${y}%`);
    });
  },
  { passive: true },
);

// Actual GitHub checking stages.
const unsubscribeCheck = updater.onCheckProgress(({ percent, message }) => {
  setProgress('check', percent, message);
});

// Actual download bytes.
const unsubscribeDownload = updater.onDownloadProgress(
  ({ percent, received, total }) => {
    const downloadedMB = (received / 1048576).toFixed(1);

    const detail = total
      ? `${downloadedMB} / ${(total / 1048576).toFixed(1)} MB`
      : `${downloadedMB} MB downloaded`;

    setProgress('download', percent, detail);
  },
);

$('#update-button').addEventListener('click', async () => {
  if (updateBusy) return;

  showUpdater();
  setBusy(true);

  $('#download-button').classList.add('hidden');
  $('#downloads-button').classList.add('hidden');
  $('#releases-button').classList.add('hidden');

  $('#check-section').classList.remove('hidden');
  $('#download-section').classList.add('hidden');

  $('#update-message').textContent = 'Checking GitHub Releases...';

  $('#latest-version').textContent = 'Checking...';

  setResult('');
  setProgress('check', 0, 'Connecting to GitHub...');

  try {
    const result = await updater.check();

    $('#installed-version').textContent = result.currentVersion;

    $('#latest-version').textContent = result.latestVersion || 'Not published';

    if (result.status === 'up-to-date') {
      $('#update-message').textContent = 'Update check complete';

      setResult("No update found, you're up to date ✓", 'success');
    } else if (result.status === 'no-release') {
      $('#update-message').textContent = 'Update check complete';

      setResult('No stable release has been published yet.', 'neutral');

      $('#releases-button').classList.remove('hidden');
    } else if (result.status === 'update-available') {
      $('#update-message').textContent = 'Update available!';

      if (result.asset) {
        setResult(
          `Forge AI Desktop ${result.latestVersion} is available.`,
          'available',
        );

        $('#download-button').classList.remove('hidden');
      } else if (result.assetError === 'missing-signature') {
        setResult(
          'A newer release exists, but it has no signed release manifest. Download it from GitHub instead.',
          'available',
        );
      } else {
        setResult(
          'A newer release exists, but no compatible signed Linux AppImage was found.',
          'available',
        );
      }

      $('#releases-button').classList.remove('hidden');
    } else {
      throw new Error('Unexpected update-check result');
    }
  } catch (error) {
    $('#update-message').textContent = 'Update check failed';

    setResult(error.message, 'error');
    $('#releases-button').classList.remove('hidden');
  } finally {
    setBusy(false);
  }
});

$('#download-button').addEventListener('click', async () => {
  if (updateBusy) return;

  setBusy(true);

  $('#download-section').classList.remove('hidden');
  $('#update-message').textContent = 'Downloading your update...';

  setResult('');
  setProgress('download', 0, 'Starting download...');

  try {
    const result = await updater.download();

    setProgress('download', 100, 'Download completed');

    $('#update-message').textContent = 'Download complete';

    setResult(
      `Update saved to ${result.path}. Signature and SHA-256 verified. Installation is manual.`,
      'success',
    );

    $('#download-button').classList.add('hidden');
    $('#downloads-button').classList.remove('hidden');
  } catch (error) {
    $('#update-message').textContent = 'Download failed';

    setResult(error.message, 'error');
  } finally {
    setBusy(false);
  }
});

$('#releases-button').addEventListener('click', () => {
  updater.openReleases();
});

$('#downloads-button').addEventListener('click', () => {
  updater.openDownloads();
});

// Taskbar shortcut setup. The panel reports the entry file and the exact
// manual pinning steps; it never claims the application is pinned.
let taskbarBusy = false;

function setTaskbarResult(message, type = '') {
  const element = $('#taskbar-result');
  element.className = `update-result ${type}`;
  element.textContent = message;
}

function showTaskbar() {
  $('#taskbar-overlay').classList.remove('hidden');
  $('#taskbar-panel').focus();
}

function hideTaskbar() {
  if (taskbarBusy) return;
  $('#taskbar-overlay').classList.add('hidden');
  $('#taskbar-button').focus();
}

function setTaskbarBusy(busy) {
  taskbarBusy = busy;
  $('#taskbar-button').disabled = busy;
  $('#close-taskbar').disabled = busy;
  $('#taskbar-install').disabled = busy;
}

async function openTaskbar() {
  if (taskbarBusy) return;

  showTaskbar();
  setTaskbarResult('');
  $('#taskbar-message').textContent = 'Checking shortcut status...';
  $('#taskbar-path').textContent = '...';
  $('#taskbar-appimage-row').classList.add('hidden');
  $('#taskbar-appimage').textContent = '...';
  $('#taskbar-install').classList.add('hidden');
  setTaskbarBusy(true);

  try {
    const status = await api.taskbar.status();

    if (!status) {
      throw new Error('Taskbar status unavailable');
    }

    $('#taskbar-message').textContent = status.message;
    $('#taskbar-path').textContent =
      status.kind === 'system'
        ? status.systemEntryPath
        : status.entryPath || 'Not installed';

    if (status.kind === 'appimage' && status.appImagePath) {
      $('#taskbar-appimage-row').classList.remove('hidden');
      $('#taskbar-appimage').textContent = status.appImagePath;
    }

    if (
      status.supported &&
      (!status.installed || status.needsAppImageInstall)
    ) {
      $('#taskbar-install').classList.remove('hidden');
    }
  } catch (error) {
    $('#taskbar-message').textContent = 'Taskbar shortcut unavailable';
    setTaskbarResult(error.message, 'error');
  } finally {
    setTaskbarBusy(false);
  }
}

$('#taskbar-button').addEventListener('click', openTaskbar);
$('#close-taskbar').addEventListener('click', hideTaskbar);
$('#taskbar-close').addEventListener('click', hideTaskbar);

$('#taskbar-overlay').addEventListener('click', (event) => {
  if (event.target === $('#taskbar-overlay')) {
    hideTaskbar();
  }
});

window.addEventListener('keydown', (event) => {
  if (
    event.key === 'Escape' &&
    !$('#taskbar-overlay').classList.contains('hidden')
  ) {
    event.preventDefault();
    hideTaskbar();
  }
});

$('#taskbar-install').addEventListener('click', async () => {
  if (taskbarBusy) return;

  setTaskbarBusy(true);
  setTaskbarResult('');
  $('#taskbar-message').textContent = 'Installing shortcut...';

  try {
    const result = await api.taskbar.install();

    if (!result) {
      throw new Error('Taskbar install failed');
    }

    $('#taskbar-path').textContent = result.path;
    $('#taskbar-message').textContent = result.message;

    if (result.appImagePath) {
      $('#taskbar-appimage-row').classList.remove('hidden');
      $('#taskbar-appimage').textContent = result.appImagePath;
    }

    $('#taskbar-install').classList.add('hidden');
    setTaskbarResult(
      result.copied
        ? 'AppImage installed to ~/Applications. Pin it from the application launcher.'
        : 'Shortcut ready. Pin it from the application launcher.',
      'success',
    );
  } catch (error) {
    $('#taskbar-message').textContent = 'Shortcut install failed';
    setTaskbarResult(error.message, 'error');
  } finally {
    setTaskbarBusy(false);
  }
});

// Read the installed application version.
updater
  .version()
  .then((version) => {
    $('#app-version').textContent = `Desktop Edition · V${version}`;

    $('#installed-version').textContent = version;
  })
  .catch(() => {
    $('#app-version').textContent = 'Desktop Edition';
  });

// Start the first Forge session.
newTab();

// Clean up when Vite reloads the renderer.
if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    clearSplashCheckTimers();

    if (splashHideTimer !== null) {
      window.clearTimeout(splashHideTimer);
    }

    resizeObserver.disconnect();

    unsubscribeData();
    unsubscribeStatus();
    unsubscribeCheck();
    unsubscribeDownload();

    for (const session of sessions.values()) {
      api.close(session.id);
      session.terminal.dispose();
    }

    sessions.clear();
  });
}
