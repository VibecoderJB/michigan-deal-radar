// One place for every number/date format so the whole app is consistent:
//   money   -> $45.7M / $1.2B / $850K       (compact, prose & cards)
//   mm      -> $45.7  (banking tables, $ in millions, one decimal)
//   mult    -> 8.5x
//   date    -> Nov 2, 2026
//   Not disclosed is always rendered by ndHtml() / ND.

export const ND = "Not disclosed";
const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape untrusted text (all source data) before inserting into HTML. */
export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);
export const ndHtml = (label = ND) => `<span class="nd">${label}</span>`;

export function money(value, { empty = ND } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return empty;
  const abs = Math.abs(value);
  for (const [size, suffix] of [[1e9, "B"], [1e6, "M"], [1e3, "K"]]) {
    if (abs >= size) {
      const n = value / size;
      return `$${n >= 100 ? n.toFixed(0) : n.toFixed(1).replace(/\.0$/, "")}${suffix}`;
    }
  }
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

/** Banking table format: $ millions, one decimal. */
export const mm = (v) => (v == null ? null : `$${(v / 1e6).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`);
export const mult = (v) => (v == null ? null : `${Number(v).toFixed(1)}x`);
export const int = (v) => (v == null ? null : Number(v).toLocaleString("en-US"));
export const pct = (v, { signed = true } = {}) => (v == null ? "n.m." : `${signed && v > 0 ? "+" : ""}${Number(v).toFixed(0)}%`);

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11-06" -> "Nov 6, 2026" (calendar date, no timezone shift). */
export function date(iso, { year = true } = {}) {
  if (!iso) return null;
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  if (!y || !m) return iso;
  return `${MONTHS[m - 1]} ${d}${year ? `, ${y}` : ""}`;
}
export const monthLabel = (ym) => {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS[m - 1]} '${String(y).slice(2)}`;
};
/** "2026-Q3" -> "3Q26" (banking style). */
export const quarterLabel = (q) => `${q.slice(-1)}Q${q.slice(2, 4)}`;
export const quarterOf = (iso) => `${iso.slice(0, 4)}-Q${Math.floor((Number(iso.slice(5, 7)) - 1) / 3) + 1}`;

export function relativeTime(isoTimestamp) {
  if (!isoTimestamp) return "";
  const diff = (Date.now() - new Date(isoTimestamp).getTime()) / 1000;
  if (diff < 90) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} hr ago`;
  return `${Math.round(diff / 86400)} days ago`;
}

export const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
