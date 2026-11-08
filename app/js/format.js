// Formatting + escaping helpers shared by every view.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape untrusted text (all SEC data) before inserting into HTML. */
export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);

/** Compact currency: 1250000 -> "$1.3M". */
export function money(value, { empty = "—", estimate = false } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return empty;
  const abs = Math.abs(value);
  const units = [[1e9, "B"], [1e6, "M"], [1e3, "K"]];
  let out = `$${Math.round(value).toLocaleString("en-US")}`;
  for (const [size, suffix] of units) {
    if (abs >= size) {
      const n = value / size;
      out = `$${n >= 100 ? n.toFixed(0) : n.toFixed(1).replace(/\.0$/, "")}${suffix}`;
      break;
    }
  }
  return estimate ? `~${out}` : out;
}

export const fullMoney = (v) => (v == null ? "—" : `$${Math.round(v).toLocaleString("en-US")}`);
export const num = (v) => (v == null ? "—" : Number(v).toLocaleString("en-US"));

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11-06" -> "Nov 6, 2026" (parsed as a calendar date, no timezone shift). */
export function date(iso, { year = true } = {}) {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m) return iso;
  return `${MONTHS[m - 1]} ${d}${year ? `, ${y}` : ""}`;
}

export const monthLabel = (ym) => {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS[m - 1]} '${String(y).slice(2)}`;
};

export function relativeTime(isoTimestamp) {
  if (!isoTimestamp) return "";
  const diff = (Date.now() - new Date(isoTimestamp).getTime()) / 1000;
  if (diff < 90) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} hr ago`;
  return `${Math.round(diff / 86400)} days ago`;
}

/** ISO date string (YYYY-MM-DD) for a Date in local time. */
export const isoDay = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export const typeClass = (type) => `badge badge-${String(type).replace(/[^A-Za-z]/g, "")}`;
export const badge = (type) => `<span class="${typeClass(type)}">${esc(type)}</span>`;
