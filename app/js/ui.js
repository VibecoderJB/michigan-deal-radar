// Small shared UI components.
import { badge, date, esc, money } from "./format.js";

export function dealItem(d) {
  const amount = d.amount ?? d.amount_sold;
  return `
    <a class="deal-item" href="#/deal/${encodeURIComponent(d.id)}">
      <span class="deal-co">${esc(d.company)}${d.ticker ? ` <span class="muted mono small">${esc(d.ticker)}</span>` : ""}</span>
      <span class="deal-amt">${money(amount, { estimate: d.amount_is_estimate })}</span>
      <span class="deal-meta">${badge(d.type)}<span>${esc(d.subtype || "")}</span><span>·</span><span>${esc(d.city || "Michigan")}</span><span>·</span><span class="mono">${date(d.filed, { year: false })}</span></span>
      <span class="deal-sum">${esc(d.summary)}</span>
    </a>`;
}

export function emptyState(message, icon = "M12 2a10 10 0 100 20 10 10 0 000-20zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z") {
  return `<div class="empty"><svg viewBox="0 0 24 24"><path d="${icon}"/></svg><p>${message}</p></div>`;
}

/** Horizontal bar list (used for counts by type and sector). */
export function barRows(rows, { format = (v) => v, href = null, dim = false } = {}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return `<div class="bars">${rows
    .map((r) => {
      const tag = href ? "a" : "div";
      const link = href ? ` href="${href(r)}"` : "";
      const width = ((r.value / max) * 100).toFixed(1);
      return `<${tag} class="bar-row"${link}><span class="bar-label">${esc(r.label)}</span><span class="bar-track"><span class="bar-fill ${dim ? "dim" : ""}" style="width:${width}%"></span></span><span class="bar-val">${format(r.value)}</span></${tag}>`;
    })
    .join("")}</div>`;
}

export function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2200);
}

export const spinner = () => `<div class="spinner" role="progressbar" aria-label="Loading"></div>`;
