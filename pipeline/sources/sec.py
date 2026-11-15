"""SEC EDGAR source adapters: discover filings and turn each one into an *evidence event*.

An evidence event is the audit trail for one filing: what we fetched, what we extracted,
and the exact text each value came from. Deals are rebuilt from events on every run
(see ``storage/linking.py``), so improving a rule re-derives history consistently.

Every filing is processed in isolation: an exception is logged into the run's error list
and that filing is skipped. One bad filing never stops the pipeline.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
from dataclasses import asdict, dataclass, field as dc_field
from datetime import date

from .. import config
from ..extraction import llm
from ..extraction import terms as T
from ..extraction.eightk import analyze_8k, classify_agreement, extract_sections
from ..extraction.formd import parse_form_d
from ..extraction.htmltext import clip, html_to_text
from ..extraction.schedule13d import parse_schedule_13d
from ..ingestion.edgar import (
    FilingHit,
    document_url,
    filing_index_url,
    find_primary_document,
    parse_index_documents,
    search_filings,
)
from ..ingestion.sec_client import SecClient  # re-exported for run.py
from ..models import field
from ..textutil import display_name

log = logging.getLogger(__name__)

MERGER_QUERY = (
    '"agreement and plan of merger" OR "merger agreement" OR "business combination agreement" '
    'OR "definitive agreement to acquire" OR "purchase agreement"'
)
# Forms filed around a merger; all imply the deal is at least pending.
MERGER_FORMS = ("S-4", "DEFM14A", "SC TO-T", "SC 14D9")
DEAL_8K_ITEMS = {"1.01", "1.02", "2.01"}
MAX_TEXT_CHARS = 600_000

_ABS_NAME_RE = re.compile(r"\b(trust 20\d\d|master owner trust|receivables|lease trust|auto lease|securitization|funding (?:llc|i+\b))", re.I)


@dataclass
class SourceResult:
    events: list[dict] = dc_field(default_factory=list)
    errors: list[dict] = dc_field(default_factory=list)
    seen: int = 0
    skipped: int = 0

    def fail(self, accession: str, source: str, exc: Exception) -> None:
        log.warning("Skipping %s %s: %s", source, accession, exc)
        self.errors.append({"source": source, "accession": accession, "error": f"{type(exc).__name__}: {exc}"[:300]})


def is_abs_vehicle(hit: FilingHit) -> bool:
    name = hit.entities[0]["name"] if hit.entities else ""
    return "6189" in hit.sics or bool(_ABS_NAME_RE.search(name))


def _filer(hit: FilingHit, prefer_state: str = config.STATE_CODE) -> dict:
    """The Michigan entity on a filing (first entity with a Michigan address, else the first)."""
    ents = hit.entities or [{"name": "", "tickers": [], "cik": hit.ciks[0] if hit.ciks else None, "location": "", "state": ""}]
    ent = next((e for e in ents if e.get("state") == prefer_state), ents[0])
    tickers = ent.get("tickers") or []
    return {
        "name": ent.get("name"),
        "cik": (ent.get("cik") or (hit.ciks[0] if hit.ciks else "")).lstrip("0"),
        "tickers": tickers,
        "city": (ent.get("location") or "").split(",")[0].strip() or None,
        "state": ent.get("state") or None,
        "sic": hit.sics[0] if hit.sics else None,
        "inc_state": hit.inc_states[0] if hit.inc_states else None,
    }


def _base_event(hit: FilingHit, kind: str, doc: str | None) -> dict:
    filer = _filer(hit)
    cik = filer["cik"] or hit.ciks[0].lstrip("0")
    return {
        "event_id": hit.accession,
        "kind": kind,
        "form": hit.form,
        "items": hit.items,
        "filed": hit.file_date,
        "url": filing_index_url(cik, hit.accession),
        "doc_url": document_url(cik, hit.accession, doc) if doc else None,
        "filer": filer,
        "entities": [{"name": e.get("name"), "cik": (e.get("cik") or "").lstrip("0"), "state": e.get("state"), "tickers": e.get("tickers")} for e in hit.entities],
    }


# ----------------------------------------------------------------------------- M&A filings

def _press_release(client: SecClient, cik: str, accession: str) -> tuple[str | None, str]:
    """Fetch EX-99.1 (press release) if the filing has one. Returns (url, text)."""
    docs = parse_index_documents(client.get_text(filing_index_url(cik, accession)))
    for filename, doc_type in docs:
        if doc_type.upper().startswith("EX-99") and filename.lower().endswith((".htm", ".html", ".txt")):
            url = document_url(cik, accession, filename)
            return url, html_to_text(client.get_text(url))[:MAX_TEXT_CHARS]
    return None, ""


def analyze_ma_filing(hit: FilingHit, main_text: str, main_url: str, pr_text: str = "", pr_url: str | None = None) -> dict | None:
    """Build an M&A / material-agreement evidence event from already-fetched text.

    Pure function (no network) so it can be unit-tested on real filings.
    """
    event = _base_event(hit, "sec_ma", None)
    event["doc_url"] = main_url
    filer = event["filer"]
    form = (hit.form or "").upper()
    if form.startswith("8-K"):
        analysis = analyze_8k(main_text if "<" not in main_text[:200] else main_text, hit.items, filer["name"] or "")
        text = html_to_text(main_text) if "<" in main_text[:2000] else main_text
        sections = extract_sections(text)
        if analysis["type"] is None and "1.02" not in hit.items:
            return None
        if "1.02" in hit.items and not re.search(r"merger|acquisition|purchase agreement|business combination", sections.get("1.02", ""), re.I):
            return None
        deal_text = " \n".join(sections.get(i, "") for i in ("2.01", "1.01", "1.02", "8.01", "7.01")) or text
        category = analysis["type"] or "M&A"
        subtype = analysis["subtype"] or "Termination"
        excerpt = analysis["excerpt"]
    else:
        text = html_to_text(main_text) if "<" in main_text[:2000] else main_text
        deal_text = text[:MAX_TEXT_CHARS]
        category, subtype, excerpt = "M&A", f"{form} filed", clip(deal_text[:3000], 420)

    combined = deal_text + "\n" + pr_text
    party = T.Party.from_text(display_name(filer["name"]) or "", combined)
    event.update({"category": category, "subtype": subtype, "excerpt": excerpt, "press_release_url": pr_url})

    if category == "Material Agreement":
        kind = classify_agreement(deal_text)
        event["agreement_kind"] = kind
        facility = _facility_amount(deal_text, main_url)
        event["facility_amount"] = facility
        event["lenders"] = [a for a in T.extract_advisors(deal_text, main_url, party) if a["role"] == "lender"]
        event["status"] = field("Closed", main_url, T.sentences(deal_text)[0] if T.sentences(deal_text) else excerpt)
        return event

    # Status: explicit item/form signals first, then language.
    if "1.02" in hit.items:
        status = field("Terminated", main_url, clip(sections.get("1.02", excerpt), 400), "filing_metadata", note="8-K Item 1.02")
    elif "2.01" in hit.items:
        status = field("Closed", main_url, clip(sections.get("2.01", excerpt), 400), "filing_metadata", note="8-K Item 2.01")
    elif form.startswith(MERGER_FORMS):
        status = field("Pending", main_url, f"{hit.form} filed {hit.file_date}", "filing_metadata", note="merger registration/proxy/tender filing")
    else:
        found = T.status_from_text(deal_text)
        status = field(found[0], main_url, found[1]) if found else field("Announced", main_url, excerpt, note="8-K Item 1.01 agreement")
    event["status"] = status

    role = T.filer_role(combined, party, hit.form)
    event["role"] = field(role[0], main_url, role[1]) if role else field(None)
    cp = None
    if role and role[0] == "acquirer":
        cp = T.merger_sub_target(deal_text, party)
    cp = cp or T.find_counterparty(deal_text, party) or (T.find_counterparty(pr_text, party) if pr_text else None)
    event["counterparty"] = field(cp[0], main_url, cp[1]) if cp else field(None)
    event["agreement_date"] = T.agreement_date(combined, main_url)
    event["closing_date"] = T.closing_date(deal_text, main_url) if status["value"] == "Closed" else field(None)
    fin = T.extract_financials(deal_text, main_url)
    if pr_text:
        for k, v in T.extract_financials(pr_text, pr_url or main_url).items():
            fin.setdefault(k, v)
    event["financials"] = fin
    event["advisors"] = T.extract_advisors(deal_text, main_url, party) + (T.extract_advisors(pr_text, pr_url, party) if pr_text else [])
    rationale = T.extract_rationale(pr_text, pr_url) if pr_text else T.extract_rationale(deal_text, main_url)
    event["rationale"] = rationale
    event["sponsor_context"] = T.extract_sponsor_context(combined, main_url)
    event["merger_of_equals"] = bool(re.search(r"merger of equals", combined, re.I))
    event["recapitalization"] = bool(re.search(r"\brecapitali[sz]ation\b", combined, re.I))
    return event


_FACILITY_RE = re.compile(
    r"(?:aggregate (?:principal amount|commitments?)|revolving (?:credit )?(?:facility|commitments?)|term loan|credit facility|notes)"
    r"[^.$]{0,80}?(?:of |up to |in an aggregate (?:principal )?amount of )?(?:up to )?" + T.MONEY_RE.pattern,
    re.I,
)


def _facility_amount(text: str, url: str) -> dict:
    for s in T.sentences(text):
        m = _FACILITY_RE.search(s)
        if m:
            v = T.money_value(m)
            if v and v >= 1_000_000:
                return field(v, url, s)
    return field(None)


# ----------------------------------------------------------------------------- stored text (offline re-extraction)

def _text_path(accession: str):
    return config.EVIDENCE_TEXT_DIR / f"{accession}.json.gz"


def save_filing_text(hit: FilingHit, main_text: str, main_url: str, pr_text: str, pr_url: str | None) -> None:
    """Keep the filing text we extracted from, so rules can be re-run without re-querying SEC."""
    path = _text_path(hit.accession)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"hit": asdict(hit), "main_url": main_url, "main_text": main_text[:MAX_TEXT_CHARS], "pr_url": pr_url, "pr_text": pr_text[:200_000]}
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(payload, fh)


def reextract(event: dict) -> dict | None:
    """Re-run current extraction rules on stored filing text. Returns the new event, or None if no text."""
    path = _text_path(event["event_id"])
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    new = analyze_ma_filing(FilingHit(**payload["hit"]), payload["main_text"], payload["main_url"], payload["pr_text"], payload["pr_url"])
    if new is not None and event.get("llm"):
        new["llm"] = event["llm"]
    return new


def collect_ma(client: SecClient, start: date, end: date, known: set[str]) -> SourceResult:
    """8-K (Items 1.01/1.02/2.01 + merger language), S-4, DEFM14A, SC TO-T, SC 14D9."""
    result = SourceResult()
    candidates: dict[str, FilingHit] = {}
    for location_type in (None, "incorporated"):
        for hit in search_filings(client, "8-K", start, end, location_type=location_type):
            if set(hit.items) & DEAL_8K_ITEMS:
                candidates.setdefault(hit.accession, hit)
        for hit in search_filings(client, "8-K", start, end, query=MERGER_QUERY, location_type=location_type):
            candidates.setdefault(hit.accession, hit)
        for form in MERGER_FORMS:
            for hit in search_filings(client, form, start, end, location_type=location_type):
                if (hit.form or "").upper() == form:  # skip amendments (S-4/A etc.)
                    candidates.setdefault(hit.accession, hit)

    for hit in candidates.values():
        result.seen += 1
        if hit.accession in known or is_abs_vehicle(hit):
            result.skipped += 1
            continue
        try:
            cik = _filer(hit)["cik"] or hit.ciks[0]
            doc = hit.primary_document or find_primary_document(client, cik, hit.accession, hit.form or "8-K")
            if not doc:
                raise ValueError("could not locate the primary document")
            main_url = document_url(cik, hit.accession, doc)
            raw = client.get_text(main_url)
            text = html_to_text(raw)[:MAX_TEXT_CHARS]
            pr_url, pr_text = None, ""
            is_8k = (hit.form or "").upper().startswith("8-K")
            if is_8k:
                pre = analyze_8k(raw, hit.items, _filer(hit)["name"] or "")
                if pre["type"] == "M&A" or "2.01" in hit.items:
                    pr_url, pr_text = _press_release(client, cik, hit.accession)
            event = analyze_ma_filing(hit, raw if is_8k else text, main_url, pr_text, pr_url)
            if event is None:
                result.skipped += 1
                continue
            save_filing_text(hit, html_to_text(raw) if is_8k else text, main_url, pr_text, pr_url)
            if event.get("category") == "M&A" and not (event.get("role") or {}).get("value") and llm.enabled():
                filled = llm.fill_roles(text + "\n" + pr_text, display_name(event["filer"]["name"]) or "", main_url)
                if filled:
                    event["llm"] = filled
            result.events.append(event)
        except Exception as exc:  # noqa: BLE001 - isolate every filing
            result.fail(hit.accession, f"SEC {hit.form}", exc)
    return result


# ----------------------------------------------------------------------------- Form D

def xml_snippet(xml: str, tag: str) -> str | None:
    """Exact ``<tag>...</tag>`` text from the source document (used as the field's quote)."""
    m = re.search(rf"<{tag}>\s*([^<]*?)\s*</{tag}>", xml)
    return f"<{tag}>{m.group(1)}</{tag}>" if m else None


def formd_event(hit: FilingHit, xml: str, url: str) -> dict | None:
    parsed = parse_form_d(xml)
    if parsed.get("state") != config.STATE_CODE:
        return None
    event = _base_event(hit, "sec_formd", "primary_doc.xml")
    event["doc_url"] = url
    event["parsed"] = parsed
    event["file_number"] = hit.file_nums[0] if hit.file_nums else None
    event["quotes"] = {
        tag: xml_snippet(xml, tag)
        for tag in (
            "entityName", "city", "zipCode", "industryGroupType", "investmentFundType", "totalOfferingAmount",
            "totalAmountSold", "totalRemaining", "totalNumberAlreadyInvested", "isBusinessCombinationTransaction",
            "isAmendment", "withinFiveYears", "isEquityType", "isDebtType", "descriptionOfOtherType", "value",
        )
    }
    return event


def collect_form_d(client: SecClient, start: date, end: date, known: set[str]) -> SourceResult:
    result = SourceResult()
    for hit in search_filings(client, "D", start, end):
        result.seen += 1
        if hit.accession in known:
            result.skipped += 1
            continue
        try:
            doc = hit.primary_document or "primary_doc.xml"
            url = document_url(hit.ciks[0], hit.accession, doc)
            event = formd_event(hit, client.get_text(url), url)
            if event is None:
                result.skipped += 1
                continue
            result.events.append(event)
        except Exception as exc:  # noqa: BLE001
            result.fail(hit.accession, "SEC Form D", exc)
    return result


# ----------------------------------------------------------------------------- Schedule 13D

def collect_13d(client: SecClient, start: date, end: date, known: set[str]) -> SourceResult:
    """Schedule 13D/13D-A where the *subject company* is headquartered in Michigan."""
    result = SourceResult()
    for hit in search_filings(client, "SCHEDULE 13D", start, end):
        result.seen += 1
        subject = hit.entities[0] if hit.entities else {}
        if hit.accession in known or subject.get("state") != config.STATE_CODE:
            result.skipped += 1
            continue
        try:
            url = document_url(hit.ciks[0], hit.accession, hit.primary_document or "primary_doc.xml")
            parsed = parse_schedule_13d(client.get_text(url))
            if parsed.get("issuer_state") and parsed["issuer_state"] != config.STATE_CODE:
                result.skipped += 1
                continue
            event = _base_event(hit, "sec_13d", None)
            event.update({"doc_url": url, "parsed": parsed, "subject": {k: subject.get(k) for k in ("name", "cik", "tickers", "location", "state")}})
            result.events.append(event)
        except Exception as exc:  # noqa: BLE001
            result.fail(hit.accession, "SEC Schedule 13D", exc)
    return result
