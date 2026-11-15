"""Migrate schema-v1 records (data/backup/v1-*/deals.json) into v2 evidence events.

The 24-month backfill re-fetches every v1 filing from EDGAR, which yields exact source
text. This migrator is the safety net: any v1 filing that is *not* in the v2 evidence
ledger is converted from the archived v1 record so no data is lost. Migrated events are
marked ``migrated_from_v1`` and their quotes are rebuilt from the archived values, which
the UI labels accordingly.

    python -m pipeline.storage.migrate_v1            # fill gaps in data/evidence.json
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from .. import config
from ..ingestion.edgar import FilingHit
from ..sources.sec import analyze_ma_filing
from .store import load_evidence, merge_evidence, read_json, save_evidence

log = logging.getLogger(__name__)
NOTE = "migrated from the v1 archive; quote rebuilt from archived value"


def _num(v):
    return None if v is None else (int(v) if float(v).is_integer() else v)


def _formd_event(d: dict) -> dict:
    x = d.get("details") or {}
    filed_year = int(d["filed"][:4])
    yoi = x.get("year_of_inc")
    within5 = None
    if yoi and str(yoi).isdigit():
        within5 = "true" if filed_year - int(yoi) <= 5 else "false"
    q = lambda tag, v: None if v is None else f"<{tag}>{v}</{tag}>"  # noqa: E731
    securities = x.get("securities") or []
    parsed = {
        "cik": d["cik"], "issuer_name": d["company"], "city": d.get("city"), "state": d.get("state") or "MI", "zip": None,
        "industry": d.get("industry"), "is_pooled_fund": bool(x.get("is_pooled_fund")), "fund_type": x.get("fund_type"),
        "is_amendment": d.get("form") == "D/A", "date_of_first_sale": d.get("event_date"),
        "first_sale_yet_to_occur": x.get("first_sale_yet_to_occur"), "is_business_combination": "Business Combination" in (d.get("subtype") or ""),
        "securities": securities, "exemptions": x.get("exemptions"), "total_offering_amount": x.get("total_offering_amount"),
        "offering_indefinite": x.get("offering_indefinite"), "total_amount_sold": d.get("amount_sold"),
        "total_remaining": x.get("total_remaining"), "investor_count": x.get("investor_count"),
        "related_persons": d.get("related_persons") or [], "year_of_inc": yoi,
    }
    return {
        "event_id": d["accession"], "kind": "sec_formd", "form": d.get("form"), "items": [], "filed": d["filed"],
        "url": d["url"], "doc_url": d.get("doc_url"),
        "filer": {"name": d["company"], "cik": d["cik"], "tickers": [], "city": d.get("city"), "state": "MI", "sic": None, "inc_state": None},
        "entities": [], "parsed": parsed, "file_number": x.get("file_number"),
        "quotes": {
            "entityName": q("entityName", d["company"]), "city": q("city", (d.get("city") or "").upper() or None),
            "industryGroupType": q("industryGroupType", d.get("industry")), "investmentFundType": q("investmentFundType", x.get("fund_type")),
            "totalOfferingAmount": q("totalOfferingAmount", "Indefinite" if x.get("offering_indefinite") else _num(x.get("total_offering_amount"))),
            "totalAmountSold": q("totalAmountSold", _num(d.get("amount_sold"))), "totalRemaining": q("totalRemaining", _num(x.get("total_remaining"))),
            "totalNumberAlreadyInvested": q("totalNumberAlreadyInvested", _num(x.get("investor_count"))),
            "isBusinessCombinationTransaction": q("isBusinessCombinationTransaction", str(parsed["is_business_combination"]).lower()),
            "withinFiveYears": q("withinFiveYears", within5), "isDebtType": q("isDebtType", "true" if "Debt" in securities else None),
            "value": q("value", d.get("event_date")),
        },
        "migrated_from_v1": True, "migration_note": NOTE,
    }


def _ma_event(d: dict) -> dict | None:
    x = d.get("details") or {}
    hit = FilingHit(
        accession=d["accession"], form="8-K" if (d.get("form") or "").startswith("EX-") else (d.get("form") or "8-K"), file_date=d["filed"], ciks=[d["cik"]],
        entities=[{"name": d["company"], "tickers": [d["ticker"]] if d.get("ticker") else [], "cik": d["cik"].zfill(10),
                   "location": f"{d.get('city') or ''}, MI", "state": "MI"}],
        items=d.get("items") or [], sics=[x["sic"]] if x.get("sic") else [], primary_document=None,
    )
    heading = {"2.01": "Item 2.01 Completion of Acquisition or Disposition of Assets", "1.01": "Item 1.01 Entry into a Material Definitive Agreement"}
    item = "2.01" if "2.01" in hit.items else "1.01" if "1.01" in hit.items else "8.01"
    text = f"{heading.get(item, 'Item 8.01 Other Events')}\n{d.get('excerpt') or d.get('summary')}"
    event = analyze_ma_filing(hit, text, d.get("doc_url") or d["url"])
    if event is None:  # excerpt too short to classify: keep it as non-deal evidence rather than drop it
        from ..sources.sec import _base_event
        event = _base_event(hit, "sec_ma", None)
        event.update({"category": "Material Agreement", "agreement_kind": d.get("subtype") or "Material Agreement",
                      "excerpt": d.get("excerpt"), "doc_url": d.get("doc_url"), "status": {"value": None, "method": "rule"}})
    event["url"] = d["url"]
    event["migrated_from_v1"] = True
    event["migration_note"] = "migrated from the v1 archive; only the stored 420-character excerpt was available"
    return event


def _13d_event(d: dict) -> dict:
    x = d.get("details") or {}
    return {
        "event_id": d["accession"], "kind": "sec_13d", "form": d.get("form"), "items": [], "filed": d["filed"], "url": d["url"], "doc_url": d.get("doc_url"),
        "filer": {"name": d["company"], "cik": d["cik"], "tickers": [d["ticker"]] if d.get("ticker") else [], "city": d.get("city"), "state": "MI", "sic": None, "inc_state": None},
        "entities": [],
        "parsed": {"submission_type": d.get("form"), "is_amendment": "/A" in (d.get("form") or ""), "amendment_no": x.get("amendment_no"),
                   "issuer_name": d["company"], "issuer_cik": d["cik"], "issuer_city": d.get("city"), "issuer_state": "MI",
                   "event_date": d.get("event_date"), "max_percent": x.get("percent_of_class"), "purpose_excerpt": d.get("excerpt"),
                   "reporting_persons": [{"name": p["name"], "percent_of_class": None, "shares": None, "type": None} for p in d.get("related_persons") or []]},
        "subject": {"name": d["company"], "cik": d["cik"], "tickers": [d["ticker"]] if d.get("ticker") else [], "location": f"{d.get('city')}, MI", "state": "MI"},
        "migrated_from_v1": True, "migration_note": NOTE,
    }


def migrate(v1_records: list[dict], existing_ids: set[str]) -> list[dict]:
    """Convert v1 records whose filings are absent from the v2 evidence ledger."""
    events = []
    for d in v1_records:
        try:
            if d.get("accession") in existing_ids:
                continue
            form = d.get("form") or ""
            if form in ("D", "D/A"):
                events.append(_formd_event(d))
            elif "13D" in form.upper():
                events.append(_13d_event(d))
            elif form.startswith(("8-K", "EX-")):  # v1 sometimes stored the exhibit type as the form
                e = _ma_event(d)
                if e:
                    events.append(e)
        except Exception as exc:  # noqa: BLE001 - one bad record never stops migration
            log.warning("Could not migrate %s: %s", d.get("id"), exc)
    return events


def latest_v1_archive() -> Path | None:
    backups = sorted(config.BACKUP_DIR.glob("v1-*/deals.json"))
    return backups[-1] if backups else None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = latest_v1_archive()
    if not path:
        log.error("No v1 archive found under %s", config.BACKUP_DIR)
        return 1
    v1 = (read_json(path, {}) or {}).get("deals", [])
    evidence = load_evidence()
    new = migrate(v1, {e["event_id"] for e in evidence})
    save_evidence(merge_evidence(evidence, new))
    log.info("Migrated %d of %d v1 records (others already present from EDGAR)", len(new), len(v1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
