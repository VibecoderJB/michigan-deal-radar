"""Pipeline entry point.

    python -m pipeline.run                    # daily incremental run (last 10 days)
    python -m pipeline.run --backfill 730     # rebuild 24 months of history
    python -m pipeline.run --rebuild          # re-derive datasets from stored evidence only (no network)

Order of operations: back up v1 data if present -> collect each source in isolation ->
merge evidence -> rebuild datasets -> analytics snapshot -> weekly briefings ->
data-quality report -> meta.json.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from datetime import date, timedelta

from . import __version__, config
from .analytics.metrics import snapshot
from .analytics.quality import quality_report, summary_line
from .reporting.briefing import generate_briefings
from .reporting.readme import update_readme
from .sources import news as news_source
from .sources import sec
from .storage.linking import build_datasets
from .storage.store import (
    known_event_ids,
    load_dataset,
    load_evidence,
    merge_evidence,
    read_json,
    save_dataset,
    save_evidence,
    utc_now,
    write_json,
)

log = logging.getLogger("pipeline")


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Michigan Deal Radar: SEC EDGAR + press-release pipeline")
    p.add_argument("--days", type=int, default=config.DEFAULT_LOOKBACK_DAYS, help="lookback window for incremental runs")
    p.add_argument("--backfill", type=int, metavar="DAYS", help="fetch this many days of history (730 = 24 months)")
    p.add_argument("--end", type=date.fromisoformat, default=None, help="end date (default: today)")
    p.add_argument("--refresh", action="store_true", help="re-extract filings already in the evidence ledger")
    p.add_argument("--skip", nargs="*", default=[], choices=["ma", "formd", "13d", "news"], help="sources to skip")
    p.add_argument("--rebuild", action="store_true", help="no network: rebuild datasets/briefings from stored evidence")
    p.add_argument("--reextract", action="store_true", help="no network: re-run extraction rules on stored filing text, then rebuild")
    p.add_argument("--rebuild-briefings", action="store_true", help="regenerate every weekly briefing")
    return p.parse_args(argv)


def backup_v1_data() -> list[set[str]] | None:
    """If deals.json is still schema v1, copy it (with meta and briefings) to data/backup/ first.

    Returns one set of accession numbers per v1 record so the quality report can prove nothing was lost.
    """
    current = read_json(config.DEALS_FILE, {}) or {}
    backups = sorted(config.BACKUP_DIR.glob("v1-*"))
    if current and current.get("schema_version", 1) < 2:
        dest = config.BACKUP_DIR / f"v1-{date.today().isoformat()}"
        if not dest.exists():
            dest.mkdir(parents=True)
            shutil.copy2(config.DEALS_FILE, dest / "deals.json")
            if config.META_FILE.exists():
                shutil.copy2(config.META_FILE, dest / "meta.json")
            if config.BRIEFINGS_DIR.exists():
                shutil.copytree(config.BRIEFINGS_DIR, dest / "briefings", dirs_exist_ok=True)
            log.info("Backed up v1 data to %s", dest)
        backups = [dest]
    if not backups:
        return None
    v1 = read_json(backups[-1] / "deals.json", {}) or {}
    records = []
    for d in v1.get("deals", []):
        acc = {d.get("accession")} | {f.get("accession") for f in d.get("filings") or []}
        acc.discard(None)
        records.append(acc)
    return records


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    args = parse_args(argv)
    started = time.monotonic()
    today = args.end or date.today()
    days = args.backfill or args.days
    start = today - timedelta(days=days)

    v1_accessions = backup_v1_data()
    previous_ids = {d.get("deal_id") for d in load_dataset(config.DEALS_FILE, "deals") if d.get("deal_id")}
    evidence = load_evidence()
    meta = read_json(config.META_FILE, {}) or {}
    run: dict = {"started_at": utc_now(), "window": [start.isoformat(), today.isoformat()], "sources": {}, "errors": []}

    if args.reextract:
        args.rebuild = True
        updated = 0
        for i, e in enumerate(evidence):
            if e["kind"] == "sec_ma":
                new = sec.reextract(e)
                if new is not None:
                    evidence[i] = new
                    updated += 1
        save_evidence(evidence)
        log.info("Re-extracted %d filings from stored text", updated)

    if not args.rebuild:
        known = set() if args.refresh else known_event_ids(evidence)
        new_events: list[dict] = []
        failed = attempted = 0
        try:
            client = sec.SecClient()
        except RuntimeError as exc:  # missing SEC_USER_AGENT: fail loudly, keep data untouched
            log.error("%s", exc)
            return 2
        collectors = {"ma": sec.collect_ma, "formd": sec.collect_form_d, "13d": sec.collect_13d}
        for name, collect in collectors.items():
            if name in args.skip:
                continue
            attempted += 1
            log.info("Collecting %s for %s..%s", name, start, today)
            try:
                res = collect(client, start, today, known)
            except Exception as exc:  # noqa: BLE001 - e.g. EDGAR search is down
                log.error("Source %s failed entirely: %s", name, exc)
                failed += 1
                run["sources"][name] = {"status": "failed", "error": str(exc)[:300]}
                continue
            new_events += res.events
            run["errors"] += res.errors
            run["sources"][name] = {"status": "ok", "seen": res.seen, "new": len(res.events), "skipped": res.skipped, "errors": len(res.errors)}
            log.info("%s: %d seen, %d new, %d skipped, %d errors", name, res.seen, len(res.events), res.skipped, len(res.errors))
        if "news" not in args.skip:
            attempted += 1
            try:
                res = news_source.collect_news(known)
                new_events += res.items
                run["errors"] += res.errors
                run["sources"]["news"] = {"status": "ok", "new": len(res.items), "feeds": res.feeds}
                log.info("news: %d new items from %d feeds", len(res.items), sum(1 for f in res.feeds if f["ok"]))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                run["sources"]["news"] = {"status": "failed", "error": str(exc)[:300]}
        run["requests"] = client.request_count
        evidence = merge_evidence(evidence, new_events)
        save_evidence(evidence)
        if attempted and failed == attempted:
            log.error("Every source failed; keeping existing datasets")
            _write_meta(meta, run, evidence, started, None)
            return 1

    news_items = [e for e in evidence if e["kind"] == "news"]
    sec_events = [e for e in evidence if e["kind"] != "news"]
    datasets = build_datasets(sec_events, news_items)
    save_dataset(config.DEALS_FILE, datasets["deals"], "deals")
    save_dataset(config.CAPITAL_FORMATION_FILE, datasets["capital_formation"], "records")
    save_dataset(config.OWNERSHIP_FILE, datasets["ownership"], "records")

    earliest = min((e["filed"] for e in sec_events), default=start.isoformat())
    candidates = [earliest] + ([meta["coverage_start"]] if meta.get("coverage_start") else []) + ([start.isoformat()] if args.backfill else [])
    coverage_start = date.fromisoformat(min(candidates))
    snap = snapshot(datasets["deals"], datasets["capital_formation"], datasets["ownership"], today)
    write_json(config.DATA_DIR / "analytics.json", snap)
    written = generate_briefings(datasets["deals"], datasets["capital_formation"], datasets["ownership"], today, coverage_start,
                                 force=args.rebuild_briefings)
    run["briefings_written"] = len(written)

    report = quality_report(
        datasets["deals"], previous_ids, len(evidence), run["errors"], run["sources"],
        v1_accessions, known_event_ids(evidence),
    )
    report.update({"generated_at": utc_now(), "window": run["window"]})
    write_json(config.QUALITY_DIR / "latest.json", report)
    history = read_json(config.QUALITY_DIR / "history.json", []) or []
    history.append({"at": report["generated_at"], "summary": summary_line(report), "new_deals": report["new_deal_count"],
                    "duplicates_merged": report["duplicates_merged"], "flagged": report["flagged_for_review_count"],
                    "errors": report["source_error_count"]})
    write_json(config.QUALITY_DIR / "history.json", history[-180:])

    meta["coverage_start"] = coverage_start.isoformat()
    _write_meta(meta, run, evidence, started, datasets)
    if config.DATA_DIR.resolve() == (config.ROOT_DIR / "data").resolve():
        update_readme()  # keep README "Key Findings" in sync with the published data
    log.info("Done: %s", summary_line(report))
    return 0


def _write_meta(meta: dict, run: dict, evidence: list[dict], started: float, datasets: dict | None) -> None:
    run["duration_seconds"] = round(time.monotonic() - started, 1)
    run["errors"] = run["errors"][:50]
    meta.update({
        "pipeline_version": __version__,
        "schema_version": 2,
        "last_run": run,
        "updated_at": utc_now(),
        "data_as_of": max((e["filed"] for e in evidence), default=None),
        "evidence_events": len(evidence),
        "state": config.STATE_NAME,
    })
    if datasets:
        meta["counts"] = {k: len(v) for k, v in datasets.items()}
    write_json(config.META_FILE, meta)


if __name__ == "__main__":
    sys.exit(main())
