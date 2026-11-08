"""Read/merge/write the deal history in ``data/deals.json``."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload, indent: int | None = 1) -> None:
    """Atomic write so a crash mid-run never leaves a truncated data file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=indent, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


def load_deals(path: Path | None = None) -> list[dict]:
    payload = read_json(path or config.DATA_DIR / "deals.json", default={"deals": []})
    return payload.get("deals", [])


def known_accessions(deals: list[dict]) -> set[str]:
    seen = set()
    for deal in deals:
        seen.add(deal.get("accession"))
        for filing in deal.get("filings", []):
            seen.add(filing.get("accession"))
    seen.discard(None)
    return seen


def merge_deals(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Upsert by ``id``. Form D amendments share an id (CIK + file number):
    the most recent filing wins and the full amendment history is kept."""
    by_id = {deal["id"]: deal for deal in existing}
    for deal in incoming:
        current = by_id.get(deal["id"])
        if current is None:
            by_id[deal["id"]] = deal
            continue
        history = {f["accession"]: f for f in current.get("filings", []) + deal.get("filings", [])}
        newer = deal if (deal["filed"], deal["accession"]) >= (current["filed"], current["accession"]) else current
        merged = dict(newer)
        if history:
            merged["filings"] = sorted(history.values(), key=lambda f: (f["filed"], f["accession"]))
            # Keep the original filing date so a deal is dated when it first appeared.
            merged["first_filed"] = merged["filings"][0]["filed"]
        by_id[deal["id"]] = merged
    return sort_deals(list(by_id.values()))


def sort_deals(deals: list[dict]) -> list[dict]:
    return sorted(deals, key=lambda d: (d.get("filed") or "", d.get("id")), reverse=True)


def save_deals(deals: list[dict], path: Path | None = None) -> None:
    write_json(
        path or config.DATA_DIR / "deals.json",
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "state": config.STATE_CODE,
            "count": len(deals),
            "deals": sort_deals(deals),
        },
    )
