import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import {
  checkForUpdates,
  downloadUpdate,
  getInstalledVersion,
  openReleasePage,
  openDownloadsFolder,
} from './update-service.js';

const requireNative = createRequire(
  path.join(app.getAppPath(), 'package.json'),
);
const pty = requireNative('node-pty');

// Packaged builds must launch the bundled engine, not a developer-only
// ~/.local/bin/forge. FORGE_BIN still overrides for local testing.
function resolveForgePath() {
  const override = process.env.FORGE_BIN;

  if (override) {
    return path.resolve(override);
  }

  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'forge', 'forge');
  }

  return path.join(os.homedir(), '.local', 'bin', 'forge');
}

function resolveForgeDirectory() {
  const configured = process.env.FORGE_WORKSPACE;

  if (configured && fs.existsSync(configured)) {
    return configured;
  }

  const home = path.join(os.homedir(), 'Forge');

  return fs.existsSync(home) ? home : os.homedir();
}

const forgePath = resolveForgePath();
const forgeDirectory = resolveForgeDirectory();

const sessions = new Map();
const MAX_SESSIONS = 12;
let nextId = 1;
let mainWindow = null;
let checking = false;
let downloading = false;
let approvedAsset = null;

function validSender(event) {
  return event.sender === mainWindow?.webContents;
}

function send(channel, payload) {
  if (
    mainWindow &&
    !mainWindow.isDestroyed() &&
    !mainWindow.webContents.isDestroyed()
  ) {
    mainWindow.webContents.send(channel, payload);
  }
}

function validSize(cols, rows) {
  return (
    Number.isInteger(cols) &&
    Number.isInteger(rows) &&
    cols >= 2 &&
    cols <= 500 &&
    rows >= 2 &&
    rows <= 200
  );
}

function publicSession(s) {
  return {
    id: s.id,
    title: s.title,
    running: s.running,
    cols: s.cols,
    rows: s.rows,
  };
}

function stopSession(s) {
  const proc = s.process;
  s.process = null;
  s.running = false;
  if (proc) {
    try {
      proc.kill();
    } catch (error) {
      console.error(error);
    }
  }
}

function startSession(s) {
  stopSession(s);

  if (!fs.existsSync(forgePath)) {
    send('forge:data', {
      id: s.id,
      data: `\r\nForge executable missing: ${forgePath}\r\n`,
    });
    return false;
  }

  try {
    const env = {
      ...process.env,
      TERM: 'xterm-256color',
      COLORTERM: 'truecolor',
    };
    delete env.ELECTRON_RUN_AS_NODE;

    const proc = pty.spawn(forgePath, ['chat'], {
      name: 'xterm-256color',
      cols: s.cols,
      rows: s.rows,
      cwd: fs.existsSync(forgeDirectory) ? forgeDirectory : os.homedir(),
      env,
    });

    s.process = proc;
    s.running = true;

    proc.onData((data) => {
      if (s.process === proc) {
        send('forge:data', { id: s.id, data });
      }
    });

    proc.onExit(({ exitCode }) => {
      if (s.process !== proc) return;
      s.process = null;
      s.running = false;
      send('forge:data', {
        id: s.id,
        data: `\r\n[Forge exited: ${exitCode}]\r\n`,
      });
      send('forge:status', { id: s.id, running: false });
    });

    send('forge:status', { id: s.id, running: true });
    return true;
  } catch (error) {
    send('forge:data', {
      id: s.id,
      data: `\r\nLaunch failed: ${error.message}\r\n`,
    });
    return false;
  }
}

function closeSession(id) {
  const s = sessions.get(id);
  if (!s) return false;
  sessions.delete(id);
  stopSession(s);
  return true;
}

function stopAllSessions() {
  for (const id of sessions.keys()) closeSession(id);
}

ipcMain.handle('forge:create', (event, size = {}) => {
  if (!validSender(event)) return null;
  if (sessions.size >= MAX_SESSIONS) {
    throw new Error('Maximum of 12 tabs reached');
  }

  const id = `forge-${nextId}`;
  const s = {
    id,
    title: `Forge ${nextId++}`,
    cols: validSize(size.cols, size.rows) ? size.cols : 100,
    rows: validSize(size.cols, size.rows) ? size.rows : 30,
    process: null,
    running: false,
  };
  sessions.set(id, s);
  return publicSession(s);
});

ipcMain.handle('forge:start', (event, id) => {
  if (!validSender(event)) return false;
  const s = sessions.get(id);
  return s ? startSession(s) : false;
});

ipcMain.handle('forge:close', (event, id) => {
  return validSender(event) ? closeSession(id) : false;
});

ipcMain.handle('forge:restart', (event, id) => {
  if (!validSender(event)) return false;
  const s = sessions.get(id);
  return s ? startSession(s) : false;
});

ipcMain.on('forge:input', (event, payload) => {
  if (!validSender(event)) return;
  if (typeof payload?.data !== 'string') return;
  if (payload.data.length > 65536) return;
  sessions.get(payload.id)?.process?.write(payload.data);
});

ipcMain.on('forge:resize', (event, payload) => {
  if (!validSender(event)) return;
  const { id, cols, rows } = payload ?? {};
  if (!validSize(cols, rows)) return;

  const s = sessions.get(id);
  if (!s) return;
  if (s.cols === cols && s.rows === rows) return;

  s.cols = cols;
  s.rows = rows;
  try {
    s.process?.resize(cols, rows);
  } catch (error) {
    console.error(error);
  }
});

// GitHub updater
ipcMain.handle('updater:version', (event) => {
  if (!validSender(event)) return null;
  return getInstalledVersion();
});

ipcMain.handle('updater:check', async (event) => {
  if (!validSender(event)) return null;
  if (checking || downloading) {
    throw new Error('Another update operation is running');
  }

  checking = true;
  approvedAsset = null;

  try {
    const result = await checkForUpdates((progress) => {
      send('updater:check-progress', progress);
    });

    if (result.status === 'update-available') {
      approvedAsset = result.asset;
    }

    return result;
  } finally {
    checking = false;
  }
});

ipcMain.handle('updater:download', async (event) => {
  if (!validSender(event)) return null;
  if (downloading || checking) {
    throw new Error('Another update operation is running');
  }
  if (!approvedAsset) {
    throw new Error('Check for an available update first');
  }

  downloading = true;
  const asset = approvedAsset;

  try {
    const result = await downloadUpdate(asset, (progress) => {
      send('updater:download-progress', progress);
    });
    approvedAsset = null;
    return result;
  } finally {
    downloading = false;
  }
});

ipcMain.handle('updater:open-releases', (event) => {
  if (!validSender(event)) return false;
  return openReleasePage();
});

ipcMain.handle('updater:open-downloads', (event) => {
  if (!validSender(event)) return false;
  return openDownloadsFolder();
});

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 850,
    minWidth: 740,
    minHeight: 480,
    title: 'Forge AI Desktop',
    backgroundColor: '#0b1020',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  mainWindow.on('closed', () => {
    stopAllSessions();
    mainWindow = null;
  });

  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(
      path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`),
    );
  }
}

app.whenReady().then(() => {
  app.setName('Forge AI Desktop');
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', stopAllSessions);
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
