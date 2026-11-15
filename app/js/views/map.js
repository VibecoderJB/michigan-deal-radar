// Michigan county choropleth of deal activity (Census county boundaries, pre-projected SVG).
import { loadCounties, loadDeals, REGIONS } from "../data.js";
import { applyFilters, bindFilters, filterBar, readFilters, writeFilters } from "../filters.js";
import { esc } from "../format.js";
import { dealItem, emptyState, pageHead, SOURCE_NOTE } from "../ui.js";

const SCALE = ["#e8edf5", "#c3cfe2", "#8fa6c9", "#5a7aa8", "#2f5384", "#0b1f3a"];

export async function renderMap(root, params) {
  const [{ deals }, geo] = await Promise.all([loadDeals(), loadCounties()]);
  const f = readFilters(params, {});
  let selected = params.get("county") || null;

  root.innerHTML = `
    ${pageHead("County Map", "Deal activity by the Michigan party's county (target, else acquirer). Click a county for its deals.")}
    <section class="card filters">${filterBar(f, ["category", "type", "sector", "buyer", "from", "to"])}</section>
    <div class="grid-2">
      <section class="card">
        <div class="card-head"><h2>Michigan deal activity by county</h2><span class="sub">number of deals</span></div>
        <div class="map-wrap" id="map"></div>
        <div class="legend" id="legend"></div>
        <div class="chart-note">Boundaries: U.S. Census Bureau cartographic files. City to county mapped by point-in-polygon. ${SOURCE_NOTE}</div>
      </section>
      <div class="stack">
        <section class="card"><div class="card-head"><h2 id="sel-title">Top counties</h2></div><div id="sel-body"></div></section>
        <section class="card"><div class="card-head"><h2>By region</h2><span class="sub">deal count</span></div><div id="regions"></div></section>
      </div>
    </div>`;

  function render() {
    writeFilters("map", f);
    const pool = applyFilters(deals, f);
    const counts = new Map();
    for (const d of pool) if (d._county) counts.set(d._county, (counts.get(d._county) || 0) + 1);
    const max = Math.max(1, ...counts.values());
    const bucket = (n) => (n ? Math.min(SCALE.length - 1, 1 + Math.floor(((SCALE.length - 2) * Math.log(n)) / Math.log(max + 1))) : 0);
    const [x, y, w, h] = geo.viewBox;
    root.querySelector("#map").innerHTML = `<svg viewBox="${x} ${y} ${w} ${h}" role="img" aria-label="Choropleth map of Michigan deals by county">
      <title>Michigan deals by county</title>
      ${geo.counties.map((c) => {
        const name = `${c.name} County`;
        const n = counts.get(name) || 0;
        return `<path d="${c.d}" fill="${SCALE[bucket(n)]}" data-county="${esc(name)}" class="${selected === name ? "sel" : ""}"><title>${esc(name)}: ${n} deal${n === 1 ? "" : "s"}</title></path>`;
      }).join("")}</svg>`;
    root.querySelector("#legend").innerHTML = `<span>Fewer</span>${SCALE.map((c) => `<span class="sw" style="background:${c}"></span>`).join("")}<span>More (max ${max})</span>`;

    const regions = new Map(REGIONS.map((r) => [r, 0]));
    for (const d of pool) if (d._region) regions.set(d._region, (regions.get(d._region) || 0) + 1);
    const rmax = Math.max(1, ...regions.values());
    root.querySelector("#regions").innerHTML = `<div class="bars">${[...regions].sort((a, b) => b[1] - a[1]).map(([r, n]) =>
      `<a class="bar-row" href="#/deals?region=${encodeURIComponent(r)}"><span class="bar-label">${esc(r)}</span><span class="bar-track"><span class="bar-fill" style="width:${(n / rmax) * 100}%"></span></span><span class="bar-val">${n}</span></a>`).join("")}</div>`;

    const title = root.querySelector("#sel-title");
    const body = root.querySelector("#sel-body");
    if (selected) {
      const list = pool.filter((d) => d._county === selected).sort((a, b) => b._date.localeCompare(a._date));
      title.textContent = `${selected} (${list.length})`;
      body.innerHTML = list.length ? list.slice(0, 12).map(dealItem).join("") + (list.length > 12 ? `<p class="small muted">Showing 12 of ${list.length}.</p>` : "") : emptyState("No deals in this county for these filters.");
    } else {
      title.textContent = "Top counties";
      const top = [...counts].sort((a, b) => b[1] - a[1]).slice(0, 12);
      body.innerHTML = top.length ? `<div class="bars">${top.map(([c, n]) => `<a class="bar-row" href="#" data-pick="${esc(c)}"><span class="bar-label">${esc(c)}</span><span class="bar-track"><span class="bar-fill" style="width:${(n / max) * 100}%"></span></span><span class="bar-val">${n}</span></a>`).join("")}</div>` : emptyState("No deals for these filters.");
    }
  }

  root.addEventListener("click", (e) => {
    const target = e.target.closest("[data-county],[data-pick]");
    if (!target) return;
    e.preventDefault();
    const c = target.dataset.county || target.dataset.pick;
    selected = selected === c ? null : c;
    render();
  });
  bindFilters(root, f, render);
  render();
}
