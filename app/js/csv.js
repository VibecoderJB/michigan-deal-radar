// CSV export of the currently filtered deal table.

const COLUMNS = [
  ["filed", "Filed"],
  ["type", "Type"],
  ["subtype", "Subtype"],
  ["company", "Company"],
  ["ticker", "Ticker"],
  ["city", "City"],
  ["sector", "Sector"],
  ["industry", "Industry"],
  ["amount", "Amount (USD)"],
  ["amount_sold", "Amount Sold (USD)"],
  ["amount_is_estimate", "Amount Parsed From Text"],
  ["counterparty", "Counterparty"],
  ["form", "Form"],
  ["summary", "Summary"],
  ["url", "SEC Filing URL"],
];

function cell(value) {
  if (value === null || value === undefined) return "";
  const s = String(value);
  // Neutralize spreadsheet formula injection, then quote when needed.
  const safe = /^[=+\-@]/.test(s) ? `'${s}` : s;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export function toCSV(deals) {
  const header = COLUMNS.map(([, label]) => label).join(",");
  const rows = deals.map((d) => COLUMNS.map(([key]) => cell(d[key])).join(","));
  return [header, ...rows].join("\r\n");
}

export function downloadCSV(deals, filename = "michigan-deals.csv") {
  const blob = new Blob(["﻿" + toCSV(deals)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(link);
  link.click();
  link.parentNode.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
