// Shared filter bar (sector, region, deal type, buyer type, category, date range).
// Filter state lives in the URL hash query so every view is shareable.
import { BUYER_TYPES, DEAL_TYPES, FOCUS_SECTORS, REGIONS, v } from "./data.js";
import { esc } from "./format.js";

export const FILTER_KEYS = ["q", "category", "type", "status", "sector", "region", "buyer", "from", "to", "min", "max", "period"];

export function readFilters(params, defaults = {}) {
  const f = { ...defaults };
  for (const k of FILTER_KEYS) if (params.get(k)) f[k] = params.get(k);
  return f;
}

export function writeFilters(view, f, defaults = {}) {
  const params = new URLSearchParams();
  for (const k of FILTER_KEYS) if (f[k] && f[k] !== defaults[k]) params.set(k, f[k]);
  const qs = params.toString();
  history.replaceState(null, "", `#/${view}${qs ? `?${qs}` : ""}`);
}

export function applyFilters(deals, f) {
  const terms = (f.q || "").toLowerCase().split(/\s+/).filter(Boolean);
  const min = f.min ? Number(f.min) * 1e6 : null;
  const max = f.max ? Number(f.max) * 1e6 : null;
  return deals.filter((d) => {
    if (f.category && f.category !== "All" && d.category !== f.category) return false;
    if (f.type && v(d.deal_type) !== f.type) return false;
    if (f.status && v(d.status) !== f.status) return false;
    if (f.sector && d.focus_sector !== f.sector) return false;
    if (f.region && d._region !== f.region) return false;
    if (f.buyer && d._buyerType !== f.buyer) return false;
    if (f.from && d._date < f.from) return false;
    if (f.to && d._date > f.to) return false;
    if (min !== null && (d._value == null || d._value < min)) return false;
    if (max !== null && (d._value == null || d._value > max)) return false;
    return terms.every((t) => d._search.includes(t));
  });
}

const opts = (values, selected, placeholder) =>
  `<option value="">${placeholder}</option>` + values.map((x) => `<option value="${esc(x)}" ${x === selected ? "selected" : ""}>${esc(x)}</option>`).join("");

/** Render the filter controls. `show` picks which controls appear. */
export function filterBar(f, show = ["category", "sector", "region", "type", "buyer", "from", "to"]) {
  const controls = {
    category: `<label class="field">Category<select data-f="category">${opts(["M&A", "Financing"], f.category, "All deals")}</select></label>`,
    sector: `<label class="field">Sector<select data-f="sector">${opts(FOCUS_SECTORS, f.sector, "All sectors")}</select></label>`,
    region: `<label class="field">Region<select data-f="region">${opts(REGIONS, f.region, "All regions")}</select></label>`,
    type: `<label class="field">Deal type<select data-f="type">${opts(DEAL_TYPES, f.type, "All types")}</select></label>`,
    status: `<label class="field">Status<select data-f="status">${opts(["Rumored", "Announced", "Pending", "Closed", "Terminated"], f.status, "All statuses")}</select></label>`,
    buyer: `<label class="field">Buyer type<select data-f="buyer">${opts(BUYER_TYPES, f.buyer, "All buyers")}</select></label>`,
    from: `<label class="field">From<input type="date" data-f="from" value="${esc(f.from || "")}"></label>`,
    to: `<label class="field">To<input type="date" data-f="to" value="${esc(f.to || "")}"></label>`,
    min: `<label class="field">Min value ($M)<input type="number" inputmode="decimal" min="0" step="any" data-f="min" placeholder="0" value="${esc(f.min || "")}"></label>`,
    max: `<label class="field">Max value ($M)<input type="number" inputmode="decimal" min="0" step="any" data-f="max" placeholder="Any" value="${esc(f.max || "")}"></label>`,
  };
  return `<div class="filter-grid">${show.map((k) => controls[k]).join("")}</div>`;
}

export function bindFilters(root, f, onChange) {
  root.querySelectorAll("[data-f]").forEach((el) =>
    el.addEventListener("change", () => {
      f[el.dataset.f] = el.value;
      onChange();
    }),
  );
}

export function periodToggle(period) {
  return `<div class="seg" role="group" aria-label="Period">${["month", "quarter", "year"]
    .map((p) => `<button type="button" data-period="${p}" aria-pressed="${p === period}">${p[0].toUpperCase() + p.slice(1)}</button>`)
    .join("")}</div>`;
}
