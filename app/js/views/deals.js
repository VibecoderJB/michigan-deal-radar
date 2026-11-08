// Deal table: search, filter (type, sector, city, date range, amount), sort, CSV export.
// Filter state lives in the URL hash (#/deals?type=M%26A&sector=...) so views are shareable.
import { downloadCSV } from "../csv.js";
import { DEAL_TYPES, loadDeals } from "../data.js";
import { badge, date, esc, money } from "../format.js";
import { dealItem, emptyState, toast } from "../ui.js";
import { starButton } from "../watchlist.js";

const PAGE = 50;
const COLUMNS = [
  { key: "filed", label: "Filed" },
  { key: "company", label: "Company" },
  { key: "type", label: "Type" },
  { key: "subtype", label: "Detail" },
  { key: "city", label: "City" },
  { key: "sector", label: "Sector" },
  { key: "amount", label: "Amount", right: true },
  { key: "amount_sold", label: "Sold", right: true },
];

function readFilters(params) {
  return {
    q: params.get("q") || "",
    types: (params.get("type") || "").split(",").filter(Boolean),
    sector: params.get("sector") || "",
    city: params.get("city") || "",
    from: params.get("from") || "",
    to: params.get("to") || "",
    min: params.get("min") || "",
    max: params.get("max") || "",
    sort: params.get("sort") || "filed",
    dir: params.get("dir") || "desc",
  };
}

function writeFilters(f) {
  const params = new URLSearchParams();
  if (f.q) params.set("q", f.q);
  if (f.types.length) params.set("type", f.types.join(","));
  for (const key of ["sector", "city", "from", "to", "min", "max"]) if (f[key]) params.set(key, f[key]);
  if (f.sort !== "filed" || f.dir !== "desc") {
    params.set("sort", f.sort);
    params.set("dir", f.dir);
  }
  const qs = params.toString();
  history.replaceState(null, "", `#/deals${qs ? `?${qs}` : ""}`);
}

export function applyFilters(deals, f) {
  const terms = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  const min = f.min ? Number(f.min) * 1e6 : null;
  const max = f.max ? Number(f.max) * 1e6 : null;
  const out = deals.filter((d) => {
    if (f.types.length && !f.types.includes(d.type)) return false;
    if (f.sector && d.sector !== f.sector) return false;
    if (f.city && d.city !== f.city) return false;
    if (f.from && d.filed < f.from) return false;
    if (f.to && d.filed > f.to) return false;
    const amount = d.amount ?? d.amount_sold;
    if (min !== null && (amount == null || amount < min)) return false;
    if (max !== null && (amount == null || amount > max)) return false;
    return terms.every((t) => d._search.includes(t));
  });
  const sign = f.dir === "asc" ? 1 : -1;
  return out.sort((a, b) => {
    const av = a[f.sort];
    const bv = b[f.sort];
    if (av == null && bv == null) return 0;
    if (av == null) return 1; // blanks always last
    if (bv == null) return -1;
    return (typeof av === "number" ? av - bv : String(av).localeCompare(String(bv))) * sign;
  });
}

const options = (values, selected, placeholder) =>
  `<option value="">${placeholder}</option>` +
  values.map(([v, n]) => `<option value="${esc(v)}" ${v === selected ? "selected" : ""}>${esc(v)}${n ? ` (${n})` : ""}</option>`).join("");

const tally = (deals, key) =>
  Object.entries(deals.reduce((m, d) => (d[key] ? ((m[d[key]] = (m[d[key]] || 0) + 1), m) : m), {}));

