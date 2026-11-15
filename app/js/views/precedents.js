// Precedent transactions: deals with a disclosed value or multiple, plus median/mean multiples.
import { precedents, stats } from "../analytics.js";
import { loadDeals, v } from "../data.js";
import { applyFilters, bindFilters, filterBar, readFilters, writeFilters } from "../filters.js";
import { date, esc, mm, mult, ndHtml } from "../format.js";
import { emptyState, fieldHtml, pageHead } from "../ui.js";

const cellMM = (f) => (v(f) == null ? ndHtml("n.d.") : fieldHtml(f, (x) => `<span class="mono">${esc(mm(x))}</span>`));
const cellX = (f) => (v(f) == null ? ndHtml("n.d.") : fieldHtml(f, (x) => `<span class="mono">${esc(mult(x))}</span>`));

export async function renderPrecedents(root, params) {
  const { deals } = await loadDeals();
  const f = readFilters(params, {});

  root.innerHTML = `
    ${pageHead("Precedent Transactions", "Michigan M&amp;A with a disclosed value or multiple. Multiples are shown only when stated in a source or computed from disclosed EV and revenue/EBITDA (estimates are labeled).",
      `<a class="btn btn-primary" href="reports/michigan-deal-radar.xlsx" download>Download Excel (banking format)</a>`)}
    <section class="card filters">${filterBar(f, ["sector", "region", "type", "buyer", "from", "to"])}</section>
    <section class="card" id="summary"></section>
    <div class="table-wrap section-gap"><table class="data"><thead><tr>
      <th>Announced</th><th>Target</th><th>Acquirer</th><th>Type</th><th>Status</th><th class="r">EV ($M)</th><th class="r">Txn value ($M)</th>
      <th class="r">Revenue ($M)</th><th class="r">EBITDA ($M)</th><th class="r">EV/Rev</th><th class="r">EV/EBITDA</th></tr></thead><tbody id="rows"></tbody></table></div>
    <p class="small muted section-gap">$ in millions. n.d. = not disclosed by any source. Click <b>src</b> for the exact quote behind any number. The Excel workbook's Precedents tab includes median/mean rows and live source links.</p>`;

  function render() {
    writeFilters("precedents", f);
    const rows = precedents(applyFilters(deals, f));
    const fin = (d) => d.financials || {};
    const s = { ebitda: stats(rows.map((d) => v(fin(d).ev_ebitda))), rev: stats(rows.map((d) => v(fin(d).ev_revenue))), val: stats(rows.map((d) => d._value)) };
    const row = (label, st, fmt) => `<tr><td class="name">${label}</td><td class="r num">${st.n}</td><td class="r num">${fmt(st.median) ?? "n.d."}</td><td class="r num">${fmt(st.mean) ?? "n.d."}</td><td class="r num">${fmt(st.low) ?? "n.d."}</td><td class="r num">${fmt(st.high) ?? "n.d."}</td></tr>`;
    root.querySelector("#summary").innerHTML = `<div class="card-head"><h2>Summary statistics</h2><span class="sub">${rows.length} precedent deals in view</span></div>
      <div class="table-wrap"><table class="data"><thead><tr><th>Metric</th><th class="r">N</th><th class="r">Median</th><th class="r">Mean</th><th class="r">Low</th><th class="r">High</th></tr></thead><tbody>
      ${row("EV / EBITDA", s.ebitda, mult)}${row("EV / Revenue", s.rev, mult)}${row("Disclosed value ($M)", s.val, mm)}</tbody></table></div>`;
    root.querySelector("#rows").innerHTML = rows.length ? rows.map((d) => `<tr class="clickable" data-id="${esc(d.deal_id)}">
      <td class="num">${esc(date(d._date) || "")}</td><td class="name">${esc(v(d.target?.name) || "Not disclosed")}</td><td>${esc(v(d.acquirer?.name) || "Not disclosed")}</td>
      <td>${esc(v(d.deal_type))}</td><td>${esc(v(d.status))}</td>
      <td class="r">${cellMM(fin(d).enterprise_value)}</td><td class="r">${cellMM(fin(d).transaction_value)}</td><td class="r">${cellMM(fin(d).revenue)}</td><td class="r">${cellMM(fin(d).ebitda)}</td>
      <td class="r">${cellX(fin(d).ev_revenue)}</td><td class="r">${cellX(fin(d).ev_ebitda)}</td></tr>`).join("")
      : `<tr><td colspan="11">${emptyState("No deals with disclosed terms for these filters. Most Michigan middle-market deals don't disclose terms.")}</td></tr>`;
  }
  root.querySelector("#rows").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-id]");
    if (tr && !e.target.closest(".fn,.prov,a")) location.hash = `#/deal/${encodeURIComponent(tr.dataset.id)}`;
  });
  bindFilters(root, f, render);
  render();
}
