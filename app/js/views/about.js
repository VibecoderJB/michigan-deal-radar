// About / methodology page.
import { loadMeta } from "../data.js";
import { date, esc, relativeTime } from "../format.js";

export async function renderAbout(root) {
  const meta = await loadMeta().catch(() => ({}));
  const run = meta.last_run || {};
  const counts = meta.counts_by_type || {};

  root.innerHTML = `
    <div class="page-head"><div><h1>About &amp; methodology</h1><p>How Michigan Deal Radar finds, classifies and summarizes deals.</p></div></div>
    <div class="grid-2">
      <article class="card prose">
        <h2 style="margin-top:0">What this is</h2>
        <p>A free tracker of M&amp;A, private equity and private fundraising activity involving Michigan companies. Every record comes straight from public SEC EDGAR filings and links back to the original document.</p>

        <h2>Data sources</h2>
        <ul>
          <li><strong>Form D</strong>: Regulation D private placements and fund raises where the issuer's principal place of business is in Michigan. Parsed from the filing XML: offering size, amount sold, investors, first-sale date, industry group, pooled-fund type, exemptions and related persons.</li>
          <li><strong>Form 8-K</strong>: current reports from Michigan-headquartered public companies with Item 1.01 (material definitive agreement), Item 2.01 (completed acquisition/disposition), or merger language in the body.</li>
          <li><strong>Schedule 13D</strong>: 5%+ ownership disclosures where the <em>subject company</em> is headquartered in Michigan.</li>
        </ul>
        <p>Filings are discovered with EDGAR full-text search (filtered to Michigan business addresses), then each primary document is downloaded and parsed. Requests carry a contact User-Agent and stay under SEC's 10 requests/second fair-access limit.</p>

        <h2>Classification rules</h2>
        <ul>
          <li><strong>Fundraise</strong>: any Form D (private placement or pooled fund).</li>
          <li><strong>M&amp;A</strong>: 8-K Item 2.01; 8-K with merger-agreement language (e.g. "Agreement and Plan of Merger", "stock purchase agreement", "tender offer"); or a Form D flagged as a business combination.</li>
          <li><strong>Material Agreement</strong>: other 8-K Item 1.01 filings, sub-typed by keyword (credit facility, debt offering, equity financing, employment, lease, commercial).</li>
          <li><strong>Stake</strong>: Schedule 13D and 13D/A.</li>
        </ul>
        <p>Asset-backed securitization trusts (SIC 6189, such as auto-loan trusts) are excluded because their 8-Ks are financing mechanics, not deals. Form D amendments are merged into one offering with a filing history.</p>

        <h2>No AI, by design</h2>
        <p>Summaries, classifications, deal values and the weekly talking points are produced by deterministic Python rules and templates. The app never calls an AI or LLM service, so the same filing always produces the same output.</p>

        <h2>Limitations</h2>
        <ul>
          <li>Form D amounts are self-reported and filed within 15 days of first sale. Many private deals never file one.</li>
          <li>8-K "value cited" is the largest dollar figure in the deal section of the filing: a parsed estimate (shown with ~), not a verified deal value.</li>
          <li>Location reflects the filer's business address on EDGAR. Michigan companies headquartered elsewhere are not included.</li>
          <li>Not investment advice. Always confirm details in the original filing.</li>
        </ul>
      </article>

      <div class="stack">
        <section class="card">
          <div class="card-head"><h2>Data status</h2></div>
          <dl class="kv">
            <dt>Last refresh</dt><dd>${meta.updated_at ? `${esc(relativeTime(meta.updated_at))}` : "—"}</dd>
            <dt>Coverage</dt><dd>${date(meta.earliest_filing)} – ${date(meta.latest_filing)}</dd>
            <dt>Total deals</dt><dd>${meta.deal_count ?? "—"}</dd>
            <dt>Fundraise</dt><dd>${counts.Fundraise ?? 0}</dd>
            <dt>M&amp;A</dt><dd>${counts["M&A"] ?? 0}</dd>
            <dt>Material agmts</dt><dd>${counts["Material Agreement"] ?? 0}</dd>
            <dt>Stakes</dt><dd>${counts.Stake ?? 0}</dd>
            <dt>Last run</dt><dd>${run.duration_seconds ?? "—"}s · ${run.requests ?? 0} SEC requests · ${(run.errors || []).length} errors</dd>
          </dl>
        </section>
        <section class="card prose" id="install">
          <div class="card-head"><h2>Install the app</h2></div>
          <p><strong>iPhone / iPad (Safari):</strong> tap Share → <em>Add to Home Screen</em>.</p>
          <p><strong>Android (Chrome):</strong> tap ⋮ → <em>Install app</em> (or use the Install button at the top).</p>
          <p><strong>Desktop (Chrome / Edge):</strong> click the install icon in the address bar, or the Install button at the top.</p>
          <p class="small muted" style="margin:0">Once installed, the last loaded data stays available offline.</p>
        </section>
        <section class="card prose">
          <div class="card-head"><h2>Built by</h2></div>
          <p style="margin:0">A portfolio project by a finance student focused on investment banking and private equity. Open source on <a href="https://github.com/VibecoderJB/michigan-deal-radar" target="_blank" rel="noopener">GitHub</a>. Data refreshes daily via GitHub Actions.</p>
        </section>
      </div>
    </div>`;
}
