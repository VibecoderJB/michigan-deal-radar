"""Build all downloadable reports into the site bundle.

    python -m pipeline.reporting.build --out _site/reports

Writes weekly PDFs (latest 26 weeks), quarterly PDFs (up to 8 completed quarters), the
banking-format Excel workbook, and ``index.json`` listing everything for the app.
Generated at deploy time (not committed) so the repo stays small.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from .. import config
from ..analytics.metrics import _last_quarters, quarter
from ..storage.store import load_dataset, read_json, utc_now, write_json
from .excel import build_workbook
from .pdf import html_to_pdf, quarterly_context, render_quarterly, render_weekly

log = logging.getLogger("reports")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=config.REPORTS_DIR)
    p.add_argument("--weeks", type=int, default=26)
    p.add_argument("--quarters", type=int, default=8)
    p.add_argument("--no-pdf", action="store_true", help="skip PDFs (Excel only)")
    args = p.parse_args(argv)

    deals = load_dataset(config.DEALS_FILE, "deals")
    cf = load_dataset(config.CAPITAL_FORMATION_FILE, "records")
    own = load_dataset(config.OWNERSHIP_FILE, "records")
    analytics = read_json(config.DATA_DIR / "analytics.json", {}) or {}
    meta = read_json(config.META_FILE, {}) or {}
    as_of = meta.get("data_as_of") or date.today().isoformat()
    index: dict = {"generated_at": utc_now(), "data_as_of": as_of, "weekly": [], "quarterly": [], "excel": []}
    errors = 0

    xlsx = build_workbook(deals, cf, analytics, args.out / "michigan-deal-radar.xlsx", as_of)
    index["excel"].append({"title": "Full dataset (M&A, precedents, financings, fund raises, league tables)", "path": f"reports/{xlsx.name}"})
    log.info("Wrote %s", xlsx)

    if not args.no_pdf:
        weeks = (read_json(config.BRIEFINGS_DIR / "index.json", {}) or {}).get("weeks", [])[: args.weeks]
        for w in weeks:
            out = args.out / "weekly" / f"michigan-deal-flow-{w['week_start']}.pdf"
            try:
                briefing = read_json(config.BRIEFINGS_DIR / f"{w['week_start']}.json")
                html_to_pdf(render_weekly(briefing, as_of), out)
                index["weekly"].append({"week_start": w["week_start"], "headline": w["headline"], "path": f"reports/weekly/{out.name}"})
            except Exception as exc:  # noqa: BLE001 - one bad report never blocks the deploy
                errors += 1
                log.warning("Weekly PDF %s failed: %s", w["week_start"], exc)

        coverage = meta.get("coverage_start") or as_of
        current_q = quarter(date.today().isoformat())
        completed = [q for q in _last_quarters(current_q, args.quarters + 1)[1:] if q >= quarter(coverage)]
        for q in completed:
            out = args.out / "quarterly" / f"michigan-ma-review-{q}.pdf"
            try:
                ctx = quarterly_context(q, deals, cf, own)
                html_to_pdf(render_quarterly(ctx, as_of), out)
                index["quarterly"].append({"quarter": q, "headline": ctx["headline"], "path": f"reports/quarterly/{out.name}"})
            except Exception as exc:  # noqa: BLE001
                errors += 1
                log.warning("Quarterly PDF %s failed: %s", q, exc)

    write_json(args.out / "index.json", index)
    log.info("Reports: %d weekly, %d quarterly, %d workbook(s), %d errors", len(index["weekly"]), len(index["quarterly"]), len(index["excel"]), errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
