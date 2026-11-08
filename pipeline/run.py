"""CLI entry point.

    python -m pipeline.run                  # daily incremental run (last 10 days)
    python -m pipeline.run --backfill 365   # rebuild the last 12 months
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from datetime import date, timedelta

from . import __version__, config
from .briefing import generate_briefings
from .collectors import collect_13d, collect_8k, collect_form_d
from .sec_client import SecClient
from .store import known_accessions, load_deals, merge_deals, read_json, save_deals, utc_now, write_json

log = logging.getLogger("pipeline")


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Michigan Deal Radar - SEC EDGAR pipeline")
    p.add_argument("--days", type=int, default=config.DEFAULT_LOOKBACK_DAYS, help="lookback window for incremental runs")
    p.add_argument("--backfill", type=int, metavar="DAYS", help="fetch this many days of history")
    p.add_argument("--end", type=date.fromisoformat, default=None, help="end date (default: today)")
    p.add_argument("--refresh", action="store_true", help="re-parse filings already in deals.json")
    p.add_argument("--skip", nargs="*", default=[], choices=["formd", "8k", "13d"], help="sources to skip")
    p.add_argument("--rebuild-briefings", action="store_true", help="regenerate every weekly briefing")
    p.add_argument("--briefings-only", action="store_true", help="only (re)generate briefings from deals.json")
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    args = parse_args(argv)
    started = time.monotonic()
    today = args.end or date.today()
    days = args.backfill or args.days
    start = today - timedelta(days=days)

    existing = load_deals()
    meta_path = config.DATA_DIR / "meta.json"
    meta = read_json(meta_path, {}) or {}

    run = {"started_at": utc_now(), "window": [start.isoformat(), today.isoformat()], "sources": {}, "errors": []}
    deals = existing
    if not args.briefings_only:
        client = SecClient()
        known = set() if args.refresh else known_accessions(existing)
        collectors = {"formd": collect_form_d, "8k": collect_8k, "13d": collect_13d}
        new_deals, failed_sources = [], 0
        for name, collect in collectors.items():
            if name in args.skip:
                continue
            log.info("Collecting %s for %s..%s", name, start, today)
            try:
                res = collect(client, start, today, known)
            except Exception as exc:  # noqa: BLE001 - e.g. EDGAR search is down
                log.error("Source %s failed entirely: %s", name, exc)
                failed_sources += 1
                run["sources"][name] = {"status": "failed", "error": str(exc)[:300]}
                continue
            new_deals.extend(res.deals)
            run["errors"].extend(res.errors)
            run["sources"][name] = {"status": "ok", "seen": res.seen, "new": len(res.deals), "skipped": res.skipped, "errors": len(res.errors)}
            log.info("%s: %d seen, %d new, %d skipped, %d errors", name, res.seen, len(res.deals), res.skipped, len(res.errors))
        deals = merge_deals(existing, new_deals)
        save_deals(deals)
        run["requests"] = client.request_count
        if failed_sources and failed_sources == len(collectors) - len(args.skip):
            log.error("Every source failed; keeping existing data")
            _write_meta(meta_path, meta, run, deals, started)
            return 1

    coverage_start = date.fromisoformat(meta["coverage_start"]) if meta.get("coverage_start") else (start if args.backfill else None)
    if args.backfill:
        coverage_start = min(coverage_start, start) if coverage_start else start
    written = generate_briefings(deals, today, force=args.rebuild_briefings, coverage_start=coverage_start)
    run["briefings_written"] = written
    meta["coverage_start"] = coverage_start.isoformat() if coverage_start else meta.get("coverage_start")
    _write_meta(meta_path, meta, run, deals, started)
    log.info("Done: %d deals total, %d briefings written, %d errors", len(deals), len(written), len(run["errors"]))
    return 0


def _write_meta(path, meta, run, deals, started) -> None:
    run["duration_seconds"] = round(time.monotonic() - started, 1)
    run["errors"] = run["errors"][:50]
    counts = Counter(d["type"] for d in deals)
    meta.update({
        "pipeline_version": __version__,
        "last_run": run,
        "updated_at": utc_now(),
        "deal_count": len(deals),
        "counts_by_type": dict(counts),
        "latest_filing": max((d["filed"] for d in deals), default=None),
        "earliest_filing": min((d["filed"] for d in deals), default=None),
        "state": config.STATE_NAME,
        "source": "SEC EDGAR full-text search + filing archives",
    })
    write_json(path, meta)


if __name__ == "__main__":
    sys.exit(main())
