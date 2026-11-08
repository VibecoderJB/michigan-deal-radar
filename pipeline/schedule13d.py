"""Parser for structured Schedule 13D / 13D-A XML (EDGAR schema since Dec 2024)."""

from __future__ import annotations

from .htmltext import clip
from .xmlutil import ParseError, first_text, parse_xml, text, to_number


def parse_schedule_13d(xml_text: str) -> dict:
    root = parse_xml(xml_text)
    submission_type = first_text(root, "submissionType") or ""
    if "13D" not in submission_type.upper():
        raise ParseError(f"not a Schedule 13D: {submission_type!r}")

    issuer_name = first_text(root, "issuerName")
    if not issuer_name:
        raise ParseError("Schedule 13D has no issuer name")

    issuer_address = root.find(".//issuerInfo/address")
    if issuer_address is None:
        issuer_address = next(iter(root.iter("issuerPrincipalAddress")), None)

    reporters = []
    for rp in root.iter("reportingPersonInfo"):
        name = text(rp, "reportingPersonName")
        if not name:
            continue
        reporters.append(
            {
                "name": name,
                "cik": text(rp, "reportingPersonCIK"),
                "percent_of_class": to_number(text(rp, "percentOfClass")),
                "shares": to_number(text(rp, "aggregateAmountOwned")),
                "type": text(rp, "typeOfReportingPerson"),
            }
        )
    if not reporters:  # older layouts: scan flat tags
        name = first_text(root, "reportingPersonName")
        if name:
            reporters.append(
                {
                    "name": name,
                    "cik": first_text(root, "reportingPersonCIK"),
                    "percent_of_class": to_number(first_text(root, "percentOfClass")),
                    "shares": to_number(first_text(root, "aggregateAmountOwned")),
                    "type": first_text(root, "typeOfReportingPerson"),
                }
            )

    purpose = first_text(root, "transactionPurpose")
    return {
        "submission_type": submission_type,
        "is_amendment": submission_type.upper().endswith("/A"),
        "amendment_no": first_text(root, "amendmentNo"),
        "issuer_name": issuer_name,
        "issuer_cik": first_text(root, "issuerCIK"),
        "issuer_cusip": first_text(root, "issuerCusipNumber"),
        "issuer_city": text(issuer_address, "city") if issuer_address is not None else None,
        "issuer_state": text(issuer_address, "stateOrCountry") if issuer_address is not None else None,
        "security_class": first_text(root, "securitiesClassTitle"),
        "event_date": _us_date_to_iso(first_text(root, "dateOfEvent")),
        "reporting_persons": reporters,
        "max_percent": max((r["percent_of_class"] or 0 for r in reporters), default=None),
        "purpose_excerpt": clip(purpose, 420) if purpose else None,
    }


def _us_date_to_iso(value: str | None) -> str | None:
    """``09/11/2026`` -> ``2026-09-11`` (passes through ISO dates)."""
    if not value:
        return None
    parts = value.split("/")
    if len(parts) == 3 and len(parts[2]) == 4:
        month, day, year = parts
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return value
