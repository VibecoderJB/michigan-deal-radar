// Michigan Deal Radar desktop app (Electron).
//
// Online: loads the live site so data is always the latest daily refresh.
// Offline: falls back to the copy of the app + data bundled at build time.
// No AI, no telemetry; the only network calls go to the GitHub Pages site and SEC links you click.

const { app, BrowserWindow, Menu, net, protocol, shell } = require("electron");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const LIVE_URL = "https://vibecoderjb.github.io/michigan-deal-radar/";
const LOCAL_URL = "app://bundle/index.html";
const WEB_ROOT = path.join(__dirname, "web");

// Custom scheme so the bundled copy can use ES modules, fetch() and a service worker.
protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
]);

function serveBundle() {
  protocol.handle("app", (request) => {
    const { pathname } = new URL(request.url);
    const safe = path.normalize(decodeURIComponent(pathname)).replace(/^(\.\.[/\\])+/, "");
    const file = path.join(WEB_ROOT, safe === path.sep || safe === "/" ? "index.html" : safe);
    if (!file.startsWith(WEB_ROOT)) return new Response("Not found", { status: 404 });
    return net.fetch(pathToFileURL(file).toString());
  });
}

async function liveSiteReachable() {
  try {
    const res = await Promise.race([
      net.fetch(`${LIVE_URL}data/meta.json`, { cache: "no-store" }),
      new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 5000)),
    ]);
    return res.ok;
  } catch {
    return false;
  }
}

const isAppUrl = (url) => url.startsWith(LIVE_URL) || url.startsWith("app://bundle/");

async function createWindow() {
  const win = new BrowserWindow({
    width: 1360,
    height: 880,
    minWidth: 380,
    minHeight: 560,
    title: "Michigan Deal Radar",
    backgroundColor: "#07111f",
    icon: path.join(__dirname, "build", "icon.png"),
    show: false,
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false },
  });

  // SEC filings and other external links open in the user's normal browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (!isAppUrl(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!isAppUrl(url)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  win.once("ready-to-show", () => win.show());
  const online = await liveSiteReachable();
  await win.loadURL(online ? LIVE_URL : LOCAL_URL);
  // If the live page fails mid-load (network drop), use the bundled copy.
  win.webContents.on("did-fail-load", (_e, code, _desc, url) => {
    if (code !== -3 && url.startsWith(LIVE_URL)) win.loadURL(LOCAL_URL);
  });
  return win;
}

function buildMenu() {
  const isMac = process.platform === "darwin";
  const template = [
    ...(isMac ? [{ role: "appMenu" }] : []),
    { role: "fileMenu" },
    { role: "editMenu" },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    {
      role: "help",
      submenu: [
        { label: "Project on GitHub", click: () => shell.openExternal("https://github.com/VibecoderJB/michigan-deal-radar") },
        { label: "SEC EDGAR", click: () => shell.openExternal("https://www.sec.gov/edgar/search/") },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const [win] = BrowserWindow.getAllWindows();
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  app.whenReady().then(() => {
    serveBundle();
    buildMenu();
    createWindow();
    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });
}
