// Watchlist: starred companies and their deals (saved on this device only).
import { loadDeals } from "../data.js";
import { isoDay } from "../format.js";
import { dealItem, emptyState, pageHead } from "../ui.js";
import { companyKey, starButton, watchlist } from "../watchlist.js";

export async function renderWatchlist(root) {
  const { deals } = await loadDeals();
  const items = watchlist.all();
  const lastSeen = watchlist.lastSeen();
  const matched = deals.filter((d) => watchlist.matches(d));

  if (!Object.keys(items).length) {
    root.innerHTML = `${pageHead("Watchlist", "Star companies to follow their deals. Saved privately on this device.")}
      <section class="card">${emptyState('No companies yet. Tap the ☆ star on any deal to watch that company.<br><br><a class="btn btn-primary" href="#/deals">Browse deals</a>')}</section>`;
    return;
  }
  const groups = new Map();
  for (const d of matched) {
    const { key, name } = companyKey(d);
    if (!groups.has(key)) groups.set(key, { name, list: [], sample: d });
    groups.get(key).list.push(d);
  }
  const fresh = lastSeen ? matched.filter((d) => d._date > lastSeen) : [];
  root.innerHTML = `
    ${pageHead("Watchlist", `${Object.keys(items).length} compan${Object.keys(items).length === 1 ? "y" : "ies"} · saved on this device only.`)}
    ${fresh.length ? `<section class="card" style="border-color:var(--accent)"><div class="card-head"><h2>New since your last visit</h2><span class="sub">${fresh.length}</span></div>${fresh.map(dealItem).join("")}</section><div class="section-gap"></div>` : ""}
    <div class="stack">${[...groups.values()].map((g) => `<section class="card"><div class="card-head"><h2>${g.name}</h2>${starButton(g.sample)}</div>${g.list.slice(0, 5).map(dealItem).join("")}</section>`).join("") || emptyState("Your starred companies have no deals in the current dataset.")}</div>`;
  watchlist.markSeen(isoDay(new Date()));
}
