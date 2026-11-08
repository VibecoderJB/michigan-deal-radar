// Deal detail: key facts, rule-based summary, filing excerpt, people, amendment history.
import { loadDeals } from "../data.js";
import { badge, date, esc, fullMoney, money, num } from "../format.js";
import { dealItem, emptyState } from "../ui.js";
import { starButton } from "../watchlist.js";

const fact = (k, v, mono = false) =>
  v === null || v === undefined || v === "" ? "" : `<div class="fact"><div class="k">${k}</div><div class="v ${mono ? "mono" : ""}">${v}</div></div>`;

function factsFor(d) {
  const x = d.details || {};
  const common = [
    fact("Filed", date(d.filed), true),
    fact("Form", esc(d.form), true),
    fact("City", esc(d.city || "—")),
    fact("Sector", esc(d.sector || "—")),
  ];
  if (d.form === "D" || d.form === "D/A") {
    return [
      ...common,
      fact("Offering size", x.offering_indefinite ? "Indefinite" : fullMoney(x.total_offering_amount), true),
      fact("Amount sold", fullMoney(d.amount_sold), true),
      fact("Remaining", x.offering_indefinite ? "Indefinite" : fullMoney(x.total_remaining), true),
      fact("Investors", num(x.investor_count), true),
      fact("First sale", x.first_sale_yet_to_occur ? "Yet to occur" : date(d.event_date), true),
      fact("Industry group", esc(d.industry || "—")),
      fact("Securities", esc((x.securities || []).join(", ") || "—")),
      fact("Exemptions", esc((x.exemptions || []).join(", ") || "—")),
      fact("Min. investment", x.minimum_investment ? fullMoney(x.minimum_investment) : null, true),
      fact("Entity type", esc(x.entity_type || "")),
      fact("Incorporated", esc([x.jurisdiction, x.year_of_inc].filter(Boolean).join(", "))),
      fact("Revenue range", esc(x.revenue_range || "")),
    ];
  }
  if (d.type === "Stake") {
    return [
      ...common,
      fact("Ticker", esc(d.ticker || "—"), true),
      fact("Stake", x.percent_of_class != null ? `${x.percent_of_class}%` : "—", true),
      fact("Event date", date(d.event_date), true),
      fact("Security", esc(x.security_class || "")),
      fact("CUSIP", esc(x.cusip || ""), true),
    ];
  }
  return [
    ...common,
    fact("Ticker", esc(d.ticker || "—"), true),
    fact("Counterparty", esc(d.counterparty || "")),
    fact("Value cited", d.amount ? `~${money(d.amount)}` : null, true),
    fact("Industry", esc(d.industry || "")),
  ];
}

export async function renderDetail(root, id) {
  const { deals, byId } = await loadDeals();
  const d = byId.get(id);
  if (!d) {
    root.innerHTML = `<a class="back-link" href="#/deals">← All deals</a>${emptyState("That deal isn't in the dataset. It may have been merged with an amended filing.")}`;
    return;
  }
  const related = deals.filter((o) => o.cik === d.cik && o.id !== d.id).slice(0, 6);
  const headline = d.amount ?? d.amount_sold;
  const isFormD = d.form === "D" || d.form === "D/A";
  const items = (d.items || []).filter((i) => i !== "9.01");

  root.innerHTML = `
    <a class="back-link" href="#/deals" id="back-link">← All deals</a>
    <section class="detail-head">
      <div class="row">
        <div style="min-width:0">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px">${badge(d.type)}<span class="tag">${esc(d.subtype || "")}</span></div>
          <h1>${esc(d.company)}${d.ticker ? ` <span class="muted mono" style="font-size:1rem">${esc(d.ticker)}</span>` : ""}</h1>
          <div class="muted small">${esc([d.city, d.state].filter(Boolean).join(", "))} · CIK <span class="mono">${esc(d.cik)}</span></div>
        </div>
        ${starButton(d.cik, d.company, { label: true })}
      </div>
      ${headline ? `<div><div class="upper">${isFormD ? (d.details?.total_offering_amount ? "Offering size" : "Amount sold") : "Value cited in filing"}</div><div class="detail-amount">${money(headline, { estimate: d.amount_is_estimate })}</div></div>` : ""}
    </section>

    <div class="stack">
      <section class="card">
        <div class="card-head"><h2>Summary</h2><span class="muted small">auto-generated from filing data</span></div>
        <p style="margin:0">${esc(d.summary)}</p>
        ${d.excerpt ? `<div class="upper" style="margin:14px 0 6px">From the filing</div><blockquote class="excerpt">${esc(d.excerpt)}</blockquote>` : ""}
        ${items.length ? `<div style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap">${items.map((i, n) => `<span class="tag mono" title="${esc(d.details?.item_titles?.[n] || "")}">Item ${esc(i)}</span>`).join("")}</div>` : ""}
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:16px">
          <a class="btn btn-accent" href="${esc(d.url)}" target="_blank" rel="noopener">View filing on SEC EDGAR ↗</a>
          ${d.doc_url ? `<a class="btn" href="${esc(d.doc_url)}" target="_blank" rel="noopener">Primary document ↗</a>` : ""}
          <a class="btn btn-ghost" href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${esc(d.cik)}" target="_blank" rel="noopener">Company filings ↗</a>
        </div>
      </section>

      <section class="facts" aria-label="Key facts">${factsFor(d).join("")}</section>

      ${d.related_persons?.length ? `
      <section class="card">
        <div class="card-head"><h2>${d.type === "Stake" ? "Reporting persons" : "Related persons"}</h2><span class="muted small">${d.related_persons.length}</span></div>
        <div class="people">${d.related_persons.map((p) => `<div class="person"><span>${esc(p.name)}${p.clarification ? `<div class="muted small">${esc(p.clarification)}</div>` : ""}</span><span class="muted small" style="text-align:right">${esc((p.roles || []).join(" · "))}</span></div>`).join("")}</div>
      </section>` : ""}

      ${d.filings?.length > 1 ? `
      <section class="card">
        <div class="card-head"><h2>Filing history</h2><span class="muted small">${d.filings.length} filings for this offering</span></div>
        <div class="people">${d.filings.slice().reverse().map((f) => `<div class="person"><span class="mono">${date(f.filed)} · ${esc(f.form)}</span><span class="mono">${money(f.amount_sold)} sold</span></div>`).join("")}</div>
      </section>` : ""}

      ${related.length ? `
      <section class="card">
        <div class="card-head"><h2>Other filings by ${esc(d.company)}</h2></div>
        <div class="deal-list">${related.map((o) => dealItem(o)).join("")}</div>
      </section>` : ""}
    </div>`;

  // Prefer real "back" when the user navigated here from inside the app.
  root.querySelector("#back-link").addEventListener("click", (e) => {
    if ((window.mdrNavDepth || 0) > 1) {
      e.preventDefault();
      history.back();
    }
  });
}
