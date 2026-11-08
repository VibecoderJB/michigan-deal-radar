// Watchlist: starred companies, stored only on this device (localStorage).

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
    /* storage full or blocked (private mode): the star just won't persist */
  }
  window.dispatchEvent(new CustomEvent("watchlist-change"));
}

export const watchlist = {
  all: () => read(),
  has: (cik) => Boolean(read()[cik]),
  count: () => Object.keys(read()).length,
  toggle(cik, name) {
    const items = read();
    if (items[cik]) delete items[cik];
    else items[cik] = { name, addedAt: new Date().toISOString() };
    write(items);
    return Boolean(items[cik]);
  },
  lastSeen() {
    try {
      return localStorage.getItem(SEEN_KEY);
    } catch {
      return null;
    }
  },
  markSeen(isoDate) {
    try {
      localStorage.setItem(SEEN_KEY, isoDate);
    } catch {
      /* ignore */
    }
  },
};

const STAR = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 17.3l-6.2 3.7 1.7-7L2 9.2l7.2-.6L12 2l2.8 6.6 7.2.6-5.5 4.8 1.7 7z"/></svg>`;

/** Star toggle button. Clicks are handled globally in main.js via [data-star]. */
export function starButton(cik, name, { label = false } = {}) {
  const on = watchlist.has(cik);
  const text = label ? `<span>${on ? "Watching" : "Watch"}</span>` : "";
  const safeName = String(name).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  return `<button type="button" class="star-btn ${on ? "on" : ""} ${label ? "" : "icon-only"}" data-star="${cik}" data-name="${safeName}" aria-pressed="${on}" aria-label="${on ? "Remove from" : "Add to"} watchlist">${STAR}${text}</button>`;
}
