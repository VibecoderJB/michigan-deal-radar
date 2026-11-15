// CSV export of the currently filtered deal table (v2 schema, $ in millions).
import { disclosedValue, v } from "./data.js";

const mmNum = (x) => (x == null ? "Not disclosed" : (x / 1e6).toFixed(1));
const ndv = (f) => (v(f) == null ? "Not disclosed" : v(f));

const COLUMNS = [
  ["Announced", (d) => d._date],
  ["Closed", (d) => ndv(d.closing_date)],
  ["Deal", (d) => d.title],
  ["Category", (d) => d.category],
  ["Deal Type", (d) => v(d.deal_type)],
  ["Status", (d) => v(d.status)],
  ["Target", (d) => ndv(d.target?.name)],
  ["Target County", (d) => ndv(d.target?.county)],
  ["Region", (d) => d._region || "Not disclosed"],
  ["Focus Sector", (d) => d.focus_sector || "Not disclosed"],
  ["GICS Sector", (d) => ndv(d.target?.gics_sector)],
  ["Acquirer / Investor", (d) => ndv(d.acquirer?.name)],
  ["Buyer Type", (d) => ndv(d.acquirer?.type)],
  ["Disclosed Value ($M)", (d) => mmNum(disclosedValue(d))],
  ["Amount Raised ($M)", (d) => mmNum(v(d.financials?.amount_raised))],
  ["EV/EBITDA", (d) => (v(d.financials?.ev_ebitda) == null ? "Not disclosed" : `${v(d.financials.ev_ebitda).toFixed(1)}x`)],
  ["Advisors", (d) => (d.advisors || []).map((a) => `${a.firm} (${a.role})`).join("; ")],
  ["Confidence", (d) => d.confidence],
  ["Deal ID", (d) => d.deal_id],
  ["Primary Source", (d) => d.sources?.[0]?.url],
];

function cell(value) {
  if (value === null || value === undefined) return "";
  const s = String(value);
  const safe = /^[=+\-@]/.test(s) ? `'${s}` : s; // neutralize spreadsheet formula injection
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export const toCSV = (deals) => [COLUMNS.map(([h]) => h).join(","), ...deals.map((d) => COLUMNS.map(([, fn]) => cell(fn(d))).join(","))].join("\r\n");

export function downloadCSV(deals, filename) {
  const blob = new Blob(["﻿" + toCSV(deals)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(link);
  link.click();
  link.parentNode.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
