// Private capital: Michigan fund vehicles (Form D) and 5%+ ownership stakes (Schedule 13D).
import { loadCapitalFormation, loadOwnership, v } from "../data.js";
import { date, esc, mm, ndHtml } from "../format.js";
import { emptyState, fieldHtml, pageHead } from "../ui.js";

export async function renderCapital(root, params) {
  const [funds, stakes] = await Promise.all([loadCapitalFormation(), loadOwnership()]);
  let tab = params.get("tab") || "funds";

  root.innerHTML = `
    ${pageHead("Private Capital", "Michigan-based fund and real-estate vehicles raising capital (Form D), and activist / 5%+ stakes in Michigan public companies (Schedule 13D). Kept separate from M&amp;A deal counts.",
      `<div class="seg" role="group"><button type="button" data-tab="funds" aria-pressed="${tab === "funds"}">Fund raises (${funds.length})</button><button type="button" data-tab="stakes" aria-pressed="${tab === "stakes"}">13D stakes (${stakes.length})</button></div>`)}
    <div id="body"></div>`;

  const mmCell = (f) => (v(f) == null ? (f?.note === "Indefinite" ? '<span class="nd">Indefinite</span>' : ndHtml("n.d.")) : fieldHtml(f, (x) => `<span class="mono">${esc(mm(x))}</span>`));

  function render() {
    history.replaceState(null, "", `#/capital${tab !== "funds" ? `?tab=${tab}` : ""}`);
    const body = root.querySelector("#body");
    if (tab === "funds") {
      body.innerHTML = funds.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Last filed</th><th>Fund / vehicle</th><th>Category</th><th>City</th><th>County</th><th class="r">Raised ($M)</th><th class="r">Target ($M)</th><th class="r">Investors</th><th>Source</th></tr></thead><tbody>
        ${funds.map((c) => `<tr><td class="num">${esc(date(c.filed))}</td><td class="name">${esc(v(c.name))}</td><td>${esc(v(c.category) || "")}</td><td>${esc(v(c.city) || "—")}</td><td>${esc(v(c.county) || "—")}</td>
          <td class="r">${mmCell(c.amount_raised)}</td><td class="r">${mmCell(c.offering_size)}</td><td class="r num">${v(c.investor_count) ?? "—"}</td>
          <td><a href="${esc(c.sources.at(-1).url)}" target="_blank" rel="noopener">Form D ↗</a></td></tr>`).join("")}</tbody></table></div>` : emptyState("No fund raises in the dataset.");
    } else {
      body.innerHTML = stakes.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Filed</th><th>Company</th><th>Holder(s)</th><th class="r">% of class</th><th>Type</th><th>Purpose (excerpt)</th><th>Source</th></tr></thead><tbody>
        ${stakes.map((o) => `<tr><td class="num">${esc(date(o.filed))}</td><td class="name">${esc(v(o.company))}${v(o.ticker) ? ` <span class="muted mono">${esc(v(o.ticker))}</span>` : ""}</td>
          <td>${esc(o.holders.map((h) => h.name).slice(0, 3).join("; "))}</td><td class="r">${fieldHtml(o.percent_of_class, (x) => `<span class="mono">${esc(x)}%</span>`)}</td>
          <td>${o.amendment ? `Amendment ${esc(o.amendment_no || "")}` : "Initial 13D"}</td><td class="small">${esc((v(o.purpose) || "").slice(0, 180))}${(v(o.purpose) || "").length > 180 ? "…" : ""}</td>
          <td><a href="${esc(o.sources[0].url)}" target="_blank" rel="noopener">13D ↗</a></td></tr>`).join("")}</tbody></table></div>` : emptyState("No Schedule 13D filings in the dataset.");
    }
  }
  root.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
    tab = b.dataset.tab;
    root.querySelectorAll("[data-tab]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    render();
  }));
  render();
}
