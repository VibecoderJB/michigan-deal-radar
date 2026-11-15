// Data access for the static JSON produced by the pipeline (schema v2).
// The service worker serves the last saved copy when offline and flags it with a header.

const cache = new Map();
export const status = { offline: false, generatedAt: null, asOf: null };

async function getJSON(path, { optional = false } = {}) {
  if (cache.has(path)) return cache.get(path);
  const promise = fetch(path, { cache: "no-cache" })
    .then((res) => {
      if (!res.ok) {
        if (optional) return null;
        throw new Error(`${res.status} loading ${path}`);
      }
      if (res.headers.get("x-mdr-offline") === "1") status.offline = true;
      return res.json();
    })
    .catch((err) => {
      cache.delete(path);
      if (optional) return null;
      throw err;
    });
  cache.set(path, promise);
  return promise;
}

/** Field helpers: every datum is {value, source_url, source_text, method, estimate?, note?}. */
export const v = (f) => (f && f.value !== undefined ? f.value : null);
export const disclosed = (f) => v(f) !== null && v(f) !== undefined;

export const dealDate = (d) => (v(d.announcement_date) || "").slice(0, 10);
export const disclosedValue = (d) => {
  const f = d.financials || {};
  return v(f.enterprise_value) ?? v(f.transaction_value) ?? v(f.equity_value);
};
export const raised = (d) => v((d.financials || {}).amount_raised);
export const MA_TYPES = new Set(["Acquisition", "Merger", "PE Buyout", "Add-on", "Divestiture / Carve-out", "Recapitalization"]);
export const isMA = (d) => d.category === "M&A" && MA_TYPES.has(v(d.deal_type));
export const isFinancing = (d) => d.category === "Financing";
export const headlineValue = (d) => (isMA(d) ? disclosedValue(d) : raised(d));

/** Michigan party for geography/sector (target, else acquirer, else filer). */
export function miParty(d) {
  for (const role of ["target", "acquirer", "michigan_party"]) {
    const p = d[role];
    if (p && v(p.state) === "MI") return p;
  }
  return d.target || d.michigan_party || {};
}
export const partyName = (p) => (p ? v(p.name) : null);
export const ciksOf = (d) => [d.target?.cik, d.acquirer?.cik, d.michigan_party?.cik, d.seller?.cik].filter(Boolean);

let dealsPromise;
export function loadDeals() {
  dealsPromise ??= getJSON("data/deals.json").then((payload) => {
    status.generatedAt = payload.generated_at;
    const deals = payload.deals.map((d) => {
      const mp = miParty(d);
      return {
        ...d,
        _date: dealDate(d),
        _value: headlineValue(d),
        _county: v(mp.county),
        _region: v(mp.region),
        _buyerType: v(d.acquirer?.type),
        _search: [d.title, partyName(d.target), partyName(d.acquirer), partyName(d.michigan_party), v(d.target?.city), v(mp.county), d.focus_sector,
          v(d.deal_type), ...(d.advisors || []).map((a) => a.firm), v(d.acquirer?.sponsor)].filter(Boolean).join(" ").toLowerCase(),
      };
    });
    const byId = new Map();
    for (const d of deals) {
      byId.set(d.deal_id, d);
      for (const legacy of d.legacy_ids || []) if (!byId.has(legacy)) byId.set(legacy, d);
    }
    return { deals, byId, generatedAt: payload.generated_at };
  });
  return dealsPromise;
}

export const loadMeta = () => getJSON("data/meta.json");
export const loadAnalytics = () => getJSON("data/analytics.json", { optional: true });
export const loadCapitalFormation = () => getJSON("data/capital_formation.json", { optional: true }).then((p) => p?.records || []);
export const loadOwnership = () => getJSON("data/ownership.json", { optional: true }).then((p) => p?.records || []);
export const loadQuality = () => getJSON("data/quality/latest.json", { optional: true });
export const loadBriefingIndex = () => getJSON("data/briefings/index.json", { optional: true }).then((p) => p || { weeks: [] });
export const loadBriefing = (week) => getJSON(`data/briefings/${week}.json`);
export const loadReports = () => getJSON("reports/index.json", { optional: true });
export const loadCounties = () => getJSON("assets/mi-counties.json");

export const DEAL_TYPES = ["Acquisition", "Merger", "PE Buyout", "Add-on", "Growth Equity", "Venture Round", "Recapitalization", "Divestiture / Carve-out", "IPO", "Debt Raise"];
export const STATUSES = ["Rumored", "Announced", "Pending", "Closed", "Terminated"];
export const FOCUS_SECTORS = ["Automotive & Mobility", "Advanced Manufacturing", "Healthcare", "Software & Technology", "Consumer", "Business Services", "Financial Services", "Real Estate", "Energy & Utilities"];
export const REGIONS = ["Southeast Michigan", "West Michigan", "Southwest Michigan", "Mid-Michigan", "East Michigan & Thumb", "Northern Michigan", "Upper Peninsula"];
export const BUYER_TYPES = ["Strategic", "Financial Sponsor", "Family Office"];