export async function renderDeals(root, params) {
  const { deals } = await loadDeals();
  const f = readFilters(params);
  let shown = PAGE;
  const sectors = tally(deals, "sector").sort((a, b) => b[1] - a[1]);
  const cities = tally(deals, "city").sort((a, b) => a[0].localeCompare(b[0]));

  root.innerHTML = `
    <div class="page-head">
      <div><h1>Deals</h1><p>Every Michigan deal filing since ${date(deals.at(-1)?.filed)}. Tap a row for details.</p></div>
      <div class="page-actions">
        <button class="btn" id="reset-filters" type="button">Reset</button>
        <button class="btn btn-accent" id="export-csv" type="button"><svg viewBox="0 0 24 24"><path d="M5 20h14v-2H5v2zM19 9h-4V3H9v6H5l7 7 7-7z"/></svg>Export CSV</button>
      </div>
    </div>
    <section class="card filters" aria-label="Filters">
      <div class="search-row">
        <input id="f-q" type="search" placeholder="Search company, ticker, city, investor…" value="${esc(f.q)}" aria-label="Search deals" autocomplete="off">
      </div>
      <div class="chips" role="group" aria-label="Deal type">
        ${DEAL_TYPES.map((t) => `<button type="button" class="chip" data-type="${esc(t)}" aria-pressed="${f.types.includes(t)}">${esc(t)}</button>`).join("")}
      </div>
      <div class="filter-grid">
        <label class="field">Sector<select id="f-sector">${options(sectors, f.sector, "All sectors")}</select></label>
        <label class="field">City<select id="f-city">${options(cities, f.city, "All cities")}</select></label>
        <label class="field">From<input id="f-from" type="date" value="${esc(f.from)}"></label>
        <label class="field">To<input id="f-to" type="date" value="${esc(f.to)}"></label>
        <label class="field">Min amount ($M)<input id="f-min" type="number" inputmode="decimal" min="0" step="any" placeholder="0" value="${esc(f.min)}"></label>
        <label class="field">Max amount ($M)<input id="f-max" type="number" inputmode="decimal" min="0" step="any" placeholder="Any" value="${esc(f.max)}"></label>
      </div>
    </section>
    <div class="result-bar" aria-live="polite" id="result-bar"></div>
    <div class="table-wrap">
      <table class="deals">
        <thead><tr>${COLUMNS.map((c) => `<th scope="col" data-sort="${c.key}" class="${c.right ? "r" : ""}">${c.label}</th>`).join("")}<th class="nosort" scope="col"><span class="sr-only">Watch</span></th></tr></thead>
        <tbody id="deal-rows"></tbody>
      </table>
    </div>
    <div class="card-list" id="deal-cards"></div>
    <div class="load-more"><button class="btn" id="load-more" type="button" hidden>Show more</button></div>`;

  let filtered = [];
  const rowsEl = root.querySelector("#deal-rows");
  const cardsEl = root.querySelector("#deal-cards");
  const moreBtn = root.querySelector("#load-more");

  function render() {
    filtered = applyFilters(deals, f);
    const page = filtered.slice(0, shown);
    const total = filtered.reduce((s, d) => s + (d.type === "Fundraise" ? d.amount_sold || 0 : 0), 0);
    root.querySelector("#result-bar").innerHTML = `<span><strong>${filtered.length}</strong> deals · <strong>${money(total, { empty: "$0" })}</strong> raised (Form D)</span><span>Sorted by ${esc(COLUMNS.find((c) => c.key === f.sort)?.label || f.sort)} ${f.dir === "asc" ? "↑" : "↓"}</span>`;

    root.querySelectorAll("th[data-sort]").forEach((th) => {
      th.setAttribute("aria-sort", th.dataset.sort === f.sort ? (f.dir === "asc" ? "ascending" : "descending") : "none");
    });

    rowsEl.innerHTML = page.length
      ? page
          .map(
            (d) => `<tr data-id="${esc(d.id)}" tabindex="0">
              <td class="mono">${date(d.filed)}</td>
              <td class="co" title="${esc(d.company)}">${esc(d.company)}${d.ticker ? ` <span class="muted mono small">${esc(d.ticker)}</span>` : ""}</td>
              <td>${badge(d.type)}</td>
              <td class="muted">${esc(d.subtype || "")}</td>
              <td>${esc(d.city || "—")}</td>
              <td class="muted">${esc(d.sector || "—")}</td>
              <td class="r mono">${money(d.amount, { estimate: d.amount_is_estimate })}</td>
              <td class="r mono">${money(d.amount_sold)}</td>
              <td>${starButton(d.cik, d.company)}</td>
            </tr>`,
          )
          .join("")
      : `<tr><td colspan="9">${emptyState("No deals match these filters.")}</td></tr>`;
    cardsEl.innerHTML = page.length ? page.map((d) => dealItem(d)).join("") : emptyState("No deals match these filters.");
    moreBtn.hidden = filtered.length <= shown;
    moreBtn.textContent = `Show more (${filtered.length - shown} left)`;
  }

  const update = () => {
    shown = PAGE;
    writeFilters(f);
    render();
  };

  let debounce;
  root.querySelector("#f-q").addEventListener("input", (e) => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      f.q = e.target.value.trim();
      update();
    }, 150);
  });
  const bind = (id, key) => root.querySelector(id).addEventListener("change", (e) => {
    f[key] = e.target.value;
    update();
  });
  bind("#f-sector", "sector");
  bind("#f-city", "city");
  bind("#f-from", "from");
  bind("#f-to", "to");
  bind("#f-min", "min");
  bind("#f-max", "max");

  root.querySelectorAll(".chip[data-type]").forEach((chip) =>
    chip.addEventListener("click", () => {
      const t = chip.dataset.type;
      f.types = f.types.includes(t) ? f.types.filter((x) => x !== t) : [...f.types, t];
      chip.setAttribute("aria-pressed", f.types.includes(t));
      update();
    }),
  );

  root.querySelectorAll("th[data-sort]").forEach((th) =>
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      f.dir = f.sort === key && f.dir === "desc" ? "asc" : "desc";
      f.sort = key;
      update();
    }),
  );

  const openRow = (tr) => tr?.dataset.id && (location.hash = `#/deal/${encodeURIComponent(tr.dataset.id)}`);
  rowsEl.addEventListener("click", (e) => {
    if (e.target.closest("[data-star]")) return;
    openRow(e.target.closest("tr"));
  });
  rowsEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.target.closest("[data-star]")) openRow(e.target.closest("tr"));
  });

  moreBtn.addEventListener("click", () => {
    shown += PAGE;
    render();
  });

  root.querySelector("#reset-filters").addEventListener("click", () => {
    location.hash = "#/deals";
  });

  root.querySelector("#export-csv").addEventListener("click", () => {
    if (!filtered.length) return toast("Nothing to export");
    const stamp = new Date().toISOString().slice(0, 10);
    downloadCSV(filtered, `michigan-deal-radar-${stamp}.csv`);
    toast(`Exported ${filtered.length} deals to CSV`);
  });

  render();
}
