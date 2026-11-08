// Copy the web app + latest data into desktop/web so the installer works offline.
const fs = require("node:fs");
const path = require("node:path");

const repo = path.resolve(__dirname, "..", "..");
const out = path.resolve(__dirname, "..", "web");

fs.rmSync(out, { recursive: true, force: true });
fs.cpSync(path.join(repo, "app"), out, { recursive: true });
fs.cpSync(path.join(repo, "data"), path.join(out, "data"), { recursive: true });

const count = (dir) =>
  fs.readdirSync(dir, { withFileTypes: true }).reduce((n, e) => n + (e.isDirectory() ? count(path.join(dir, e.name)) : 1), 0);
console.log(`Bundled ${count(out)} files into desktop/web`);
