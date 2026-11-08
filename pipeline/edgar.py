"""EDGAR discovery helpers: full-text search paging and archive URL building."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterator

from . import config
from .sec_client import SecClient

log = logging.getLogger(__name__)

PAGE_SIZE = 100  # fixed by the EDGAR full-text search API
_DISPLAY_NAME_RE = re.compile(r"^(?P<name>.*?)\s*(?:\((?P<tickers>[A-Z0-9.\-, ]+)\))?\s*\(CIK (?P<cik>\d{10})\)$")


@dataclass
class FilingHit:
    """One filing (accession) discovered via full-text search."""

    accession: str
    form: str
    file_date: str
    ciks: list[str]
    entities: list[dict]  # [{name, tickers, cik, location, state}]
    items: list[str] = field(default_factory=list)
    sics: list[str] = field(default_factory=list)
    file_nums: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)  # filenames seen in hits
    primary_document: str | None = None


def parse_display_name(display: str) -> dict:
    """Split ``"DTE ENERGY CO  (DTE, DTW)  (CIK 0000936340)"`` into parts."""
    match = _DISPLAY_NAME_RE.match(display.strip())
    if not match:
        return {"name": display.strip(), "tickers": [], "cik": None}
    tickers = [t.strip() for t in (match.group("tickers") or "").split(",") if t.strip()]
    return {"name": match.group("name").strip(), "tickers": tickers, "cik": match.group("cik")}


def month_windows(start: date, end: date) -> Iterator[tuple[date, date]]:
    """Yield <=31-day windows so no single search exceeds the API's result cap."""
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=30), end)
        yield cursor, window_end
        cursor = window_end + timedelta(days=1)


def search_filings(
    client: SecClient,
    forms: str,
    start: date,
    end: date,
    query: str | None = None,
    location: str = config.STATE_CODE,
) -> list[FilingHit]:
    """Return filings (deduplicated by accession) matching the search.

    ``location`` filters on the state of the filer's principal business address.
    """
    by_accession: dict[str, FilingHit] = {}
    for win_start, win_end in month_windows(start, end):
        offset = 0
        while True:
            params = {
                "forms": forms,
                "locationCodes": location,
                "dateRange": "custom",
                "startdt": win_start.isoformat(),
                "enddt": win_end.isoformat(),
                "from": offset,
            }
            if query:
                params["q"] = query
            payload = client.get_json(config.FTS_URL, params)
            hits = payload.get("hits", {}).get("hits", [])
            for hit in hits:
                _merge_hit(by_accession, hit)
            total = payload.get("hits", {}).get("total", {}).get("value", 0)
            offset += PAGE_SIZE
            if not hits or offset >= total or offset >= 10_000:
                break
    log.info("FTS %s %s..%s q=%r -> %d filings", forms, start, end, query, len(by_accession))
    return sorted(by_accession.values(), key=lambda h: (h.file_date, h.accession), reverse=True)


def _merge_hit(store: dict[str, FilingHit], hit: dict) -> None:
    src = hit.get("_source", {})
    accession = src.get("adsh")
    if not accession:
        return
    filename = hit.get("_id", "").split(":", 1)[-1]
    existing = store.get(accession)
    if existing is None:
        locations = src.get("biz_locations") or []
        entities = []
        for i, display in enumerate(src.get("display_names") or []):
            entity = parse_display_name(display)
            loc = locations[i] if i < len(locations) else ""
            entity["location"] = loc
            entity["state"] = loc.rsplit(",", 1)[-1].strip() if "," in loc else ""
            entities.append(entity)
        existing = FilingHit(
            accession=accession,
            form=src.get("file_type") or src.get("form") or "",
            file_date=src.get("file_date") or "",
            ciks=list(src.get("ciks") or []),
            entities=entities,
            items=list(src.get("items") or []),
            sics=[str(x) for x in (src.get("sics") or [])],
            file_nums=list(src.get("file_num") or []),
        )
        store[accession] = existing
    if filename and filename not in existing.documents:
        existing.documents.append(filename)
    # The main document's file_type equals the form (exhibits are "EX-99.1" etc).
    if (src.get("file_type") or "") == (src.get("form") or "") and existing.primary_document is None:
        existing.primary_document = filename


def filing_folder_url(cik: str, accession: str) -> str:
    return f"{config.ARCHIVES_URL}/{int(cik)}/{accession.replace('-', '')}"


def filing_index_url(cik: str, accession: str) -> str:
    return f"{filing_folder_url(cik, accession)}/{accession}-index.htm"


def document_url(cik: str, accession: str, filename: str) -> str:
    return f"{filing_folder_url(cik, accession)}/{filename}"


_INDEX_ROW_RE = re.compile(
    r"<tr>\s*<td[^>]*>\d+</td>\s*<td[^>]*>[^<]*</td>\s*<td[^>]*><a href=\"[^\"]*?/([^/\"]+)\">[^<]*</a>.*?</td>\s*<td[^>]*>([^<]+)</td>",
    re.S,
)


def parse_index_documents(index_html: str) -> list[tuple[str, str]]:
    """Return ``[(filename, type), ...]`` from an EDGAR ``-index.htm`` page."""
    return [(m.group(1), m.group(2).strip()) for m in _INDEX_ROW_RE.finditer(index_html)]


def find_primary_document(client: SecClient, cik: str, accession: str, form: str) -> str | None:
    """Look up the main document when full-text search only matched an exhibit."""
    docs = parse_index_documents(client.get_text(filing_index_url(cik, accession)))
    for filename, doc_type in docs:
        if doc_type == form:
            return filename
    return docs[0][0] if docs else None
