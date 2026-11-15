// Watchlist: starred companies (by SEC CIK, or by name for news-only deals), stored on this device only.
import { ciksOf, partyName } from "./data.js";
import { esc } from "./format.js";

const KEY = "mdr.watchlist.v1";
const SEEN_KEY = "mdr.watchlist.lastSeen";

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}
function write(items) {
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    /* storage blocked: the star just won't persist */
  }
}

/** The company a deal is "about" for watchlist purposes: the Michigan party. */
export function companyKey(d) {
  const cik = ciksOf(d)[0];
  const name = partyName(d.michigan_party) || partyName(d.target) || partyName(d.acquirer) || d.title;
  return { key: cik ? `cik:${cik}` : `name:${(name || "").toLowerCase()}`, name };
}

export const watchlist = {
  all: () => read(),
  has: (key) => Boolean(read()[key] || read()[key.replace(/^cik:/, "")]),
  toggle(key, name) {
    const items = read();
    const legacy = key.replace(/^cik:/, ""); // v1 stored bare CIKs
    if (items[key] || items[legacy]) {
      delete items[key];
      delete items[legacy];
    } else items[key] = { name, addedAt: new Date().toISOString() };
    write(items);
    return Boolean(items[key]);
  },
  matches(d) {
    const items = read();
    return ciksOf(d).some((c) => items[`cik:${c}`] || items[c]) || Boolean(items[companyKey(d).key]);
  },
  lastSeen() {
    try { return localStorage.getItem(SEEN_KEY); } catch { return null; }
  },
  markSeen(iso) {
    try { localStorage.setItem(SEEN_KEY, iso); } catch { /* ignore */ }
  },
};

const STAR = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 17.3l-6.2 3.7 1.7-7L2 9.2l7.2-.6L12 2l2.8 6.6 7.2.6-5.5 4.8 1.7 7z"/></svg>`;

export function starButton(d, { label = false } = {}) {
  const { key, name } = companyKey(d);
  const on = watchlist.has(key);
  return `<button type="button" class="star-btn ${on ? "on" : ""} ${label ? "" : "icon-only"}" data-star="${esc(key)}" data-name="${esc(name)}" aria-pressed="${on}" aria-label="${on ? "Remove" : "Add"} ${esc(name)} ${on ? "from" : "to"} watchlist">${STAR}${label ? `<span>${on ? "Watching" : "Watch"}</span>` : ""}</button>`;
}
