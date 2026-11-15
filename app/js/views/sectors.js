// Sector trends: quarter-over-quarter and year-over-year deal counts by Michigan focus sector.
import { periodBuckets } from "../analytics.js";
import { FOCUS_SECTORS, loadDeals } from "../data.js";
import { applyFilters, bindFilters, filterBar, readFilters, writeFilters } from "../filters.js";
import { esc, pct, quarterLabel, quarterOf } from "../format.js";
import { chartBox, drawChart, pageHead } from "../ui.js";

const PALETTE = ["#0b1f3a", "#c8962e", "#2f5384", "#7a8fae", "#1e7b4f", "#8a5a9e", "#b33a3a", "#5aa0a0", "#9c8a5a"];

export async function renderSectors(root, params) {
  const { deals } = await loadDeals();
  const f = readFilters(params, { category: "" });

  root.innerHTML = `
    ${pageHead("Sector Trends", "Deal counts by Michigan focus sector, mapped from SEC SIC codes and Form D industry groups to GICS.")}
    <section class="card filters">${filterBar(f, ["category", "type", "region", "buyer"])}</section>
    <section class="card">${chartBox("sector-chart", "Lines: deals per quarter for each focus sector.")}</section>
    <section class="card section-gap"><div class="card-head"><h2>Quarter-over-quarter and year-over-year</h2><span class="sub" id="qnote"></span></div>
      <div class="table-wrap"><table class="data"><thead><tr><th>Sector</th><th class="r" id="h-cur"></th><th class="r">Prior qtr</th><th class="r">QoQ</th><th class="r">Year-ago qtr</th><th class="r">YoY</th><th class="r">Trailing 4Q</th></tr></thead><tbody id="rows"></tbody></table></div>
      <p class="small muted" style="margin-top:8px">Latest <b>completed</b> quarter vs. the prior quarter and the same quarter a year earlier. n.m. = not meaningful (zero base).</p>
    </section>`;

  function render() {
    writeFilters("sectors", f, { category: "" });
    const pool = applyFilters(deals, f);
    const buckets = periodBuckets("quarter", 9).slice(0, 8); // completed quarters only
    const counts = new Map(FOCUS_SECTORS.map((s) => [s, Object.fromEntries(buckets.map((b) => [b, 0]))]));
    for (const d of pool) {
      if (!d._date || !counts.has(d.focus_sector)) continue;
      const q = quarterOf(d._date);
      if (q in counts.get(d.focus_sector)) counts.get(d.focus_sector)[q] += 1;
    }
    const cur = buckets.at(-1), prev = buckets.at(-2), ya = buckets.at(-5);
    root.querySelector("#h-cur").textContent = quarterLabel(cur);
    root.querySelector("#qnote").textContent = `${quarterLabel(cur)} vs ${quarterLabel(prev)} and ${quarterLabel(ya)}`;
    const change = (a, b) => (b ? ((a - b) / b) * 100 : null);
    root.querySelector("#rows").innerHTML = FOCUS_SECTORS.map((s) => {
      const c = counts.get(s);
      const qoq = change(c[cur], c[prev]), yoy = change(c[cur], c[ya]);
      const cls = (x) => (x == null ? "" : x >= 0 ? "delta-up" : "delta-down");
      return `<tr><td class="name"><a href="#/deals?sector=${encodeURIComponent(s)}">${esc(s)}</a></td><td class="r num">${c[cur]}</td><td class="r num">${c[prev]}</td>
        <td class="r num ${cls(qoq)}">${pct(qoq)}</td><td class="r num">${c[ya]}</td><td class="r num ${cls(yoy)}">${pct(yoy)}</td><td class="r num">${buckets.slice(-4).reduce((t, q) => t + c[q], 0)}</td></tr>`;
    }).join("");
    drawChart("sector-chart", {
      type: "line",
      title: "Michigan deals by focus sector, last 8 completed quarters",
      xTitle: "Quarter (announcement date)",
      yTitle: "Deals (count)",
      labels: buckets.map(quarterLabel),
      datasets: FOCUS_SECTORS.map((s, i) => ({ label: s, data: buckets.map((b) => counts.get(s)[b]), borderColor: PALETTE[i], backgroundColor: PALETTE[i], tension: 0.25, pointRadius: 2, borderWidth: 2 })),
    });
  }
  bindFilters(root, f, render);
  render();
}
