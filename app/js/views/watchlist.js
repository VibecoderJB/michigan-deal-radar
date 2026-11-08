// Watchlist: starred companies (stored on this device) and their filings.
import { loadDeals } from "../data.js";
import { date, esc, isoDay, money } from "../format.js";
import { dealItem, emptyState } from "../ui.js";
import { starButton, watchlist } from "../watchlist.js";

export async function renderWatchlist(root) {
  const { deals } = await loadDeals();
  const starred = watchlist.all();
  const ciks = Object.keys(starred);
  const lastSeen = watchlist.lastSeen();

  if (!ciks.length) {
    root.innerHTML = `
      <div class="page-head"><div><h1>Watchlist</h1><p>Star companies to follow their filings. Saved privately on this device.</p></div></div>
      <section class="card">${emptyState(
        `No companies yet. Tap the <strong>☆ star</strong> on any deal to watch that company.<br><br><a class="btn btn-accent" href="#/deals">Browse deals</a>`,
        "M12 17.3l-6.2 3.7 1.7-7L2 9.2l7.2-.6L12 2l2.8 6.6 7.2.6-5.5 4.8 1.7 7z",
      )}</section>`;
    return;
  }

  const groups = ciks
    .map((cik) => {
      const list = deals.filter((d) => d.cik === cik);
      return { cik, name: list[0]?.company || starred[cik].name, list, latest: list[0]?.filed || "" };
    })
    .sort((a, b) => b.latest.localeCompare(a.latest));
  const fresh = lastSeen ? deals.filter((d) => starred[d.cik] && d.filed > lastSeen) : [];

  root.innerHTML = `
    <div class="page-head">
      <div><h1>Watchlist</h1><p>${ciks.length} compan${ciks.length === 1 ? "y" : "ies"} · saved on this device only.</p></div>
    </div>
    ${fresh.length ? `<section class="card" style="border-color:var(--accent)"><div class="card-head"><h2>New since your last visit</h2><span class="mono small">${fresh.length}</span></div><div class="deal-list">${fresh.map((d) => dealItem(d)).join("")}</div></section><div class="section-gap"></div>` : ""}
    <div class="stack">
      ${groups
        .map(
          (g) => `<section class="card">
            <div class="card-head">
              <div style="min-width:0"><h2>${esc(g.name)}</h2><div class="muted small mono">${g.list.length} filing${g.list.length === 1 ? "" : "s"} · last ${date(g.latest)} · ${money(g.list.reduce((s, d) => s + (d.amount_sold || 0), 0), { empty: "$0" })} sold</div></div>
              ${starButton(g.cik, g.name)}
            </div>
            <div class="deal-list">${g.list.length ? g.list.slice(0, 4).map((d) => dealItem(d)).join("") : emptyState("No filings in the current dataset.")}</div>
          </section>`,
        )
        .join("")}
    </div>`;

  watchlist.markSeen(isoDay(new Date()));
}
