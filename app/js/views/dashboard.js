// Deal Flow dashboard: count and disclosed value by month/quarter/year, filterable.
import { periodBuckets, series } from "../analytics.js";
import { isFinancing, isMA, loadBriefingIndex, loadDeals, v } from "../data.js";
import { applyFilters, bindFilters, filterBar, periodToggle, readFilters, writeFilters } from "../filters.js";
import { addDays, date, esc, isoDay, money, monthLabel, quarterLabel } from "../format.js";
import { barRows, chartBox, dealItem, drawChart, emptyState, pageHead } from "../ui.js";

const DEFAULTS = { period: "quarter" };
const N_PERIODS = { month: 24, quarter: 8, year: 3 };

export async function renderDashboard(root, params) {
  const [{ deals }, index] = await Promise.all([loadDeals(), loadBriefingIndex()]);
  const f = readFilters(params, DEFAULTS);

  root.innerHTML = `
    ${pageHead("Michigan Deal Flow", "M&amp;A and private capital activity involving Michigan companies, sourced from SEC filings and public press releases.")}
    <section class="card filters" aria-label="Filters">
      <div class="card-head"><h2>Filters</h2>${periodToggle(f.period)}</div>
      ${filterBar(f)}
    </section>
    <div id="dash-body"></div>`;

  const body = root.querySelector("#dash-body");

  function render() {
    writeFilters("dashboard", f, DEFAULTS);
    const pool = applyFilters(deals, f);
    const today = new Date();
    const yearAgo = isoDay(addDays(today, -365));
    const last12 = pool.filter((d) => d._date >= yearAgo);
    const ma12 = last12.filter(isMA);
    const fin12 = last12.filter(isFinancing);
    const valued = ma12.filter((d) => d._value);
    const sponsorDeals = ma12.filter((d) => ["PE Buyout", "Add-on"].includes(v(d.deal_type)));
    const closed = ma12.filter((d) => v(d.status) === "Closed").length;
    const latest = index.weeks?.[0];

    const buckets = periodBuckets(f.period, N_PERIODS[f.period]);
    const rows = series(pool, f.period, buckets);
    const label = f.period === "month" ? monthLabel : f.period === "quarter" ? quarterLabel : (x) => x;

    const sectorCounts = new Map();
    for (const d of last12) if (d.focus_sector) sectorCounts.set(d.focus_sector, (sectorCounts.get(d.focus_sector) || 0) + 1);
    const recent = [...pool].sort((a, b) => b._date.localeCompare(a._date)).slice(0, 8);
    const biggest = [...ma12].filter((d) => d._value).sort((a, b) => b._value - a._value).slice(0, 5);

    body.innerHTML = `
      <section class="kpis" aria-label="Key figures, last 12 months">
        <div class="kpi accent"><div class="label">M&amp;A deals · LTM</div><div class="value">${ma12.length}</div><div class="sub">${closed} closed</div></div>
        <div class="kpi"><div class="label">Disclosed M&amp;A value · LTM</div><div class="value">${money(valued.reduce((s, d) => s + d._value, 0), { empty: "$0" })}</div><div class="sub">${valued.length} of ${ma12.length} disclosed</div></div>
        <div class="kpi"><div class="label">Private financings · LTM</div><div class="value">${fin12.length}</div><div class="sub">${money(fin12.reduce((s, d) => s + (d._value || 0), 0), { empty: "$0" })} raised</div></div>
        <div class="kpi"><div class="label">Sponsor deals · LTM</div><div class="value">${sponsorDeals.length}</div><div class="sub">PE buyouts + add-ons</div></div>
        <div class="kpi"><div class="label">Deals in view</div><div class="value">${pool.length}</div><div class="sub">all dates, current filters</div></div>
        <div class="kpi"><div class="label">High confidence</div><div class="value">${pool.length ? Math.round((pool.filter((d) => d.confidence === "High").length / pool.length) * 100) : 0}%</div><div class="sub">SEC or official release</div></div>
      </section>

      <section class="card">
        ${chartBox("flow-chart", "Bars: number of deals (M&A + financings). Line: disclosed M&A value; undisclosed deals add to counts only.")}
      </section>

      <div class="grid-2 section-gap">
        <section class="card">
          <div class="card-head"><h2>Latest deals</h2><a href="#/deals">All deals →</a></div>
          <div>${recent.length ? recent.map(dealItem).join("") : emptyState("No deals match these filters.")}</div>
        </section>
        <div class="stack">
          <section class="card">
            <div class="card-head"><h2>Latest weekly brief</h2><a href="#/briefing">Reports →</a></div>
            ${latest ? `<div class="upper">Week of ${date(latest.week_start)}</div><p style="margin:4px 0 6px;font-weight:600">${esc(latest.headline)}</p><div class="mono small muted">${latest.ma_deals} M&amp;A · ${latest.financings} financings · ${money(latest.financing_raised, { empty: "$0" })} raised</div>` : emptyState("The first briefing publishes on Monday.")}
          </section>
          <section class="card">
            <div class="card-head"><h2>Activity by sector</h2><span class="sub">LTM, deal count</span></div>
            ${barRows([...sectorCounts].sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value })), { href: (r) => `#/deals?sector=${encodeURIComponent(r.label)}` })}
          </section>
          <section class="card">
            <div class="card-head"><h2>Largest disclosed M&amp;A</h2><span class="sub">LTM</span></div>
            ${biggest.length ? biggest.map(dealItem).join("") : emptyState("No disclosed deal values in this view. Most Michigan middle-market deals don't disclose terms.")}
          </section>
        </div>
      </div>`;

    drawChart("flow-chart", {
      labels: rows.map((r) => label(r.period)),
      title: `Michigan deal flow by ${f.period}`,
      xTitle: f.period[0].toUpperCase() + f.period.slice(1) + " (announcement date)",
      yTitle: "Deals (count)",
      y1Title: "Disclosed M&A value ($M)",
      y1Format: (x) => `$${Number(x).toLocaleString("en-US")}`,
      datasets: [
        { type: "bar", label: "M&A deals", data: rows.map((r) => r.maCount), backgroundColor: "#0b1f3a", stack: "n", yAxisID: "y", order: 2 },
        { type: "bar", label: "Financings", data: rows.map((r) => r.finCount), backgroundColor: "#93a8c6", stack: "n", yAxisID: "y", order: 2 },
        { type: "line", label: "Disclosed M&A value ($M)", data: rows.map((r) => +(r.value / 1e6).toFixed(1)), borderColor: "#c8962e", backgroundColor: "#c8962e", yAxisID: "y1", tension: 0.25, pointRadius: 3, order: 1 },
      ],
      tooltip: { label: (ctx) => (ctx.dataset.yAxisID === "y1" ? ` Disclosed value: $${ctx.raw.toLocaleString("en-US")}M` : ` ${ctx.dataset.label}: ${ctx.raw}`) },
    });
    if (window.Chart) {
      const c = window.Chart.getChart("flow-chart");
      if (c) { c.options.scales.x.stacked = true; c.options.scales.y.stacked = true; c.update(); }
    }
  }

  bindFilters(root, f, render);
  root.querySelectorAll("[data-period]").forEach((b) =>
    b.addEventListener("click", () => {
      f.period = b.dataset.period;
      root.querySelectorAll("[data-period]").forEach((x) => x.setAttribute("aria-pressed", x === b));
      render();
    }),
  );
  render();
}
