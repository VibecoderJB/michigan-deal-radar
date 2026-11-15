// Data-quality report from the latest pipeline run.
import { loadDeals, loadQuality } from "../data.js";
import { date, esc } from "../format.js";
import { emptyState, pageHead } from "../ui.js";

export async function renderQuality(root) {
  const [q, { byId }] = await Promise.all([loadQuality(), loadDeals()]);
  if (!q) {
    root.innerHTML = `${pageHead("Data Quality", "")}${emptyState("The quality report is written after the next pipeline run.")}`;
    return;
  }
  const feeds = q.sources?.news?.feeds || [];
  root.innerHTML = `
    ${pageHead("Data Quality", `Written automatically after every pipeline run. Last run ${esc(date(q.generated_at?.slice(0, 10)) || "")}, window ${esc(q.window?.map((x) => date(x)).join(" – ") || "")}.`)}
    <section class="kpis">
      <div class="kpi accent"><div class="label">New deals this run</div><div class="value">${q.new_deal_count}</div></div>
      <div class="kpi"><div class="label">Total deals</div><div class="value">${q.total_deals}</div></div>
      <div class="kpi"><div class="label">Filings merged</div><div class="value">${q.duplicates_merged}</div><div class="sub">duplicate reports linked</div></div>
      <div class="kpi"><div class="label">Flagged for review</div><div class="value">${q.flagged_for_review_count}</div></div>
      <div class="kpi"><div class="label">Source errors</div><div class="value">${q.source_error_count}</div><div class="sub">skipped, never fatal</div></div>
      <div class="kpi"><div class="label">Evidence events</div><div class="value">${q.evidence_events}</div><div class="sub">filings + news items</div></div>
    </section>
    <div class="grid-2 even">
      <section class="card"><div class="card-head"><h2>Missing fields</h2><span class="sub">share of deals where no source discloses the value</span></div>
        <div class="table-wrap"><table class="data"><thead><tr><th>Field</th><th class="r">Missing</th><th class="r">Of</th><th class="r">%</th></tr></thead><tbody>
        ${Object.entries(q.missing_fields).map(([k, m]) => `<tr><td>${esc(k)}</td><td class="r num">${m.missing}</td><td class="r num">${m.of}</td><td class="r num">${m.pct_missing}%</td></tr>`).join("")}
        </tbody></table></div></section>
      <section class="card"><div class="card-head"><h2>How values were obtained</h2><span class="sub">count of populated fields</span></div>
        <dl class="kv">${Object.entries(q.field_methods || {}).map(([k, n]) => `<dt>${esc(k.replace("_", " "))}</dt><dd>${n}</dd>`).join("")}</dl>
        <div class="upper" style="margin:12px 0 4px">Confidence</div>
        <dl class="kv">${Object.entries(q.confidence || {}).map(([k, n]) => `<dt>${esc(k)}</dt><dd>${n}</dd>`).join("")}</dl>
        ${q.v1_migration ? `<div class="upper" style="margin:12px 0 4px">v1 → v2 migration</div><p class="small">${q.v1_migration.covered_in_v2_evidence} of ${q.v1_migration.v1_records} v1 records are present in the v2 evidence ledger.</p>` : ""}
      </section>
    </div>
    <section class="card section-gap"><div class="card-head"><h2>Flagged for review</h2><span class="sub">low confidence or unresolved buyer/target roles</span></div>
      ${(q.flagged_for_review || []).length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Deal</th><th>Flags</th><th>Confidence</th></tr></thead><tbody>
        ${q.flagged_for_review.slice(0, 50).map((r) => `<tr><td><a href="#/deal/${encodeURIComponent(r.deal_id)}">${esc(byId.get(r.deal_id)?.title || r.title)}</a></td><td>${esc((r.flags || []).join(", ").replaceAll("_", " "))}</td><td>${esc(r.confidence)}</td></tr>`).join("")}
      </tbody></table></div>` : emptyState("Nothing flagged.")}
    </section>
    <div class="grid-2 even section-gap">
      <section class="card"><div class="card-head"><h2>Sources this run</h2></div>
        <dl class="kv">${Object.entries(q.sources || {}).map(([k, s]) => `<dt>${esc(k)}</dt><dd>${esc(s.status)}${s.new != null ? ` · ${s.new} new` : ""}${s.errors ? ` · ${s.errors} errors` : ""}</dd>`).join("")}</dl>
        ${feeds.length ? `<div class="upper" style="margin:12px 0 4px">RSS feeds (robots.txt checked)</div>${feeds.map((f) => `<div class="small">${f.ok ? "✓" : "✗"} ${esc(f.name)} ${f.ok ? `<span class="muted">(${f.items} items, ${f.kept} Michigan deal items)</span>` : `<span class="muted">${esc(f.error || "")}</span>`}</div>`).join("")}` : ""}
      </section>
      <section class="card"><div class="card-head"><h2>Source errors</h2><span class="sub">each skipped individually</span></div>
        ${(q.source_errors || []).length ? q.source_errors.slice(0, 20).map((e) => `<div class="small"><b>${esc(e.source)}</b> ${esc(e.accession || "")}: <span class="muted">${esc(e.error)}</span></div>`).join("") : emptyState("No errors.")}
      </section>
    </div>`;
}
