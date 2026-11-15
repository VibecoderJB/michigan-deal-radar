// Sponsor activity: PE platform deals vs add-ons, by quarter, plus the sponsor deal list.
import { periodBuckets } from "../analytics.js";
import { loadDeals, v } from "../data.js";
import { quarterLabel, quarterOf } from "../format.js";
import { chartBox, dealItem, drawChart, emptyState, pageHead } from "../ui.js";

export async function renderSponsors(root) {
  const { deals } = await loadDeals();
  const sponsorDeals = deals.filter((d) => ["PE Buyout", "Add-on"].includes(v(d.deal_type))).sort((a, b) => b._date.localeCompare(a._date));
  const platform = sponsorDeals.filter((d) => v(d.deal_type) === "PE Buyout");
  const addon = sponsorDeals.filter((d) => v(d.deal_type) === "Add-on");
  const buckets = periodBuckets("quarter", 8);
  const per = (list) => buckets.map((b) => list.filter((d) => d._date && quarterOf(d._date) === b).length);

  root.innerHTML = `
    ${pageHead("Sponsor Activity", "Private equity platform acquisitions vs. add-ons to existing portfolio companies on Michigan deals.")}
    <section class="kpis">
      <div class="kpi accent"><div class="label">Sponsor deals</div><div class="value">${sponsorDeals.length}</div><div class="sub">all dates</div></div>
      <div class="kpi"><div class="label">Platform (PE buyout)</div><div class="value">${platform.length}</div><div class="sub">new platform investments</div></div>
      <div class="kpi"><div class="label">Add-ons</div><div class="value">${addon.length}</div><div class="sub">"portfolio company of …"</div></div>
      <div class="kpi"><div class="label">Add-on share</div><div class="value">${sponsorDeals.length ? Math.round((addon.length / sponsorDeals.length) * 100) : 0}%</div><div class="sub">of sponsor deals</div></div>
    </section>
    <section class="card">${chartBox("sponsor-chart", "Stacked bars: platform buyouts and add-on acquisitions per quarter.")}</section>
    <section class="card section-gap"><div class="card-head"><h2>Sponsor-backed deals</h2><a href="#/league">Sponsor league table →</a></div>
      ${sponsorDeals.length ? sponsorDeals.slice(0, 30).map(dealItem).join("") : emptyState("No sponsor-backed deals identified yet. Sponsors are detected from the firm watchlist, investment-firm naming patterns, and phrases like \"a portfolio company of\" in filings and press releases.")}
    </section>`;

  drawChart("sponsor-chart", {
    title: "Michigan sponsor deals by quarter",
    xTitle: "Quarter (announcement date)",
    yTitle: "Deals (count)",
    labels: buckets.map(quarterLabel),
    datasets: [
      { label: "Platform (PE buyout)", data: per(platform), backgroundColor: "#0b1f3a", stack: "s" },
      { label: "Add-on", data: per(addon), backgroundColor: "#c8962e", stack: "s" },
    ],
  });
  const c = window.Chart?.getChart("sponsor-chart");
  if (c) { c.options.scales.x.stacked = true; c.options.scales.y.stacked = true; c.update(); }
}
