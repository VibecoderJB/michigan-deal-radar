// Shared UI components.
import { status as dataStatus, disclosed, v } from "./data.js";
import { date, esc, money, ND, ndHtml } from "./format.js";

const METHOD_LABEL = {
  filing_metadata: "Structured filing data",
  rule: "Rule-based extraction",
  derived: "Derived",
  llm_verified: "LLM-extracted, quote verified",
};
let provSeq = 0;

/**
 * Render a provenance field: formatted value + "src" footnote that expands to show
 * the exact source text, extraction method and a link to the source.
 */
export function fieldHtml(f, fmt = (x) => esc(x), { showSource = true } = {}) {
  if (!disclosed(f)) {
    const note = f?.note ? ` title="${esc(f.note)}"` : "";
    return `<span class="nd"${note}>${esc(f?.note === "Indefinite" ? "Indefinite" : ND)}</span>`;
  }
  const formatted = fmt(v(f));
  const est = f.estimate ? `<span class="est" title="${esc(f.note || "Estimate")}">EST.</span>` : "";
  if (!showSource || (!f.source_url && !f.source_text)) return `${formatted}${est}`;
  const id = `prov-${++provSeq}`;
  return `${formatted}${est}<button type="button" class="fn" data-prov="${id}" aria-expanded="false" aria-controls="${id}" title="Show source">src</button>
    <div class="prov" id="${id}" role="note">
      <div class="m">${esc(METHOD_LABEL[f.method] || f.method)}${f.note ? ` · ${esc(f.note)}` : ""}</div>
      ${f.source_text ? `<div>“${esc(f.source_text)}”</div>` : ""}
      ${f.source_url ? `<a href="${esc(f.source_url)}" target="_blank" rel="noopener">Open source ↗</a>` : ""}
    </div>`;
}

export const statusBadge = (s) => (s ? `<span class="badge status-${esc(s)}">${esc(s)}</span>` : "");
export const confBadge = (c) => (c ? `<span class="conf ${esc(c)}" title="Confidence: ${esc(c)}">${esc(c)}</span>` : "");
export const typeTag = (t) => (t ? `<span class="tag">${esc(t)}</span>` : "");

export function pageHead(title, subtitle, actions = "") {
  const asOf = dataStatus.asOf ? `Data as of ${date(dataStatus.asOf)}` : "";
  return `<div class="page-head">
    <div><h1>${title}</h1>${subtitle ? `<p>${subtitle}</p>` : ""}</div>
    <div class="page-actions">${actions}<span class="stamp">${esc(asOf)}</span></div>
  </div>`;
}

export function dealItem(d) {
  const amount = d._value;
  return `<a class="deal-item" href="#/deal/${encodeURIComponent(d.deal_id)}">
    <span class="deal-title">${esc(d.title)}</span>
    <span class="deal-amt">${amount ? money(amount) : ndHtml("n.d.")}</span>
    <span class="deal-meta">${statusBadge(v(d.status))}${typeTag(v(d.deal_type))}<span>${esc(d._region || "Michigan")}</span><span>·</span><span class="mono">${esc(date(d._date) || "")}</span>${confBadge(d.confidence)}</span>
  </a>`;
}

export function emptyState(message) {
  return `<div class="empty"><p>${message}</p></div>`;
}

export function barRows(rows, { format = (x) => x, href = null, accentFirst = true } = {}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length) return emptyState("No data for these filters.");
  return `<div class="bars">${rows
    .map((r, i) => {
      const tag = href ? "a" : "div";
      const link = href ? ` href="${href(r)}"` : "";
      return `<${tag} class="bar-row"${link}><span class="bar-label" title="${esc(r.label)}">${esc(r.label)}</span><span class="bar-track"><span class="bar-fill ${accentFirst && i === 0 ? "accent" : ""}" style="width:${((r.value / max) * 100).toFixed(1)}%"></span></span><span class="bar-val">${format(r.value)}</span></${tag}>`;
    })
    .join("")}</div>`;
}

export function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2200);
}

export const spinner = () => `<div class="spinner" role="progressbar" aria-label="Loading"></div>`;

export const SOURCE_NOTE = "Source: SEC EDGAR filings and public press releases, compiled by Michigan Deal Radar.";

/** Chart.js with the house style: title, labelled axes with units, mono ticks, source note under the canvas. */
const charts = new Map();
export function drawChart(canvasId, { type = "bar", labels, datasets, title, xTitle, yTitle, y1Title = null, yFormat = (x) => x, y1Format = (x) => x, tooltip }) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !window.Chart) return;
  charts.get(canvasId)?.destroy();
  const css = getComputedStyle(document.documentElement);
  const muted = css.getPropertyValue("--muted").trim();
  const line = css.getPropertyValue("--line").trim();
  const ink = css.getPropertyValue("--ink").trim();
  const mono = css.getPropertyValue("--mono").trim();
  const sans = css.getPropertyValue("--sans").trim();
  const axisTitle = (text) => ({ display: Boolean(text), text, color: muted, font: { family: sans, size: 11, weight: "600" } });
  const ticks = (fmt) => ({ color: muted, font: { family: mono, size: 10 }, callback: (val) => fmt(val), maxRotation: 0, autoSkip: true });
  const scales = {
    x: { grid: { display: false }, ticks: { color: muted, font: { family: mono, size: 10 }, maxRotation: 0, autoSkip: true }, title: axisTitle(xTitle) },
    y: { beginAtZero: true, grid: { color: line }, border: { display: false }, ticks: { ...ticks(yFormat), maxTicksLimit: 6 }, title: axisTitle(yTitle) },
  };
  if (y1Title) scales.y1 = { position: "right", beginAtZero: true, grid: { display: false }, border: { display: false }, ticks: { ...ticks(y1Format), maxTicksLimit: 6, precision: 0 }, title: axisTitle(y1Title) };
  const chart = new window.Chart(canvas, {
    type,
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        title: { display: true, text: title, align: "start", color: ink, font: { family: sans, size: 13, weight: "700" }, padding: { bottom: 12 } },
        legend: { display: datasets.length > 1, position: "bottom", labels: { color: muted, font: { family: sans, size: 11 }, boxWidth: 12 } },
        tooltip: { backgroundColor: "#0b1f3a", titleFont: { family: mono }, bodyFont: { family: mono }, callbacks: tooltip || {} },
      },
      scales,
    },
  });
  charts.set(canvasId, chart);
}

/** Wrapper markup for a chart: canvas + mandatory source note. */
export const chartBox = (id, note = "") => `<div class="chart-box"><canvas id="${id}" role="img"></canvas></div><div class="chart-note">${esc(note ? `${note} ` : "")}${SOURCE_NOTE}</div>`;
