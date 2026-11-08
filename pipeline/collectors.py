"""Collectors: discover filings, fetch documents, parse, and build deals.

Every filing is processed inside its own try/except: one malformed filing is
logged to the run's error list and skipped, never crashing the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from . import config
from .deals import build_13d_deal, build_8k_deal, build_form_d_deal, is_abs_vehicle
from .edgar import FilingHit, document_url, find_primary_document, search_filings
from .eightk import DEAL_ITEMS, analyze_8k
from .formd import parse_form_d
from .schedule13d import parse_schedule_13d
from .sec_client import SecClient

log = logging.getLogger(__name__)

MERGER_QUERY = '"agreement and plan of merger" OR "merger agreement" OR "business combination agreement" OR "definitive agreement to acquire"'


@dataclass
class CollectResult:
    deals: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    skipped: int = 0
    seen: int = 0

    def fail(self, hit: FilingHit, source: str, exc: Exception) -> None:
        log.warning("Skipping %s %s: %s", source, hit.accession, exc)
        self.errors.append({"source": source, "accession": hit.accession, "error": f"{type(exc).__name__}: {exc}"[:300]})


def collect_form_d(client: SecClient, start: date, end: date, known: set[str]) -> CollectResult:
    result = CollectResult()
    hits = search_filings(client, "D", start, end)
    for hit in hits:
        result.seen += 1
        if hit.accession in known:
            result.skipped += 1
            continue
        try:
            doc = hit.primary_document or "primary_doc.xml"
            parsed = parse_form_d(client.get_text(document_url(hit.ciks[0], hit.accession, doc)))
            if parsed.get("state") != config.STATE_CODE:
                result.skipped += 1  # FTS matched a related entity, not the primary issuer
                continue
            result.deals.append(build_form_d_deal(hit, parsed, doc))
        except Exception as exc:  # noqa: BLE001 - isolate every filing
            result.fail(hit, "Form D", exc)
    return result


def collect_8k(client: SecClient, start: date, end: date, known: set[str]) -> CollectResult:
    result = CollectResult()
    by_item = [h for h in search_filings(client, "8-K", start, end) if set(h.items) & DEAL_ITEMS]
    by_text = search_filings(client, "8-K", start, end, query=MERGER_QUERY)
    candidates = {h.accession: h for h in by_text + by_item}
    for hit in candidates.values():
        result.seen += 1
        if hit.accession in known or is_abs_vehicle(hit):
            result.skipped += 1
            continue
        try:
            if not hit.primary_document:
                hit.primary_document = find_primary_document(client, hit.ciks[0], hit.accession, hit.form or "8-K")
                if not hit.primary_document:
                    raise ValueError("could not locate the primary 8-K document")
            company = hit.entities[0]["name"] if hit.entities else ""
            raw = client.get_text(document_url(hit.ciks[0], hit.accession, hit.primary_document))
            analysis = analyze_8k(raw, hit.items, company)
            if analysis["type"] is None:
                result.skipped += 1  # mentions a merger but isn't a deal (e.g. earnings release)
                continue
            result.deals.append(build_8k_deal(hit, analysis))
        except Exception as exc:  # noqa: BLE001
            result.fail(hit, "8-K", exc)
    return result


def collect_13d(client: SecClient, start: date, end: date, known: set[str]) -> CollectResult:
    """Schedule 13D where the *subject company* is headquartered in Michigan."""
    result = CollectResult()
    for hit in search_filings(client, "SCHEDULE 13D", start, end):
        result.seen += 1
        subject = hit.entities[0] if hit.entities else {}
        if hit.accession in known or subject.get("state") != config.STATE_CODE:
            result.skipped += 1  # Michigan filer investing elsewhere -> not a Michigan deal
            continue
        try:
            raw = client.get_text(document_url(hit.ciks[0], hit.accession, hit.primary_document or "primary_doc.xml"))
            parsed = parse_schedule_13d(raw)
            if parsed.get("issuer_state") and parsed["issuer_state"] != config.STATE_CODE:
                result.skipped += 1
                continue
            result.deals.append(build_13d_deal(hit, parsed, subject))
        except Exception as exc:  # noqa: BLE001
            result.fail(hit, "Schedule 13D", exc)
    return result
