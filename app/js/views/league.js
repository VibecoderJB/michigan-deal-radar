// League tables: most active acquirers, PE sponsors, financial/legal advisors and lenders on Michigan deals.
import { leagueTables } from "../analytics.js";
import { loadDeals } from "../data.js";
import { applyFilters, bindFilters, filterBar, readFilters, writeFilters } from "../filters.js";
import { addDays, esc, isoDay, money } from "../format.js";
import { emptyState, pageHead } from "../ui.js";

const WINDOWS = { "12m": 365, "24m": 730, all: null };

function table(title, rows, note) {
  return `<section class="card"><div class="card-head"><h2>${title}</h2><span class="sub">${note}</span></div>
    ${rows.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>#</th><th>Firm</th><th class="r">Deals</th><th class="r">Disclosed value</th><th>Recent deals</th></tr></thead><tbody>
    ${rows.map((r, i) => `<tr><td class="num">${i + 1}</td><td class="name">${esc(r.name)}</td><td class="r num">${r.deals}</td><td class="r num">${r.value ? money(r.value) : '<span class="nd">n.d.</span>'}</td>
      <td>${r.ids.slice(0, 3).map((id, j) => `<a href="#/deal/${encodeURIComponent(id)}">${j + 1}</a>`).join(" · ")}</td></tr>`).join("")}
    </tbody></table></div>` : emptyState("None disclosed in sources for this window.")}</section>`;
}

export async function renderLeague(root, params) {
  const { deals } = await loadDeals();
  const f = readFilters(params, {});
  let win = params.get("window") || "24m";

  root.innerHTML = `
    ${pageHead("League Tables", "Most active acquirers, PE sponsors and advisors on Michigan M&amp;A, ranked by deal count (ties broken by disclosed value).",
      `<div class="seg" role="group" aria-label="Window">${Object.keys(WINDOWS).map((k) => `<button type="button" data-win="${k}" aria-pressed="${k === win}">${k === "all" ? "All" : k.toUpperCase()}</button>`).join("")}</div>`)}
    <section class="card filters">${filterBar(f, ["sector", "region", "type", "buyer"])}</section>
    <div class="grid-2 even" id="tables"></div>
    <p class="small muted section-gap">Advisors appear only when named in an SEC filing or press release (e.g. "X is serving as financial advisor"). Form D business-combination notices don't name targets, so they're excluded from the acquirer table.</p>`;

  function render() {
    writeFilters("league", f);
    let pool = applyFilters(deals, f);
    if (WINDOWS[win]) pool = pool.filter((d) => d._date >= isoDay(addDays(new Date(), -WINDOWS[win])));
    const lt = leagueTables(pool);
    const note = `${win === "all" ? "all dates" : `trailing ${win}`}`;
    root.querySelector("#tables").innerHTML = [
      table("Most active acquirers", lt.acquirers, note),
      table("Most active PE sponsors", lt.sponsors, note),
      table("Financial advisors", lt.financial, note),
      table("Legal advisors", lt.legal, note),
      table("Lenders / arrangers", lt.lenders, note),
    ].join("");
  }
  root.querySelectorAll("[data-win]").forEach((b) => b.addEventListener("click", () => {
    win = b.dataset.win;
    root.querySelectorAll("[data-win]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    render();
  }));
  bindFilters(root, f, render);
  render();
}
