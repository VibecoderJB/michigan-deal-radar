// Deal tear sheet: every sourced field, parties, financials, advisors, timeline, sources.
import { disclosed, loadDeals, v } from "../data.js";
import { date, esc, mm, money, mult, ndHtml } from "../format.js";
import { confBadge, emptyState, fieldHtml, statusBadge } from "../ui.js";
import { starButton } from "../watchlist.js";

const term = (k, html) => `<div class="term"><div class="k">${k}</div><div class="v">${html}</div></div>`;
const fDate = (f) => fieldHtml(f, (x) => `<span class="mono">${esc(date(x))}</span>`);
const fMM = (f) => fieldHtml(f, (x) => `<span class="mono">${esc(mm(x))}</span>`);
const fX = (f) => fieldHtml(f, (x) => `<span class="mono">${esc(mult(x))}</span>`);
const fText = (f) => fieldHtml(f);

function partyCard(title, p, extra = "") {
  if (!p) return "";
  const rows = [
    ["Name", fText(p.name)],
    ["HQ / City", fText(p.hq || p.city)],
    ["County", fText(p.county)],
    ["Region", fText(p.region)],
    ["GICS sector", fText(p.gics_sector)],
    ["GICS sub-industry", fText(p.gics_sub_industry)],
    ["Public / private", fText(p.public_private)],
    ["Ticker", fieldHtml(p.ticker, (x) => `<span class="mono">${esc(x)}</span>`)],
  ];
  if (p.type) rows.push(["Buyer type", fText(p.type)]);
  if (p.sponsor) rows.push(["PE sponsor", fText(p.sponsor)]);
  if (p.platform) rows.push(["Platform company", fText(p.platform)]);
  if (p.is_add_on) rows.push(["Add-on to platform", disclosed(p.is_add_on) ? fieldHtml(p.is_add_on, () => "Yes") : '<span class="muted">No indication</span>']);
  return `<section class="card"><div class="card-head"><h2>${title}</h2>${extra}</div>
    <dl class="kv">${rows.map(([k, h]) => `<dt>${k}</dt><dd style="font-family:var(--sans)">${h}</dd>`).join("")}</dl></section>`;
}

