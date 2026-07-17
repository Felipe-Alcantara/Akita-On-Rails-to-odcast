// Ponte segura entre renderer e processo principal (contextIsolation).

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("audiofy", {
  bridge: (...args) => ipcRenderer.invoke("bridge", args),
  openPath: (target) => ipcRenderer.invoke("open-path", target),
});
