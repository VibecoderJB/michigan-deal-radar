"""Keep the README's "Key Findings" section in sync with the data (run after each pipeline update).

Only the text between the KEY-FINDINGS markers is rewritten; every number comes from
``data/analytics.json`` and ``data/meta.json``.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import config
from ..storage.store import read_json
from ..textutil import money

START, END = "<!-- KEY-FINDINGS:START -->", "<!-- KEY-FINDINGS:END -->"


def key_findings_markdown(analytics: dict, meta: dict) -> str:
    s24, s12 = analytics.get("last_24_months", {}), analytics.get("last_12_months", {})
    lt = analytics.get("league_tables", {})
    counties = list((analytics.get("counties") or {}).items())[:3]
    sectors = sorted(analytics.get("sector_trends", []), key=lambda r: -r["trailing_4q"])[:3]
    prec = analytics.get("precedents", {})
    lines = [
        f"_Auto-generated from the dataset · data as of {meta.get('data_as_of', 'n/a')} · coverage from {meta.get('coverage_start', 'n/a')}_",
        "",
        "| Metric (trailing 24 months) | Value |",
        "|---|---|",
        f"| Michigan M&A deals tracked | **{s24.get('ma_deals', 0)}** ({s24.get('ma_closed', 0)} closed) |",
        f"| Deals with a disclosed value | {s24.get('ma_with_disclosed_value', 0)} ({money(s24.get('ma_disclosed_value'), '$0')} total) |",
        f"| Private financings (Form D / debt) | {s24.get('financings', 0)}, raising {money(s24.get('financing_raised'), '$0')} |",
        f"| Venture rounds | {s24.get('venture_rounds', 0)} |",
        f"| Michigan fund vehicles raising | {s24.get('fund_raises', 0)}, reporting {money(s24.get('fund_capital_raised'), '$0')} |",
        f"| Schedule 13D stakes in Michigan companies | {s24.get('stakes_13d', 0)} |",
        f"| Records sourced to SEC filings or official releases | {s24.get('high_confidence_share', 0)}% |",
        "",
    ]
    bullets = []
    if counties:
        bullets.append("Most active counties: " + ", ".join(f"{c} ({n})" for c, n in counties) + ".")
    if sectors:
        bullets.append("Most active focus sectors (trailing 4 quarters): " + ", ".join(f"{r['sector']} ({r['trailing_4q']})" for r in sectors) + ".")
    if lt.get("acquirers"):
        bullets.append("Most active acquirers: " + ", ".join(f"{r['name']} ({r['deals']})" for r in lt["acquirers"][:3]) + ".")
    if lt.get("financial_advisors"):
        bullets.append("Most active financial advisors: " + ", ".join(f"{r['name']} ({r['deals']})" for r in lt["financial_advisors"][:3]) + ".")
    if prec.get("ev_ebitda", {}).get("n"):
        e = prec["ev_ebitda"]
        bullets.append(f"Median disclosed EV/EBITDA across {e['n']} Michigan deals: {e['median']:.1f}x (mean {e['mean']:.1f}x).")
    bullets.append(f"Last 12 months: {s12.get('ma_deals', 0)} M&A deals and {s12.get('financings', 0)} private financings.")
    return "\n".join(lines + [f"- {b}" for b in bullets])


def update_readme(readme: Path | None = None) -> bool:
    readme = readme or config.ROOT_DIR / "README.md"
    if not readme.exists():
        return False
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return False
    body = key_findings_markdown(read_json(config.DATA_DIR / "analytics.json", {}) or {}, read_json(config.META_FILE, {}) or {})
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), f"{START}\n{body}\n{END}", text, flags=re.S)
    if new != text:
        readme.write_text(new, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    print("README updated" if update_readme() else "README unchanged")
