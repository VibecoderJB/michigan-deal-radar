// "Who's Active in Michigan": banks, PE firms and law firms that appear most on Michigan deals.
// Only publicly published professional information (firm names and deal-team names from press releases).
import { loadAnalytics, loadDeals } from "../data.js";
import { esc } from "../format.js";
import { emptyState, pageHead } from "../ui.js";

const KINDS = ["All", "Investment bank", "Private equity", "Venture capital", "Law firm", "Lender", "Family office"];

export async function renderActive(root, params) {
  const [{ byId }, analytics] = await Promise.all([loadDeals(), loadAnalytics()]);
  const firms = analytics?.whos_active || [];
  let kind = params.get("kind") || "All";

  root.innerHTML = `
    ${pageHead("Who's Active in Michigan", "Banks, private equity firms and law firms that appear most often on Michigan deals, with their recent deals and deal-team members named in public press releases. Useful for networking prep.",
      `<div class="seg" role="group" aria-label="Firm type">${KINDS.map((k) => `<button type="button" data-kind="${esc(k)}" aria-pressed="${k === kind}">${esc(k === "Investment bank" ? "Banks" : k === "Private equity" ? "PE" : k === "Venture capital" ? "VC" : k)}</button>`).join("")}</div>`)}
    <div id="list" class="stack"></div>
    <p class="small muted section-gap">Sources: advisor and lender names come from SEC filings and press releases ("X is serving as financial advisor to Y"); sponsors from deal records. People are listed only when a public press release names them. Michigan-based firms come from the watchlist in <code>config/firms.yml</code>.</p>`;

  function render() {
    const list = firms.filter((f) => kind === "All" || f.kind === kind);
    root.querySelector("#list").innerHTML = list.length
      ? `<div class="table-wrap"><table class="data"><thead><tr><th>#</th><th>Firm</th><th>Type</th><th class="r">Michigan deals</th><th>Recent deals</th><th>Deal team (public)</th></tr></thead><tbody>
        ${list.map((f, i) => `<tr><td class="num">${i + 1}</td><td class="name">${esc(f.name)}${f.michigan_based ? ' <span class="tag">MI-based</span>' : ""}</td><td>${esc(f.kind)}</td><td class="r num">${f.deals}</td>
          <td>${f.recent_deal_ids.map((id) => byId.get(id)).filter(Boolean).slice(0, 3).map((d) => `<div><a href="#/deal/${encodeURIComponent(d.deal_id)}">${esc(d.title)}</a></div>`).join("")}</td>
          <td>${esc((f.people || []).join(", ") || "—")}</td></tr>`).join("")}
        </tbody></table></div>`
      : `<section class="card">${emptyState("No firms of this type are named in the current sources. Advisors are only listed when a filing or press release names them.")}</section>`;
  }
  root.querySelectorAll("[data-kind]").forEach((b) => b.addEventListener("click", () => {
    kind = b.dataset.kind;
    root.querySelectorAll("[data-kind]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    history.replaceState(null, "", `#/active${kind !== "All" ? `?kind=${encodeURIComponent(kind)}` : ""}`);
    render();
  }));
  render();
}
