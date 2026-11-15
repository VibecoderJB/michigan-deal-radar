// Reports: in-app weekly "Michigan Deal Flow" brief with archive, plus PDF and Excel downloads.
import { loadBriefing, loadBriefingIndex, loadDeals, loadReports } from "../data.js";
import { date, esc, money, mm, ndHtml, pct, quarterLabel } from "../format.js";
import { emptyState, pageHead, toast } from "../ui.js";

const dealRows = (items, byId) => (items?.length
  ? `<div class="table-wrap"><table class="data"><thead><tr><th>Deal</th><th>Type</th><th>Status</th><th class="r">Value ($M)</th></tr></thead><tbody>
    ${items.map((b) => `<tr class="clickable" data-id="${esc(b.deal_id)}"><td class="name">${esc(byId.get(b.deal_id)?.title || b.title)}</td><td>${esc(b.deal_type || "")}</td><td>${esc(b.status || "")}</td><td class="r num">${b.value ? mm(b.value) : ndHtml("n.d.")}</td></tr>`).join("")}
    </tbody></table></div>`
  : emptyState("None this week."));

export async function renderBriefing(root, weekParam) {
  const [index, { byId }, reports] = await Promise.all([loadBriefingIndex(), loadDeals(), loadReports()]);
  const weeks = index.weeks || [];
  const pdfFor = (w) => reports?.weekly?.find((r) => r.week_start === w)?.path;
  const downloads = `
    <section class="card"><div class="card-head"><h2>Downloads</h2><span class="sub">regenerated on every data refresh</span></div>
      <div class="stack">
        ${(reports?.excel || []).map((x) => `<a class="btn btn-primary" href="${esc(x.path)}" download>Excel: ${esc(x.title)}</a>`).join("") || '<span class="muted small">Excel workbook builds on the next deploy.</span>'}
        <div><div class="upper" style="margin-bottom:4px">Quarterly Michigan M&amp;A Review (PDF)</div>
          ${(reports?.quarterly || []).slice().reverse().map((q) => `<a class="btn btn-sm" style="margin:0 6px 6px 0" href="${esc(q.path)}" target="_blank" rel="noopener">${esc(quarterLabel(q.quarter))}</a>`).join("") || '<span class="muted small">None yet.</span>'}
        </div>
      </div>
    </section>`;

  if (!weeks.length) {
    root.innerHTML = `${pageHead("Reports", "Weekly Michigan Deal Flow briefs and quarterly reviews.")}${downloads}${emptyState("The first weekly brief publishes on Monday.")}`;
    return;
  }
  const current = weeks.find((w) => w.week_start === weekParam) || weeks[0];
  const pos = weeks.indexOf(current);
  const b = await loadBriefing(current.week_start);
  const s = b.stats;
  const pdf = pdfFor(current.week_start);

  root.innerHTML = `
    ${pageHead("Reports", "The weekly Michigan Deal Flow brief, generated every Monday from the prior week's sourced filings (templates only, no AI), plus quarterly reviews and Excel exports.",
      `${weeks[pos + 1] ? `<a class="btn btn-sm" href="#/briefing/${weeks[pos + 1].week_start}">← Older</a>` : ""}${weeks[pos - 1] ? `<a class="btn btn-sm" href="#/briefing/${weeks[pos - 1].week_start}">Newer →</a>` : ""}
       ${pdf ? `<a class="btn btn-sm btn-accent" href="${esc(pdf)}" target="_blank" rel="noopener">PDF</a>` : ""}`)}
    <section class="brief-hero">
      <div class="upper">Michigan Deal Flow · Week of ${esc(date(b.week_start))} – ${esc(date(b.week_end))}</div>
      <h1>${esc(b.headline)}</h1>
      <div class="mini-stats">
        <div><div class="k">M&amp;A deals</div><div class="v">${s.ma_deals}</div><div class="small">${pct(b.change_vs_trailing.ma_deals)} vs 4-wk avg</div></div>
        <div><div class="k">Disclosed M&amp;A value</div><div class="v">${money(s.ma_disclosed_value, { empty: "$0" })}</div><div class="small">${s.ma_with_value} deals disclosed</div></div>
        <div><div class="k">Financings</div><div class="v">${s.financings}</div><div class="small">${money(s.financing_raised, { empty: "$0" })} raised</div></div>
        <div><div class="k">Fund raises · 13D</div><div class="v">${s.fund_raises} · ${s.stakes}</div><div class="small">${money(s.fund_capital_raised, { empty: "$0" })} reported</div></div>
      </div>
    </section>

    <section class="card"><div class="card-head"><h2>3 talking points for networking calls</h2><button class="btn btn-sm" id="copy" type="button">Copy</button></div>
      <div class="points">${b.talking_points.map((t) => `<div class="point"><div class="topic">${esc(t.topic)}</div><p>${esc(t.text)}</p>${(t.deal_ids || []).length ? `<div class="small" style="margin-top:4px">${t.deal_ids.map((id) => `<a href="#/deal/${encodeURIComponent(id)}">${esc(byId.get(id)?.title || "View deal")}</a>`).join(" · ")}</div>` : ""}</div>`).join("")}</div>
    </section>

    <div class="grid-2 even section-gap">
      <section class="card"><div class="card-head"><h2>Notable M&amp;A</h2></div>${dealRows(b.notable_ma, byId)}</section>
      <section class="card"><div class="card-head"><h2>Largest financings</h2></div>${dealRows(b.top_financings, byId)}</section>
      <section class="card"><div class="card-head"><h2>Sector commentary</h2></div>${(b.sector_commentary || []).map((c) => `<p><b>${esc(c.sector)}.</b> ${esc(c.text)}</p>`).join("") || emptyState("No sector activity this week.")}</section>
      <section class="card"><div class="card-head"><h2>League snapshot</h2><span class="sub">trailing 12 months</span></div>
        ${["acquirers", "financial_advisors"].map((k) => `<div class="upper" style="margin:6px 0 4px">${k === "acquirers" ? "Acquirers" : "Financial advisors"}</div>${(b.league_snapshot[k] || []).map((r, i) => `<div class="small">${i + 1}. ${esc(r.name)} <span class="mono muted">(${r.deals})</span></div>`).join("") || '<div class="small nd">Not disclosed in sources yet</div>'}`).join("")}
      </section>
    </div>

    <div class="grid-2 section-gap">
      <section class="card"><div class="card-head"><h2>Archive</h2><span class="sub">${weeks.length} weeks</span></div>
        <div class="archive">${weeks.map((w) => `<a href="#/briefing/${w.week_start}" class="${w.week_start === current.week_start ? "current" : ""}"><span class="mono small">${esc(date(w.week_start, { year: false }))}</span><span class="hl">${esc(w.headline)}</span><span class="mono small">${w.ma_deals}/${w.financings}</span></a>`).join("")}</div>
      </section>
      <div class="stack">${downloads}
        <section class="card"><div class="card-head"><h2>Sources appendix</h2></div><ol class="sources-list">${(b.sources || []).slice(0, 25).map((x) => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a> <span class="small muted">${esc(x.kind)} · ${esc(date(x.date) || "")}</span></li>`).join("") || '<li class="muted">No sources this week.</li>'}</ol></section>
      </div>
    </div>`;

  root.querySelectorAll("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => { location.hash = `#/deal/${encodeURIComponent(tr.dataset.id)}`; }));
  root.querySelector("#copy").addEventListener("click", async () => {
    const text = `Michigan Deal Flow, week of ${date(b.week_start)}\n\n` + b.talking_points.map((t, i) => `${i + 1}. ${t.topic}: ${t.text}`).join("\n\n");
    try { await navigator.clipboard.writeText(text); toast("Talking points copied"); } catch { toast("Copy isn't available in this browser"); }
  });
}
