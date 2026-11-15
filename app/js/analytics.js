// Client-side analytics over filtered deals. Mirrors pipeline/analytics/metrics.py so the
// dashboard, PDFs and README report identical numbers for the same filters.
import { dealDate, disclosedValue, isFinancing, isMA, raised, v } from "./data.js";
import { quarterOf } from "./format.js";

export const periodKey = {
  month: (iso) => iso.slice(0, 7),
  quarter: quarterOf,
  year: (iso) => iso.slice(0, 4),
};

/** Buckets for the last N periods (inclusive of the current one), oldest first. */
export function periodBuckets(period, n, today = new Date()) {
  const out = [];
  if (period === "year") {
    for (let i = n - 1; i >= 0; i--) out.push(String(today.getFullYear() - i));
  } else if (period === "quarter") {
    let y = today.getFullYear();
    let q = Math.floor(today.getMonth() / 3) + 1;
    for (let i = 0; i < n; i++) {
      out.unshift(`${y}-Q${q}`);
      q -= 1;
      if (q === 0) { q = 4; y -= 1; }
    }
  } else {
    for (let i = n - 1; i >= 0; i--) {
      const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
      out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
    }
  }
  return out;
}

export function series(deals, period, buckets) {
  const rows = Object.fromEntries(buckets.map((b) => [b, { count: 0, value: 0, disclosed: 0, maCount: 0, finCount: 0, raised: 0 }]));
  for (const d of deals) {
    const dt = dealDate(d);
    if (!dt) continue;
    const r = rows[periodKey[period](dt)];
    if (!r) continue;
    r.count += 1;
    if (isMA(d)) {
      r.maCount += 1;
      const val = disclosedValue(d);
      if (val) { r.value += val; r.disclosed += 1; }
    } else if (isFinancing(d)) {
      r.finCount += 1;
      r.raised += raised(d) || 0;
    }
  }
  return buckets.map((b) => ({ period: b, ...rows[b] }));
}

const canonical = (name) => (name || "").replace(/\s+/g, " ").replace(/[,.]+$/, "").trim();

export function leagueTables(deals, top = 15) {
  const tally = () => new Map();
  const add = (m, name, d) => {
    if (!name) return;
    const key = canonical(name);
    const row = m.get(key) || { name: key, deals: 0, value: 0, ids: [] };
    row.deals += 1;
    row.value += disclosedValue(d) || 0;
    row.ids.push(d.deal_id);
    m.set(key, row);
  };
  const acquirers = tally(), sponsors = tally(), fin = tally(), legal = tally(), lenders = tally();
  for (const d of deals) {
    if (!isMA(d)) continue;
    const formD = (d.sources || []).some((s) => s.kind === "SEC Form D");
    if (!formD) add(acquirers, v(d.acquirer?.name), d);
    if (v(d.acquirer?.sponsor)) add(sponsors, v(d.acquirer.sponsor), d);
    else if (v(d.acquirer?.type) === "Financial Sponsor") add(sponsors, v(d.acquirer?.name), d);
    for (const a of d.advisors || []) add(a.role === "financial" ? fin : a.role === "legal" ? legal : lenders, a.firm, d);
  }
  const rank = (m) => [...m.values()].sort((a, b) => b.deals - a.deals || b.value - a.value || a.name.localeCompare(b.name)).slice(0, top);
  return { acquirers: rank(acquirers), sponsors: rank(sponsors), financial: rank(fin), legal: rank(legal), lenders: rank(lenders) };
}

export function stats(values) {
  const xs = values.filter((x) => x != null && !Number.isNaN(x)).sort((a, b) => a - b);
  if (!xs.length) return { n: 0, median: null, mean: null, low: null, high: null };
  const mid = Math.floor(xs.length / 2);
  return {
    n: xs.length,
    median: xs.length % 2 ? xs[mid] : (xs[mid - 1] + xs[mid]) / 2,
    mean: xs.reduce((s, x) => s + x, 0) / xs.length,
    low: xs[0],
    high: xs[xs.length - 1],
  };
}

export function precedents(deals) {
  return deals
    .filter((d) => isMA(d) && (disclosedValue(d) || v(d.financials?.ev_ebitda) || v(d.financials?.ev_revenue)))
    .sort((a, b) => dealDate(b).localeCompare(dealDate(a)));
}

export function countBy(items, fn) {
  const m = new Map();
  for (const it of items) {
    const k = fn(it);
    if (k == null) continue;
    m.set(k, (m.get(k) || 0) + 1);
  }
  return m;
}
