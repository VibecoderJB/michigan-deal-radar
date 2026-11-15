// Deal table: search, filters, sortable columns, CSV export of the filtered view + full Excel workbook.
import { downloadCSV } from "../csv.js";
import { loadDeals, v } from "../data.js";
import { applyFilters, bindFilters, filterBar, readFilters, writeFilters } from "../filters.js";
import { date, esc, mm, money, ndHtml } from "../format.js";
import { confBadge, dealItem, emptyState, pageHead, statusBadge, toast } from "../ui.js";
import { starButton } from "../watchlist.js";

const PAGE = 50;
const COLS = [
  { key: "_date", label: "Announced" },
  { key: "title", label: "Deal" },
  { key: "type", label: "Type", get: (d) => v(d.deal_type) },
  { key: "status", label: "Status", get: (d) => v(d.status) },
  { key: "_region", label: "Region" },
  { key: "focus_sector", label: "Sector" },
  { key: "_value", label: "Value ($M)", right: true },
  { key: "confidence", label: "Conf." },
];
const DEFAULTS = { sort: "_date", dir: "desc" };

export async function renderDeals(root, params) {
  const { deals } = await loadDeals();
  const f = readFilters(params, {});
  f.sort = params.get("sort") || DEFAULTS.sort;
  f.dir = params.get("dir") || DEFAULTS.dir;
  let shown = PAGE;

  root.innerHTML = `
    ${pageHead("Deals", `Every Michigan deal in the dataset since ${esc(date(deals.at(-1)?._date) || "")}. Click a row for its tear sheet.`,
      `<a class="btn" href="reports/michigan-deal-radar.xlsx" download>Excel (full dataset)</a>
       <button class="btn btn-primary" id="export-csv" type="button">Export view (CSV)</button>`)}
    <section class="card filters">
      <input id="f-q" type="search" placeholder="Search target, acquirer, advisor, county…" value="${esc(f.q || "")}" aria-label="Search deals" autocomplete="off">
      ${filterBar(f, ["category", "type", "status", "sector", "region", "buyer", "from", "to", "min", "max"])}
      <div><button class="btn btn-sm" id="reset" type="button">Reset filters</button></div>
    </section>
    <div class="result-bar" id="result-bar" aria-live="polite"></div>
    <div class="table-wrap collapsible">
      <table class="data"><thead><tr>${COLS.map((c) => `<th scope="col" data-sort="${c.key}" class="${c.right ? "r" : ""}">${c.label}</th>`).join("")}<th scope="col"><span class="sr-only">Watch</span></th></tr></thead>
      <tbody id="rows"></tbody></table>
    </div>
    <div class="card-list" id="cards"></div>
    <div class="load-more"><button class="btn" id="more" type="button" hidden>Show more</button></div>`;

  let filtered = [];
  const getter = (key) => COLS.find((c) => c.key === key)?.get || ((d) => d[key]);

  function render() {
    const params = { ...f };
    writeFilters("deals", params);
    if (f.sort !== DEFAULTS.sort || f.dir !== DEFAULTS.dir) history.replaceState(null, "", `${location.hash}${location.hash.includes("?") ? "&" : "?"}sort=${f.sort}&dir=${f.dir}`);
    const get = getter(f.sort);
    const sign = f.dir === "asc" ? 1 : -1;
    filtered = applyFilters(deals, f).sort((a, b) => {
      const x = get(a), y = get(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * sign;
    });
    const page = filtered.slice(0, shown);
    const total = filtered.filter((d) => d.category === "M&A").reduce((s, d) => s + (d._value || 0), 0);
    root.querySelector("#result-bar").innerHTML = `<span><strong>${filtered.length}</strong> deals · <strong>${money(total, { empty: "$0" })}</strong> disclosed M&amp;A value</span><span>$ in millions · n.d. = not disclosed</span>`;
    root.querySelectorAll("th[data-sort]").forEach((th) => th.setAttribute("aria-sort", th.dataset.sort === f.sort ? (f.dir === "asc" ? "ascending" : "descending") : "none"));
    root.querySelector("#rows").innerHTML = page.length
      ? page.map((d) => `<tr class="clickable" data-id="${esc(d.deal_id)}" tabindex="0">
          <td class="num">${esc(date(d._date) || "")}</td>
          <td class="name">${esc(d.title)}</td>
          <td>${esc(v(d.deal_type) || "")}</td>
          <td>${statusBadge(v(d.status))}</td>
          <td>${esc(d._region || "—")}</td>
          <td>${esc(d.focus_sector || "—")}</td>
          <td class="r num">${d._value ? mm(d._value) : ndHtml("n.d.")}</td>
          <td>${confBadge(d.confidence)}</td>
          <td>${starButton(d)}</td></tr>`).join("")
      : `<tr><td colspan="9">${emptyState("No deals match these filters.")}</td></tr>`;
    root.querySelector("#cards").innerHTML = page.length ? page.map(dealItem).join("") : emptyState("No deals match these filters.");
    const more = root.querySelector("#more");
    more.hidden = filtered.length <= shown;
    more.textContent = `Show more (${filtered.length - shown} left)`;
  }

  const update = () => { shown = PAGE; render(); };
  bindFilters(root, f, update);
  let debounce;
  root.querySelector("#f-q").addEventListener("input", (e) => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { f.q = e.target.value.trim(); update(); }, 150);
  });
  root.querySelectorAll("th[data-sort]").forEach((th) => th.addEventListener("click", () => {
    f.dir = f.sort === th.dataset.sort && f.dir === "desc" ? "asc" : "desc";
    f.sort = th.dataset.sort;
    update();
  }));
  const open = (tr) => tr?.dataset.id && (location.hash = `#/deal/${encodeURIComponent(tr.dataset.id)}`);
  root.querySelector("#rows").addEventListener("click", (e) => { if (!e.target.closest("[data-star]")) open(e.target.closest("tr")); });
  root.querySelector("#rows").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.target.closest("[data-star]")) open(e.target.closest("tr")); });
  root.querySelector("#more").addEventListener("click", () => { shown += PAGE; render(); });
  root.querySelector("#reset").addEventListener("click", () => { location.hash = "#/deals"; });
  root.querySelector("#export-csv").addEventListener("click", () => {
    if (!filtered.length) return toast("Nothing to export");
    downloadCSV(filtered, `michigan-deal-radar-${new Date().toISOString().slice(0, 10)}.csv`);
    toast(`Exported ${filtered.length} deals`);
  });
  render();
}
