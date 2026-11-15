"""Banking-format Excel exports (openpyxl).

Conventions: cover tab, navy frozen header rows, $ in millions with one decimal
($#,##0.0), multiples as 8.5x, dates as mmm d, yyyy, "Not disclosed" for missing values,
estimates flagged in their own column, and a hyperlink to the source on every row.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..analytics.metrics import deal_date, disclosed_value, is_ma, precedent_transactions
from ..models import NOT_DISCLOSED, val

NAVY = "0B1F3A"
GOLD = "C8962E"
LIGHT = "EEF2F8"
HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
TITLE_FONT = Font(name="Calibri", bold=True, color=NAVY, size=14)
BODY_FONT = Font(name="Calibri", size=10)
LINK_FONT = Font(name="Calibri", size=10, color="1D4E89", underline="single")
THIN = Side(style="thin", color="D9DEE6")
FMT_MM = '$#,##0.0;($#,##0.0);"–"'
FMT_X = '0.0"x"'
FMT_DATE = "mmm d, yyyy"


def _to_date(iso: str | None):
    return date.fromisoformat(iso[:10]) if iso else None


def _mm(v):
    return None if v is None else v / 1e6


def _write_table(ws, start_row: int, columns: list[tuple[str, int, str | None]], rows: list[list], link_col: int | None = None) -> int:
    """columns: (header, width, number_format). Returns the next free row."""
    for c, (header, width, _) in enumerate(columns, 1):
        cell = ws.cell(row=start_row, column=c, value=header)
        cell.font, cell.fill = HEADER_FONT, PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center" if c > 1 else "left", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.row_dimensions[start_row].height = 30
    for r, row in enumerate(rows, start_row + 1):
        for c, value in enumerate(row, 1):
            fmt = columns[c - 1][2]
            if value is None and fmt in (FMT_MM, FMT_X, FMT_DATE):
                value = NOT_DISCLOSED if fmt != FMT_DATE else NOT_DISCLOSED
            cell = ws.cell(row=r, column=c, value=value)
            cell.font = BODY_FONT
            cell.border = Border(bottom=THIN)
            if fmt and not isinstance(value, str):
                cell.number_format = fmt
                cell.alignment = Alignment(horizontal="right")
            elif value == NOT_DISCLOSED:
                cell.font = Font(name="Calibri", size=10, italic=True, color="8A97AA")
                cell.alignment = Alignment(horizontal="right")
            if link_col and c == link_col and isinstance(value, str) and value.startswith("http"):
                cell.hyperlink = value
                cell.value = "Source"
                cell.font = LINK_FONT
            if (r - start_row) % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F6F8FB")
    ws.freeze_panes = ws.cell(row=start_row + 1, column=2)
    ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(columns))}{start_row + len(rows)}"
    return start_row + len(rows) + 1


def _title(ws, title: str, subtitle: str) -> int:
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws["A2"] = subtitle
    ws["A2"].font = Font(name="Calibri", size=9, italic=True, color="5B6B82")
    ws.sheet_view.showGridLines = False
    return 4


def _deal_row(d: dict) -> list:
    f = d.get("financials") or {}
    t, a = d.get("target") or {}, d.get("acquirer") or {}
    est = any((f.get(k) or {}).get("estimate") for k in ("ev_ebitda", "ev_revenue")) or (d.get("closing_date") or {}).get("estimate")
    return [
        _to_date(val(d.get("announcement_date"))), _to_date(val(d.get("closing_date"))),
        val(t.get("name"), NOT_DISCLOSED), val(t.get("county"), NOT_DISCLOSED), val(t.get("region"), NOT_DISCLOSED),
        val(t.get("gics_sector"), NOT_DISCLOSED), d.get("focus_sector") or NOT_DISCLOSED,
        val(a.get("name"), NOT_DISCLOSED), val(a.get("type"), NOT_DISCLOSED), "Yes" if val(a.get("is_add_on")) else "No",
        val(d.get("deal_type")), val(d.get("status")),
        _mm(val(f.get("enterprise_value"))), _mm(val(f.get("equity_value"))), _mm(val(f.get("transaction_value"))),
        _mm(val(f.get("revenue"))), _mm(val(f.get("ebitda"))), val(f.get("ev_revenue")), val(f.get("ev_ebitda")),
        val(f.get("consideration"), NOT_DISCLOSED),
        "; ".join(f"{x['firm']} ({x['role']})" for x in d.get("advisors") or []) or NOT_DISCLOSED,
        d.get("confidence"), "Yes" if est else "No", d["deal_id"], (d.get("sources") or [{}])[0].get("url"),
    ]


DEAL_COLUMNS = [
    ("Announced", 12, FMT_DATE), ("Closed", 12, FMT_DATE), ("Target", 30, None), ("County", 16, None), ("Region", 18, None),
    ("GICS Sector", 18, None), ("Focus Sector", 18, None), ("Acquirer / Investor", 30, None), ("Buyer Type", 15, None), ("Add-on", 8, None),
    ("Deal Type", 16, None), ("Status", 11, None), ("EV ($M)", 11, FMT_MM), ("Equity Value ($M)", 11, FMT_MM), ("Transaction Value ($M)", 12, FMT_MM),
    ("Revenue ($M)", 11, FMT_MM), ("EBITDA ($M)", 11, FMT_MM), ("EV / Revenue", 10, FMT_X), ("EV / EBITDA", 10, FMT_X),
    ("Consideration", 13, None), ("Advisors", 34, None), ("Confidence", 11, None), ("Contains Estimate", 10, None), ("Deal ID", 16, None), ("Source", 9, None),
]


def build_workbook(deals: list[dict], capital_formation: list[dict], analytics: dict, out: Path, as_of: str, only_ids: set[str] | None = None) -> Path:
    wb = Workbook()
    cover = wb.active
    cover.title = "Cover"
    cover.sheet_view.showGridLines = False
    cover.column_dimensions["A"].width = 4
    cover.column_dimensions["B"].width = 34
    cover.column_dimensions["C"].width = 70
    cover["B2"] = "Michigan Deal Radar"
    cover["B2"].font = Font(name="Calibri", bold=True, size=22, color=NAVY)
    cover["B3"] = "Michigan M&A and Private Capital Dataset"
    cover["B3"].font = Font(name="Calibri", size=13, color=GOLD, bold=True)
    s12 = analytics.get("last_12_months", {})
    info = [
        ("Data as of", as_of),
        ("Coverage", "Michigan-headquartered or Michigan-incorporated companies (target or acquirer)"),
        ("Sources", "SEC EDGAR (8-K Items 1.01/2.01, S-4, DEFM14A, SC TO-T, SC 14D9, Form D, Schedule 13D); public press releases and news RSS"),
        ("Units", "$ in millions (one decimal); multiples as x; dates mmm d, yyyy"),
        ("Not disclosed", "Value not stated by any source. Never estimated or filled in."),
        ("Estimates", "Flagged in 'Contains Estimate' (e.g. multiples using transaction value as an EV proxy)."),
        ("Confidence", "High = SEC filing or official press release; Medium = reputable news; Low = single unconfirmed report"),
        ("M&A deals, last 12 months", s12.get("ma_deals")),
        ("Private financings, last 12 months", s12.get("financings")),
        ("Provenance", "Every field's source URL and verbatim source text is in data/deals.json and the app's deal tear sheets."),
    ]
    for i, (k, v) in enumerate(info, 5):
        cover.cell(row=i, column=2, value=k).font = Font(name="Calibri", bold=True, color=NAVY)
        c = cover.cell(row=i, column=3, value=v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for i in range(2, 16):
        cover.cell(row=i, column=1).fill = PatternFill("solid", fgColor=NAVY)

    pool = [d for d in deals if not only_ids or d["deal_id"] in only_ids]
    ma = sorted((d for d in pool if is_ma(d)), key=deal_date, reverse=True)
    fin = sorted((d for d in pool if d.get("category") == "Financing"), key=deal_date, reverse=True)

    ws = wb.create_sheet("M&A")
    _write_table(ws, _title(ws, "Michigan M&A Transactions", f"$ in millions · Data as of {as_of} · Not disclosed = not stated by any source"),
                 DEAL_COLUMNS, [_deal_row(d) for d in ma], link_col=len(DEAL_COLUMNS))

    ws = wb.create_sheet("Precedents")
    row = _title(ws, "Precedent Transactions", "Michigan deals with a disclosed value or multiple · $ in millions")
    prec_ids = set(precedent_transactions(pool)["deal_ids"])
    prec = [d for d in ma if d["deal_id"] in prec_ids]
    cols = [("Announced", 12, FMT_DATE), ("Target", 30, None), ("Acquirer", 30, None), ("Deal Type", 16, None), ("Status", 11, None),
            ("EV ($M)", 11, FMT_MM), ("Transaction Value ($M)", 12, FMT_MM), ("Revenue ($M)", 11, FMT_MM), ("EBITDA ($M)", 11, FMT_MM),
            ("EV / Revenue", 11, FMT_X), ("EV / EBITDA", 11, FMT_X), ("Source", 9, None)]
    rows = []
    for d in prec:
        f = d["financials"]
        rows.append([_to_date(val(d["announcement_date"])), val(d["target"]["name"], NOT_DISCLOSED), val(d["acquirer"]["name"], NOT_DISCLOSED),
                     val(d["deal_type"]), val(d["status"]), _mm(val(f.get("enterprise_value"))), _mm(val(f.get("transaction_value"))),
                     _mm(val(f.get("revenue"))), _mm(val(f.get("ebitda"))), val(f.get("ev_revenue")), val(f.get("ev_ebitda")), d["sources"][0]["url"]])
    nxt = _write_table(ws, row, cols, rows, link_col=len(cols))
    stats = precedent_transactions(pool)
    for label, key in (("Median", "median"), ("Mean", "mean"), ("High", "high"), ("Low", "low")):
        ws.cell(row=nxt, column=2, value=label).font = Font(name="Calibri", bold=True)
        for col, metric, fmt in ((10, "ev_revenue", FMT_X), (11, "ev_ebitda", FMT_X), (6, "value", FMT_MM)):
            v = stats[metric][key]
            c = ws.cell(row=nxt, column=col, value=(v / 1e6 if metric == "value" and v is not None else v) if v is not None else "n.d.")
            c.number_format = fmt
            c.font = Font(name="Calibri", bold=True)
            c.alignment = Alignment(horizontal="right")
        for col in range(1, len(cols) + 1):
            ws.cell(row=nxt, column=col).fill = PatternFill("solid", fgColor=LIGHT)
            ws.cell(row=nxt, column=col).border = Border(top=Side(style="thin", color=NAVY) if key == "median" else THIN)
        nxt += 1
    ws.cell(row=nxt + 1, column=2, value=f"N (EV/EBITDA) = {stats['ev_ebitda']['n']}; N (EV/Revenue) = {stats['ev_revenue']['n']}. Only disclosed or arithmetically derived multiples.").font = Font(name="Calibri", italic=True, size=9, color="5B6B82")

    ws = wb.create_sheet("Financings")
    cols = [("Announced", 12, FMT_DATE), ("Company", 32, None), ("City", 16, None), ("County", 16, None), ("Region", 18, None), ("Focus Sector", 18, None),
            ("Deal Type", 16, None), ("Status", 11, None), ("Amount Raised ($M)", 12, FMT_MM), ("Offering Size ($M)", 12, FMT_MM), ("Investors (#)", 10, "0"),
            ("Deal ID", 16, None), ("Source", 9, None)]
    rows = [[_to_date(val(d["announcement_date"])), val(d["target"]["name"], NOT_DISCLOSED), val(d["target"].get("city"), NOT_DISCLOSED),
             val(d["target"].get("county"), NOT_DISCLOSED), val(d["target"].get("region"), NOT_DISCLOSED), d.get("focus_sector") or NOT_DISCLOSED,
             val(d["deal_type"]), val(d["status"]), _mm(val(d["financials"].get("amount_raised"))), _mm(val(d["financials"].get("offering_size"))),
             val(d["financials"].get("investor_count")), d["deal_id"], d["sources"][0]["url"]] for d in fin]
    _write_table(ws, _title(ws, "Michigan Private Financings", f"Form D offerings and 8-K debt financings · $ in millions · Data as of {as_of}"), cols, rows, link_col=len(cols))

    if not only_ids:
        ws = wb.create_sheet("Fund Raises")
        cols = [("Last Filed", 12, FMT_DATE), ("Fund / Vehicle", 40, None), ("Category", 22, None), ("City", 16, None), ("County", 16, None),
                ("Amount Raised ($M)", 12, FMT_MM), ("Offering Size ($M)", 12, FMT_MM), ("Investors (#)", 10, "0"), ("Source", 9, None)]
        rows = [[_to_date(c["filed"]), val(c["name"]), val(c["category"]), val(c.get("city"), NOT_DISCLOSED), val(c.get("county"), NOT_DISCLOSED),
                 _mm(val(c["amount_raised"])), _mm(val(c["offering_size"])), val(c["investor_count"]), c["sources"][-1]["url"]] for c in capital_formation]
        _write_table(ws, _title(ws, "Michigan Fund and Real Estate Vehicles (Form D)", "Kept separate from deal counts · $ in millions"), cols, rows, link_col=len(cols))

        ws = wb.create_sheet("League Tables")
        row = _title(ws, "League Tables: Michigan M&A", "Trailing 24 months · counts of SEC- or press-release-sourced deals")
        lt = analytics.get("league_tables", {})
        col = 1
        for key, label in (("acquirers", "Acquirers"), ("sponsors", "PE Sponsors"), ("financial_advisors", "Financial Advisors"), ("legal_advisors", "Legal Advisors")):
            ws.cell(row=row, column=col, value=label).font = Font(name="Calibri", bold=True, color=NAVY, size=11)
            for i, h in enumerate(("Rank", "Firm", "Deals")):
                c = ws.cell(row=row + 1, column=col + i, value=h)
                c.font, c.fill = HEADER_FONT, PatternFill("solid", fgColor=NAVY)
            for r, entry in enumerate(lt.get(key, [])[:15], row + 2):
                ws.cell(row=r, column=col, value=r - row - 1)
                ws.cell(row=r, column=col + 1, value=entry["name"])
                ws.cell(row=r, column=col + 2, value=entry["deals"])
            ws.column_dimensions[get_column_letter(col + 1)].width = 34
            col += 4

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
