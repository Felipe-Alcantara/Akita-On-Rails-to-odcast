// Processo principal do Audiofy Desktop.
// Toda a lógica vive no backend Python; esta camada só chama a bridge JSON
// (python3 -m audiofy.bridge <cmd>) e repassa o resultado ao renderer.

const { app, BrowserWindow, ipcMain, shell } = require("electron");
const { execFile } = require("child_process");
const path = require("path");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const PYTHON = process.env.AUDIOFY_PYTHON || "python3";

function bridge(args) {
  return new Promise((resolve) => {
    execFile(
      PYTHON,
      ["-m", "audiofy.bridge", ...args],
      {
        cwd: PROJECT_ROOT,
        env: { ...process.env, PYTHONPATH: "src" },
        maxBuffer: 32 * 1024 * 1024,
        timeout: 10 * 60 * 1000,
      },
      (error, stdout) => {
        try {
          resolve(JSON.parse(stdout.trim().split("\n").pop()));
        } catch (parseError) {
          resolve({ ok: false, error: String(error || parseError) });
        }
      }
    );
  });
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1100,
    height: 760,
    title: "Audiofy Content AI",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  window.loadFile("renderer/index.html");
}

app.whenReady().then(() => {
  ipcMain.handle("bridge", (_event, args) => bridge(args));
  ipcMain.handle("open-path", (_event, target) => shell.openPath(target));
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
