"""JSON persistence: atomic writes, dataset files, and the evidence ledger."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import config
from ..models import SCHEMA_VERSION


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: Any, indent: int | None = 1) -> None:
    """Atomic write: a crash mid-run never leaves a truncated data file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=indent, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


# ----------------------------------------------------------------------------- evidence ledger

def load_evidence(path: Path | None = None) -> list[dict]:
    payload = read_json(path or config.EVIDENCE_FILE, {"events": []}) or {"events": []}
    return payload.get("events", [])


def merge_evidence(existing: list[dict], new: list[dict]) -> list[dict]:
    """Upsert events by ``event_id`` (accession); newer extraction of the same filing wins."""
    by_id = {e["event_id"]: e for e in existing}
    for e in new:
        prior = by_id.get(e["event_id"])
        if prior and prior.get("llm") and not e.get("llm"):
            e["llm"] = prior["llm"]  # keep verified gap-fills across re-extraction
        by_id[e["event_id"]] = e
    return sorted(by_id.values(), key=lambda e: (e["filed"], e["event_id"]), reverse=True)


def save_evidence(events: list[dict], path: Path | None = None) -> None:
    write_json(path or config.EVIDENCE_FILE, {"schema_version": SCHEMA_VERSION, "generated_at": utc_now(), "count": len(events), "events": events}, indent=None)


def known_event_ids(events: list[dict]) -> set[str]:
    return {e["event_id"] for e in events}


# ----------------------------------------------------------------------------- datasets

def save_dataset(path: Path, records: list[dict], key: str, extra: dict | None = None) -> None:
    write_json(path, {"schema_version": SCHEMA_VERSION, "generated_at": utc_now(), "state": config.STATE_CODE,
                      "count": len(records), **(extra or {}), key: records})


def load_dataset(path: Path, key: str) -> list[dict]:
    return (read_json(path, {}) or {}).get(key, [])
