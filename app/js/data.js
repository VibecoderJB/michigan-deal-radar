// Data access: fetch the static JSON produced by the pipeline.
// The service worker serves the last saved copy when offline and flags it with a header.

const DATA_ROOT = "data";
const cache = new Map();
export const status = { offline: false, generatedAt: null };

async function getJSON(path) {
  if (cache.has(path)) return cache.get(path);
  const promise = fetch(`${DATA_ROOT}/${path}`, { cache: "no-cache" })
    .then((res) => {
      if (!res.ok) throw new Error(`${res.status} loading ${path}`);
      if (res.headers.get("x-mdr-offline") === "1") status.offline = true;
      return res.json();
    })
    .catch((err) => {
      cache.delete(path);
      throw err;
    });
  cache.set(path, promise);
  return promise;
}

let dealsPromise;

/** All deals, newest first, with a lowercase search blob for the table filter. */
export function loadDeals() {
  dealsPromise ??= getJSON("deals.json").then((payload) => {
    status.generatedAt = payload.generated_at;
    const deals = payload.deals.map((d) => ({
      ...d,
      _search: [d.company, d.ticker, d.city, d.industry, d.sector, d.subtype, d.counterparty, d.summary, d.form]
        .filter(Boolean)
        .join(" ")
        .toLowerCase(),
    }));
    return { deals, byId: new Map(deals.map((d) => [d.id, d])), generatedAt: payload.generated_at };
  });
  return dealsPromise;
}

export const loadMeta = () => getJSON("meta.json");
export const loadBriefingIndex = () => getJSON("briefings/index.json");
export const loadBriefing = (weekStart) => getJSON(`briefings/${weekStart}.json`);

export const DEAL_TYPES = ["Fundraise", "M&A", "Material Agreement", "Stake"];
