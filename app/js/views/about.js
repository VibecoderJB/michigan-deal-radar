// About & Methodology: sources, verification process, confidence scoring and known limitations.
import { loadMeta } from "../data.js";
import { date, esc, relativeTime } from "../format.js";
import { pageHead } from "../ui.js";

export async function renderAbout(root) {
  const meta = await loadMeta().catch(() => ({}));
  const run = meta.last_run || {};
  root.innerHTML = `
    ${pageHead("About &amp; Methodology", "How Michigan Deal Radar finds, verifies, classifies and scores Michigan deals.")}
    <div class="grid-2">
      <article class="card prose">
        <h2 style="margin-top:0">What this is</h2>
        <p>A free M&amp;A and private-capital intelligence tool for the Michigan middle market. Every number is traceable: each field stores the URL it came from and the exact source text, viewable by clicking <b>src</b> next to any value.</p>

        <h2>Sources</h2>
        <ul>
          <li><b>SEC EDGAR</b> (official API, full-text search, filing archives), filtered to Michigan-headquartered or Michigan-incorporated filers:
            8-K Items 1.01 / 1.02 / 2.01 and 8-Ks with merger language, S-4, DEFM14A, SC TO-T, SC 14D9, Form D, and Schedule 13D.</li>
          <li><b>Press-release wires</b>: PR Newswire, Business Wire and GlobeNewswire public RSS feeds, kept only when an item mentions Michigan and uses deal language.</li>
          <li><b>Michigan business news</b>: public RSS from Michigan outlets; for paywalled sites only the headline and link are stored.</li>
          <li><b>Firm watchlist</b> (<code>config/firms.yml</code>): Michigan-based and Michigan-active PE firms, banks, law firms and corporate acquirers, used to classify buyers and recognize advisors.</li>
        </ul>
        <p>Collection rules: official APIs and public RSS only; robots.txt is checked before every non-SEC request; no paywalled content; SEC fair-access rules (declared User-Agent with a contact, under 10 requests/second; this pipeline uses 6). Google News RSS is not used because its robots.txt disallows automated access.</p>

        <h2>Verification process</h2>
        <ul>
          <li><b>Rule-based extraction first.</b> Deal terms are taken only from sentences that name what the value is ("enterprise value of", "per share in cash", "EBITDA of"). Parties come from defined terms in the filing (e.g. <i>Grand River Commerce, Inc. ("Grand River")</i>).</li>
          <li><b>LLM gap-fill (optional).</b> Only where rules leave buyer/target roles unresolved. The model must return a verbatim quote; the answer is discarded unless that quote appears word-for-word in the source and contains the extracted name. Such fields are labeled "LLM-extracted, quote verified".</li>
          <li><b>Deduplication.</b> Filings about the same transaction (announcement, merger proxy, closing) are merged into one deal by the agreement's signing date, then by counterparty name; news reports join the matching SEC deal within 120 days.</li>
          <li><b>Never invent a number.</b> Undisclosed values show "Not disclosed". Computed values (e.g. EV/EBITDA from disclosed EV and EBITDA, or a filing date used as the closing date) are labeled <span class="est">EST.</span> or "Derived".</li>
        </ul>

        <h2>Confidence scoring</h2>
        <ul>
          <li><b>High</b>: an SEC filing or an official company press release.</li>
          <li><b>Medium</b>: reputable news reporting.</li>
          <li><b>Low</b>: a single unconfirmed report (e.g. "in talks", "exploring a sale").</li>
        </ul>
        <p>A deal takes the highest confidence among its sources.</p>

        <h2>Classification</h2>
        <ul>
          <li><b>Deal types</b>: Acquisition, Merger, PE Buyout, Add-on, Growth Equity, Venture Round, Recapitalization, Divestiture / Carve-out, IPO, Debt Raise.</li>
          <li><b>Form D</b> offerings by operating companies: Venture Round if the issuer was incorporated within five years, otherwise Growth Equity; debt-only offerings are Debt Raises. Pooled funds and real-estate vehicles go to <a href="#/capital">Private Capital</a>, not deal counts.</li>
          <li><b>Sectors</b>: SEC SIC codes and Form D industry groups are mapped to the closest GICS sector/sub-industry (GICS is proprietary; this is an approximation, labeled as such), then to Michigan focus sectors.</li>
          <li><b>Geography</b>: city or ZIP mapped to county by point-in-polygon on U.S. Census county boundaries; counties grouped into seven regions.</li>
        </ul>

        <h2>Known limitations</h2>
        <ul>
          <li>Most private middle-market deals never file with the SEC and many press releases omit terms, so value coverage is low and multiples are rare.</li>
          <li>Form D amounts are self-reported; one Form D can fund several transactions.</li>
          <li>RSS feeds only carry recent items, so news-sourced deals accumulate from launch; the 24-month history is SEC-based.</li>
          <li>Location is the filer's EDGAR address (or the issuer address on Form D). Michigan operations of out-of-state companies are missed.</li>
          <li>Rule-based role detection can fail on unusual structures; such deals are flagged "roles under review" on the <a href="#/quality">Data Quality</a> page.</li>
          <li>Not investment advice. Always confirm details against the linked source.</li>
        </ul>
      </article>
      <div class="stack">
        <section class="card"><div class="card-head"><h2>Data status</h2></div>
          <dl class="kv">
            <dt>Data as of</dt><dd>${esc(date(meta.data_as_of) || "—")}</dd>
            <dt>Last refresh</dt><dd>${esc(relativeTime(meta.updated_at) || "—")}</dd>
            <dt>Coverage from</dt><dd>${esc(date(meta.coverage_start) || "—")}</dd>
            <dt>Deals</dt><dd>${meta.counts?.deals ?? "—"}</dd>
            <dt>Fund raises</dt><dd>${meta.counts?.capital_formation ?? "—"}</dd>
            <dt>13D stakes</dt><dd>${meta.counts?.ownership ?? "—"}</dd>
            <dt>Evidence events</dt><dd>${meta.evidence_events ?? "—"}</dd>
            <dt>Last run</dt><dd>${run.duration_seconds ?? "—"}s · ${run.requests ?? 0} SEC requests</dd>
          </dl>
          <p class="small" style="margin-top:10px"><a href="#/quality">Full data-quality report →</a></p>
        </section>
        <section class="card prose" id="install"><div class="card-head"><h2>Install the app</h2></div>
          <p><b>Windows / Mac:</b> in Edge or Chrome, use the install icon in the address bar (Edge: ⋯ → Apps → Install this site as an app). Installed this way it isn't blocked by Smart App Control.</p>
          <p><b>iPhone:</b> Safari → Share → Add to Home Screen. <b>Android:</b> Chrome → ⋮ → Install app.</p>
          <p class="small muted" style="margin:0">After the first load, the last data stays available offline.</p>
        </section>
        <section class="card prose"><div class="card-head"><h2>Project</h2></div>
          <p style="margin:0">Open source on <a href="https://github.com/VibecoderJB/michigan-deal-radar" target="_blank" rel="noopener">GitHub</a>. Runs for $0: GitHub Actions (daily pipeline) and GitHub Pages (this app). Built as a portfolio project for investment banking and private equity recruiting.</p>
        </section>
      </div>
    </div>`;
}
