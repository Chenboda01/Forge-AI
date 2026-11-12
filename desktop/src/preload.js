import { contextBridge, ipcRenderer } from 'electron';

function subscribe(channel, callback) {
  const listener = (_event, payload) => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

contextBridge.exposeInMainWorld('forgeDesktop', {
  create(cols, rows) {
    return ipcRenderer.invoke('forge:create', { cols, rows });
  },
  start(id) {
    return ipcRenderer.invoke('forge:start', id);
  },
  close(id) {
    return ipcRenderer.invoke('forge:close', id);
  },
  restart(id) {
    return ipcRenderer.invoke('forge:restart', id);
  },
  write(id, data) {
    ipcRenderer.send('forge:input', { id, data });
  },
  resize(id, cols, rows) {
    ipcRenderer.send('forge:resize', { id, cols, rows });
  },
  onData(callback) {
    return subscribe('forge:data', callback);
  },
  onStatus(callback) {
    return subscribe('forge:status', callback);
  },

  taskbar: {
    status() {
      return ipcRenderer.invoke('taskbar:status');
    },
    install() {
      return ipcRenderer.invoke('taskbar:install');
    },
  },

  updater: {
    version() {
      return ipcRenderer.invoke('updater:version');
    },
    check() {
      return ipcRenderer.invoke('updater:check');
    },
    download() {
      return ipcRenderer.invoke('updater:download');
    },
    openReleases() {
      return ipcRenderer.invoke('updater:open-releases');
    },
    openDownloads() {
      return ipcRenderer.invoke('updater:open-downloads');
    },
    onCheckProgress(callback) {
      return subscribe('updater:check-progress', callback);
    },
    onDownloadProgress(callback) {
      return subscribe('updater:download-progress', callback);
    },
  },
});