export async function renderDetail(root, id) {
  const { deals, byId } = await loadDeals();
  const d = byId.get(id);
  if (!d) {
    root.innerHTML = `<a class="back-link" href="#/deals">← All deals</a>${emptyState("That deal isn't in the dataset. It may have been merged into another record.")}`;
    return;
  }
  const f = d.financials || {};
  const isFin = d.category === "Financing";
  const headline = d._value;
  const related = deals.filter((o) => o !== d && o.deal_id !== d.deal_id && (
    (d.target?.cik && [o.target?.cik, o.acquirer?.cik, o.michigan_party?.cik].includes(d.target.cik)) ||
    (d.acquirer?.cik && [o.target?.cik, o.acquirer?.cik, o.michigan_party?.cik].includes(d.acquirer.cik)))).slice(0, 6);

  root.innerHTML = `
    <a class="back-link" href="#/deals" id="back">← All deals</a>
    <section class="tear-head">
      <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-start">
        <div style="min-width:0">
          <div class="meta">${statusBadge(v(d.status))}<span class="tag">${esc(v(d.deal_type) || "")}</span><span>${esc(d.category)}</span>${confBadge(d.confidence)}<span class="mono">ID ${esc(d.deal_id)}</span></div>
          <h1>${esc(d.title)}</h1>
          <div class="meta"><span>Michigan link: ${esc(d.michigan_link || "")}</span>${d.focus_sector ? `<span>· ${esc(d.focus_sector)}</span>` : ""}${d._region ? `<span>· ${esc(d._region)}</span>` : ""}</div>
        </div>
        ${starButton(d, { label: true })}
      </div>
      <div class="value">${headline ? esc(money(headline)) : '<span style="font-size:1rem;color:#9fb0c9;font-style:italic">Value not disclosed</span>'}</div>
      <div class="meta">${isFin ? "Amount raised" : "Disclosed value (EV, else transaction value)"} · Data as of ${esc(date(d.sources?.at(-1)?.date) || "")}</div>
    </section>

    ${(d.flags || []).length ? `<div class="banner" style="border-radius:6px;margin-bottom:12px;text-align:left">Review flags: ${d.flags.map((x) => esc(x.replaceAll("_", " "))).join(", ")}. Values shown are only those stated in sources.</div>` : ""}

    <section class="terms" aria-label="Key terms">
      ${term("Announced", fDate(d.announcement_date))}
      ${term("Closed", fDate(d.closing_date))}
      ${term("Status", fText(d.status))}
      ${term("Deal type", fText(d.deal_type))}
      ${isFin ? `${term("Amount raised ($M)", fMM(f.amount_raised))}${term("Offering size ($M)", fMM(f.offering_size))}${term("Investors (#)", fieldHtml(f.investor_count, (x) => `<span class="mono">${x}</span>`))}${term("First sale", fDate(d.first_sale_date))}`
        : `${term("Enterprise value ($M)", fMM(f.enterprise_value))}${term("Equity value ($M)", fMM(f.equity_value))}${term("Transaction value ($M)", fMM(f.transaction_value))}${term("Price per share", fieldHtml(f.price_per_share, (x) => `<span class="mono">$${Number(x).toFixed(2)}</span>`))}
           ${term("Revenue ($M)", fMM(f.revenue))}${term("EBITDA ($M)", fMM(f.ebitda))}${term("EV / Revenue", fX(f.ev_revenue))}${term("EV / EBITDA", fX(f.ev_ebitda))}
           ${term("Consideration", fText(f.consideration))}`}
    </section>

    <section class="card section-gap">
      <div class="card-head"><h2>Deal rationale</h2><span class="sub">quoted verbatim from the source</span></div>
      ${disclosed(d.rationale) ? `<blockquote class="quote">${fieldHtml(d.rationale)}</blockquote>` : `<p class="nd">Not disclosed in the sources.</p>`}
    </section>

    <div class="grid-2 even section-gap">
      ${partyCard(d.category === "Financing" ? "Company (issuer)" : "Target", d.target)}
      ${partyCard(d.category === "Financing" ? "Investor(s)" : "Acquirer", d.acquirer)}
    </div>
    ${d.seller ? `<div class="section-gap">${partyCard("Seller", d.seller)}</div>` : ""}
    ${(d.flags || []).includes("roles_unresolved") && d.michigan_party ? `<div class="section-gap">${partyCard("Michigan party (role under review)", d.michigan_party)}</div>` : ""}

    <section class="card section-gap">
      <div class="card-head"><h2>Advisors &amp; lenders</h2><span class="sub">as named in public filings / releases</span></div>
      ${(d.advisors || []).length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Firm</th><th>Role</th><th>Client</th><th>Deal team (public)</th><th>Source</th></tr></thead><tbody>
        ${d.advisors.map((a) => `<tr><td class="name">${esc(a.firm)}</td><td>${esc({ financial: "Financial advisor", legal: "Legal counsel", lender: "Lender" }[a.role] || a.role)}</td><td>${esc(a.client || "—")}</td><td>${esc((a.people || []).join(", ") || "—")}</td><td>${fieldHtml({ value: "Quote", source_url: a.source_url, source_text: a.source_text, method: a.method })}</td></tr>`).join("")}
      </tbody></table></div>` : `<p class="nd">No advisors disclosed in the sources.</p>`}
    </section>

    ${(d.people || []).length ? `<section class="card section-gap"><div class="card-head"><h2>Related persons</h2><span class="sub">from the Form D filing</span></div>
      <dl class="kv">${d.people.map((p) => `<dt>${esc(p.name)}</dt><dd style="font-family:var(--sans)">${esc((p.roles || []).join(" · "))}</dd>`).join("")}</dl></section>` : ""}

    <div class="grid-2 even section-gap">
      <section class="card"><div class="card-head"><h2>Timeline</h2></div>
        <ol class="timeline">${(d.timeline || []).map((t) => `<li class="${esc(t.status || "")}"><div class="when">${esc(date(t.date) || "")} · ${esc(t.status || "")}</div><div>${esc(t.event)}</div>${t.source_url ? `<a class="small" href="${esc(t.source_url)}" target="_blank" rel="noopener">Source ↗</a>` : ""}</li>`).join("")}</ol>
      </section>
      <section class="card"><div class="card-head"><h2>Sources</h2><span class="sub">${(d.sources || []).length} · ${esc(d.confidence)} confidence</span></div>
        <ol class="sources-list">${(d.sources || []).map((s) => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a><div class="small muted">${esc(s.kind)} · ${esc(s.publisher || "")} · ${esc(date(s.date) || "")} · ${confBadge(s.confidence)}</div></li>`).join("")}</ol>
        <p class="small muted" style="margin-top:8px">Click <span class="fn" style="cursor:default">src</span> next to any value to see the exact source text it came from.</p>
      </section>
    </div>

    ${related.length ? `<section class="card section-gap"><div class="card-head"><h2>Other deals involving these companies</h2></div>
      ${related.map((o) => `<a class="deal-item" href="#/deal/${encodeURIComponent(o.deal_id)}"><span class="deal-title">${esc(o.title)}</span><span class="deal-amt">${o._value ? money(o._value) : ndHtml("n.d.")}</span></a>`).join("")}</section>` : ""}
  `;
  root.querySelector("#back").addEventListener("click", (e) => {
    if ((window.mdrNavDepth || 0) > 1) { e.preventDefault(); history.back(); }
  });
}

