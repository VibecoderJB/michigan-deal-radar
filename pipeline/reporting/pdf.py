"""Render weekly and quarterly PDF reports (HTML templates -> headless Chrome print-to-PDF)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..analytics.metrics import (
    _last_quarters,
    deal_date,
    disclosed_value,
    headline_stats,
    is_ma,
    league_tables,
    period_series,
    precedent_transactions,
    sector_trends,
    sponsor_activity,
)
from ..models import val
from ..textutil import money
from .charts import bar_chart, hbar_chart

TEMPLATES = Path(__file__).with_name("templates")
SOURCE_NOTE = "SEC EDGAR filings and public press releases; Michigan Deal Radar"
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ----------------------------------------------------------------------------- formatting filters

def f_date(iso: str | None) -> str:
    if not iso:
        return "n.d."
    y, m, d = (int(x) for x in iso[:10].split("-"))
    return f"{_MONTHS[m - 1]} {d}, {y}"


def f_mm(v: float | None) -> str:
    return f"{(v or 0) / 1e6:,.1f}"


def f_mm_nd(v: float | None) -> str:
    return "n.d." if not v else f"{v / 1e6:,.1f}"


def f_pct(v: float | None) -> str:
    return "n.m." if v is None else f"{v:+.0f}%"


def f_x(v: float | None) -> str:
    return "n.d." if v is None else f"{v:.1f}x"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    env.filters.update({"date": f_date, "mm": f_mm, "mm_nd": f_mm_nd, "pct": f_pct, "x": f_x})
    return env


# ----------------------------------------------------------------------------- chrome

def find_chrome() -> str:
    candidates = [os.environ.get("MDR_CHROME"), "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                  "/opt/pw-browsers/chromium-1243/chrome-linux/chrome"]
    candidates += [str(p) for p in Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome")] if Path("/opt/pw-browsers").exists() else []
    for c in candidates:
        if c and (shutil.which(c) or Path(c).exists()):
            return shutil.which(c) or c
    raise RuntimeError("No Chrome/Chromium found for PDF rendering; set MDR_CHROME")


def html_to_pdf(html: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "report.html"
        src.write_text(html, encoding="utf-8")
        subprocess.run(
            [find_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={out}", src.as_uri()],
            check=True, capture_output=True, timeout=120,
        )


# ----------------------------------------------------------------------------- weekly

def render_weekly(briefing: dict, as_of: str) -> str:
    return _env().get_template("weekly.html").render(
        b=briefing, s=briefing["stats"], t=briefing["trailing_4wk"], ch=briefing["change_vs_trailing"],
        as_of=as_of, css=(TEMPLATES / "report.css").read_text(),
    )


# ----------------------------------------------------------------------------- quarterly

def _q_bounds(q: str) -> tuple[str, str]:
    y, k = int(q[:4]), int(q[-1])
    start = date(y, 3 * k - 2, 1)
    end = date(y + (k == 4), (3 * k) % 12 + 1, 1)
    return start.isoformat(), date.fromordinal(end.toordinal() - 1).isoformat()


def _pct(a: float, b: float) -> float | None:
    return round((a - b) / b * 100, 1) if b else None


def quarterly_context(q: str, deals: list[dict], cf: list[dict], own: list[dict]) -> dict:
    start, end = _q_bounds(q)
    prev = _last_quarters(q, 2)[1]
    ya = f"{int(q[:4]) - 1}-Q{q[-1]}"
    cur, pv, yv = (headline_stats(deals, cf, own, *_q_bounds(x)) for x in (q, prev, ya))
    keys = ("ma_deals", "ma_disclosed_value", "financings", "financing_raised", "fund_raises", "stakes_13d")
    qoq = {k: _pct(cur[k], pv[k]) for k in keys}
    yoy = {k: _pct(cur[k], yv[k]) for k in keys}
    q_end = date.fromisoformat(end)
    as_of_next = date.fromordinal(q_end.toordinal() + 1)
    sectors = [s for s in sector_trends(deals, as_of_next) if s["deals"] or s["prior_quarter"] or s["year_ago_quarter"]]

    q_deals = [d for d in deals if is_ma(d) and start <= deal_date(d) <= end]
    top = sorted(q_deals, key=lambda d: (disclosed_value(d) or 0, deal_date(d)), reverse=True)[:12]
    series = {r["period"]: r for r in period_series(deals, "quarter")}
    last8 = list(reversed(_last_quarters(q, 8)))
    lab = [f"{x[-1]}Q{x[2:4]}" for x in last8]  # banking style: 3Q26

    commentary = []
    commentary.append(f"Michigan recorded {cur['ma_deals']} M&A deals in {q.replace('-', ' ')}"
                      + (f", {('up' if qoq['ma_deals'] > 0 else 'down')} {abs(qoq['ma_deals']):.0f}% from {prev.replace('-', ' ')}" if qoq["ma_deals"] is not None else "")
                      + (f" and {('up' if yoy['ma_deals'] > 0 else 'down')} {abs(yoy['ma_deals']):.0f}% year over year." if yoy["ma_deals"] is not None else "."))
    if cur["ma_with_disclosed_value"]:
        commentary.append(f"{cur['ma_with_disclosed_value']} deals disclosed a value, totaling {money(cur['ma_disclosed_value'])}; "
                          f"most Michigan middle-market transactions do not disclose terms.")
    if top:
        commentary.append(f"Largest disclosed transaction: {top[0]['title']}" + (f" ({money(disclosed_value(top[0]))})." if disclosed_value(top[0]) else "."))
    commentary.append(f"Private financings: {cur['financings']} Form D/8-K financings raised {money(cur['financing_raised'])}, "
                      f"including {cur['venture_rounds']} venture rounds.")
    lead_sector = max(sectors, key=lambda s: s["deals"], default=None)
    if lead_sector and lead_sector["deals"]:
        commentary.append(f"{lead_sector['sector']} was the most active focus sector with {lead_sector['deals']} deals.")

    sources, seen = [], set()
    for d in top:
        for s in d.get("sources") or []:
            if s["url"] not in seen:
                seen.add(s["url"])
                sources.append(s)

    charts = {
        "count": bar_chart(lab, [series.get(x, {}).get("ma_count", 0) for x in last8], title="Michigan M&A deal count by quarter",
                           y_label="Deals (count)", x_label="Quarter (announcement date)", source=SOURCE_NOTE),
        "value": bar_chart(lab, [series.get(x, {}).get("ma_value", 0) / 1e6 for x in last8], title="Disclosed M&A value",
                           y_label="$ millions", x_label="Quarter", source=SOURCE_NOTE, fmt=lambda v: f"{v:,.0f}", width=320, height=240),
        "raised": bar_chart(lab, [series.get(x, {}).get("fin_raised", 0) / 1e6 for x in last8], title="Private financing raised",
                            y_label="$ millions", x_label="Quarter", source=SOURCE_NOTE, fmt=lambda v: f"{v:,.0f}", width=320, height=240),
        "sectors": hbar_chart([s["sector"] for s in sectors], [s["deals"] for s in sectors], title=f"Deals by focus sector, {q.replace('-', ' ')}",
                              x_label="Deals (count, M&A + financings)", source=SOURCE_NOTE),
    }
    lt_start = date(q_end.year - 1, q_end.month, min(q_end.day, 28)).isoformat()
    return {
        "label": q.replace("-", " "), "prev_label": prev.replace("-", " "), "yoy_label": ya.replace("-", " "),
        "start": start, "end": end, "cur": cur, "prev": pv, "ya": yv, "qoq": qoq, "yoy": yoy,
        "headline": commentary[0], "commentary": commentary, "sectors": sectors,
        "top_deals": [{"date": deal_date(d), "title": d["title"], "deal_type": val(d["deal_type"]), "status": val(d["status"]),
                       "value": disclosed_value(d), "ev_ebitda": val(d["financials"].get("ev_ebitda"))} for d in top],
        "precedents": precedent_transactions(deals),
        "league": league_tables([d for d in deals if lt_start <= deal_date(d) <= end], top=5),
        "sponsor": sponsor_activity(deals),
        "sources": sources,
        "charts": charts,
    }


def render_quarterly(ctx: dict, as_of: str) -> str:
    return _env().get_template("quarterly.html").render(q=ctx, charts=ctx["charts"], as_of=as_of, css=(TEMPLATES / "report.css").read_text())
