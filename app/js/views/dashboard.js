// Dashboard: this week's deals, KPIs, capital raised by month, mix by type and sector.
import { DEAL_TYPES, loadBriefingIndex, loadDeals } from "../data.js";
import { date, esc, isoDay, money, monthLabel } from "../format.js";
import { barRows, dealItem, emptyState } from "../ui.js";

let chart;

const weekStartOf = (d) => {
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  copy.setDate(copy.getDate() - ((copy.getDay() + 6) % 7)); // Monday
  return copy;
};
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const capital = (list) => list.filter((d) => d.type === "Fundraise").reduce((s, d) => s + (d.amount_sold || 0), 0);
const inRange = (list, from, to) => list.filter((d) => d.filed >= from && d.filed <= to);

export async function renderDashboard(root) {
  const [{ deals }, index] = await Promise.all([loadDeals(), loadBriefingIndex().catch(() => ({ weeks: [] }))]);
  const today = new Date();

  // "This week" = Monday..today. Early in the week fall back to the trailing 7 days.
  let start = weekStartOf(today);
  let label = `Week of ${date(isoDay(start), { year: false })}`;
  let week = inRange(deals, isoDay(start), isoDay(today));
  if (week.length < 3) {
    start = addDays(today, -6);
    label = "Last 7 days";
    week = inRange(deals, isoDay(start), isoDay(today));
  }

  // Trailing 4-week average of deal count for context.
  const prior = inRange(deals, isoDay(addDays(start, -28)), isoDay(addDays(start, -1)));
  const avgDeals = prior.length / 4;
  const delta = avgDeals ? ((week.length - avgDeals) / avgDeals) * 100 : null;

  const yearAgo = isoDay(addDays(today, -365));
  const last12 = deals.filter((d) => d.filed >= yearAgo);
  const funds = last12.filter((d) => d.details?.is_pooled_fund);
  const countBy = (key) => last12.reduce((m, d) => ((m[d[key]] = (m[d[key]] || 0) + 1), m), {});
  const byType = countBy("type");
  const bySector = countBy("sector");
  const latestBriefing = index.weeks?.[0];

  const largest = inRange(deals, isoDay(addDays(today, -90)), isoDay(today))
    .filter((d) => d.type === "Fundraise" && d.amount_sold)
    .sort((a, b) => b.amount_sold - a.amount_sold)
    .slice(0, 5);

  const deltaHtml = delta === null ? "" : `<span class="${delta >= 0 ? "delta-up" : "delta-down"}">${delta >= 0 ? "▲" : "▼"} ${Math.abs(delta).toFixed(0)}%</span> vs 4-wk avg`;

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>Dashboard</h1>
        <p>M&amp;A, private equity and private fundraising involving Michigan companies, from SEC EDGAR.</p>
      </div>
    </div>

    <section class="kpis" aria-label="Key figures">
      <div class="kpi accent"><div class="label">${esc(label)}</div><div class="value">${week.length}</div><div class="sub">${deltaHtml || "deals filed"}</div></div>
      <div class="kpi"><div class="label">Raised this week</div><div class="value">${money(capital(week), { empty: "$0" })}</div><div class="sub">Form D amount sold</div></div>
      <div class="kpi"><div class="label">Raised · 12 mo</div><div class="value">${money(capital(last12))}</div><div class="sub">${byType.Fundraise || 0} offerings</div></div>
      <div class="kpi"><div class="label">Deals · 12 mo</div><div class="value">${last12.length}</div><div class="sub">all types</div></div>
      <div class="kpi"><div class="label">Funds raising</div><div class="value">${funds.length}</div><div class="sub">PE · VC · hedge · other</div></div>
      <div class="kpi"><div class="label">M&amp;A · 12 mo</div><div class="value">${byType["M&A"] || 0}</div><div class="sub">${byType.Stake || 0} 13D stakes</div></div>
    </section>

    <div class="grid-2">
      <section class="card">
        <div class="card-head"><h2>${esc(label)}</h2><a href="#/deals?from=${isoDay(start)}">View all →</a></div>
        <div class="deal-list">${week.length ? week.slice(0, 8).map((d) => dealItem(d)).join("") : emptyState("No Michigan filings yet this week.")}</div>
      </section>
      <div class="stack">
        <section class="card">
          <div class="card-head"><h2>Latest briefing</h2><a href="#/briefing">Open →</a></div>
          ${latestBriefing
            ? `<div class="upper">Week of ${date(latestBriefing.week_start)}</div>
               <p style="margin:6px 0 10px;font-weight:600">${esc(latestBriefing.headline)}</p>
               <div class="mono small muted">${latestBriefing.deal_count} deals · ${money(latestBriefing.capital_raised, { empty: "$0" })} raised</div>`
            : emptyState("The first briefing is generated on Monday.")}
        </section>
        <section class="card">
          <div class="card-head"><h2>Deals by type</h2><span class="muted small">12 months</span></div>
          ${barRows(DEAL_TYPES.map((t) => ({ label: t, value: byType[t] || 0 })), {
            href: (r) => `#/deals?type=${encodeURIComponent(r.label)}`,
          })}
        </section>
      </div>
    </div>

    <section class="card section-gap">
      <div class="card-head"><h2>Capital raised by month</h2><span class="muted small">Form D amount sold · bars = $ · line = # of offerings</span></div>
      <div class="chart-box"><canvas id="monthly-chart" aria-label="Capital raised by month chart" role="img"></canvas></div>
    </section>

    <div class="grid-2 even section-gap">
      <section class="card">
        <div class="card-head"><h2>Largest raises</h2><span class="muted small">last 90 days</span></div>
        <div class="deal-list">${largest.length ? largest.map((d) => dealItem(d)).join("") : emptyState("No raises in the last 90 days.")}</div>
      </section>
      <section class="card">
        <div class="card-head"><h2>Most active sectors</h2><span class="muted small">12 months · # deals</span></div>
        ${barRows(
          Object.entries(bySector)
            .filter(([s]) => s !== "Other")
            .sort((a, b) => b[1] - a[1])
            .slice(0, 8)
            .map(([label, value]) => ({ label, value })),
          { href: (r) => `#/deals?sector=${encodeURIComponent(r.label)}`, dim: true },
        )}
      </section>
    </div>`;

  drawMonthlyChart(last12, today);
}

function drawMonthlyChart(deals, today) {
  const months = [];
  for (let i = 11; i >= 0; i--) {
    const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  const raised = Object.fromEntries(months.map((m) => [m, 0]));
  const counts = Object.fromEntries(months.map((m) => [m, 0]));
  for (const d of deals) {
    const m = d.filed.slice(0, 7);
    if (d.type === "Fundraise" && m in raised) {
      raised[m] += d.amount_sold || 0;
      counts[m] += 1;
    }
  }

  const canvas = document.getElementById("monthly-chart");
  if (!canvas || !window.Chart) return;
  chart?.destroy();
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue("--accent").trim();
  const muted = css.getPropertyValue("--muted").trim();
  const line = css.getPropertyValue("--line").trim();
  const mono = css.getPropertyValue("--mono").trim();

  chart = new window.Chart(canvas, {
    data: {
      labels: months.map(monthLabel),
      datasets: [
        { type: "bar", label: "Capital raised", data: months.map((m) => raised[m]), backgroundColor: accent, borderRadius: 4, maxBarThickness: 36, yAxisID: "y", order: 2 },
        { type: "line", label: "Offerings", data: months.map((m) => counts[m]), borderColor: "#c5d1e3", backgroundColor: "#c5d1e3", pointRadius: 3, borderWidth: 1.5, tension: 0.3, yAxisID: "y1", order: 1 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0a1628",
          borderColor: line,
          borderWidth: 1,
          titleFont: { family: mono },
          bodyFont: { family: mono },
          callbacks: { label: (ctx) => (ctx.dataset.yAxisID === "y" ? ` Raised: ${money(ctx.raw, { empty: "$0" })}` : ` Offerings: ${ctx.raw}`) },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: muted, font: { family: mono, size: 10 }, maxRotation: 0, autoSkip: true } },
        y: { grid: { color: line }, border: { display: false }, ticks: { color: muted, font: { family: mono, size: 10 }, callback: (v) => money(v, { empty: "$0" }), maxTicksLimit: 5 } },
        y1: { position: "right", grid: { display: false }, border: { display: false }, ticks: { color: muted, font: { family: mono, size: 10 }, precision: 0, maxTicksLimit: 5 } },
      },
    },
  });
}
