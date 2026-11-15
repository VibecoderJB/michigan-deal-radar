// Copy the web app + latest data into desktop/web so the installer works offline.
const fs = require("node:fs");
const path = require("node:path");

const repo = path.resolve(__dirname, "..", "..");
const out = path.resolve(__dirname, "..", "web");

fs.rmSync(out, { recursive: true, force: true });
fs.cpSync(path.join(repo, "app"), out, { recursive: true });
// Datasets only: skip the evidence text archive, the evidence ledger and v1 backups (not used by the app).
const skip = new Set(["evidence_text", "backup", "evidence.json"]);
fs.cpSync(path.join(repo, "data"), path.join(out, "data"), { recursive: true, filter: (src) => !skip.has(path.basename(src)) });

const count = (dir) =>
  fs.readdirSync(dir, { withFileTypes: true }).reduce((n, e) => n + (e.isDirectory() ? count(path.join(dir, e.name)) : 1), 0);
console.log(`Bundled ${count(out)} files into desktop/web`);
