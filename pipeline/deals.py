"""Build normalized deal records (and their one-line summaries) from parsed filings.

Deal types:
* ``Fundraise``          - Form D private placements and pooled-fund raises
* ``M&A``                - 8-K Item 2.01 / merger agreements, Form D business combinations
* ``Material Agreement`` - other 8-K Item 1.01 agreements (credit facilities, etc.)
* ``Stake``              - Schedule 13D activist / 5%+ ownership disclosures
"""

from __future__ import annotations

import re

from .edgar import FilingHit, document_url, filing_index_url
from .sectors import sector_for_form_d, sector_for_sic

DEAL_TYPES = ("Fundraise", "M&A", "Material Agreement", "Stake")

_ABS_NAME_RE = re.compile(
    r"\b(trust 20\d\d|master owner trust|receivables|lease trust|auto lease|securitization|funding (?:llc|i+\b))",
    re.I,
)


def is_abs_vehicle(hit: FilingHit) -> bool:
    """Asset-backed securitization trusts file 8-Ks but are not deals."""
    name = hit.entities[0]["name"] if hit.entities else ""
    return "6189" in hit.sics or bool(_ABS_NAME_RE.search(name))


def money(value: float | None) -> str:
    """Compact currency for summaries: 1_250_000 -> "$1.3M"."""
    if value is None:
        return "an undisclosed amount"
    for threshold, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= threshold:
            return f"${value / threshold:,.1f}{suffix}".replace(".0" + suffix, suffix)
    return f"${value:,.0f}"


def display_name(name: str | None) -> str:
    """Title-case shouty EDGAR names while keeping short acronyms (e.g. "DTE ENERGY CO")."""
    if not name:
        return "Unknown issuer"
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\s*/[A-Za-z]{2,3}/?$", "", name)  # EDGAR suffixes like "/MI/"
    letters = [c for c in name if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.7:
        return name  # already mixed case
    words = [_title_word(word) for word in name.split(" ")]
    return " ".join(words)


_ACRONYMS = {
    "LLC", "LP", "L.P.", "LLLP", "II", "III", "IV", "VI", "VII", "USA", "US", "REIT", "DTE", "GM",
    "BV", "N.A.", "PLLC", "UWM", "AI", "ABS", "CMS", "NV", "AG", "SA", "PLC", "LTD.", "UFP", "ESOP",
}
_LOWER = {"of", "and", "the", "for", "in", "a"}


def _title_word(word: str) -> str:
    bare = word.strip(",.()/")
    if bare.upper() in _ACRONYMS or any(ch.isdigit() for ch in bare) or (bare.count(".") >= 1 and len(bare) <= 5):
        return word
    if bare.lower() in _LOWER:
        return word.lower()
    return "-".join(part.capitalize() for part in word.split("-"))


def _possessive_city(city: str | None) -> str:
    return f"{city}-based" if city else "Michigan-based"


def article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


INDUSTRY_PHRASES = {
    "Other": "",
    "Other Technology": "technology",
    "Other Health Care": "health care",
    "Other Energy": "energy",
    "Other Real Estate": "real estate",
    "Other Banking and Financial Services": "financial services",
    "Commercial": "commercial real estate",
    "Residential": "residential real estate",
    "Construction": "construction",
    "REITS and Finance": "real estate finance",
    "Investing": "investment",
    "Retailing": "retail",
    "Other Travel": "travel",
}
_STANDARD_SECURITIES = {"Equity", "Debt", "Options/Warrants", "Security to be Acquired", "Pooled Fund Interests", "Tenant-in-Common", "Mineral Property"}


def describe_securities(securities: list[str]) -> str:
    """Short phrase for the securities offered, e.g. "equity" or "SAFE"."""
    parts = []
    for sec in securities or []:
        sec = re.sub(r"\s+", " ", sec).strip().rstrip(".")
        if sec in _STANDARD_SECURITIES:
            parts.append(sec.lower())
        elif re.search(r"\bsafe", sec, re.I):
            parts.append("SAFE")
        elif "convertible" in sec.lower():
            parts.append("convertible note")
        elif len(sec) <= 30:
            parts.append(sec.lower())
        else:
            parts.append("other securities")
    parts = list(dict.fromkeys(parts))
    return " and ".join(parts[:2]) if parts else "securities"


def pick_ticker(tickers: list[str], company: str) -> str | None:
    """Prefer the common-stock ticker: the one that matches the company name."""
    if not tickers:
        return None
    letters = re.sub(r"[^A-Z]", "", company.upper())
    for t in tickers:
        if letters.startswith(t):
            return t
    return min(tickers, key=lambda t: (("-" in t or "." in t), len(t)))


def build_form_d_deal(hit: FilingHit, parsed: dict, doc_name: str = "primary_doc.xml") -> dict:
    cik = (parsed.get("cik") or hit.ciks[0]).lstrip("0")
    company = display_name(parsed.get("issuer_name") or hit.entities[0]["name"])
    offering = parsed.get("total_offering_amount")
    sold = parsed.get("total_amount_sold")
    is_fund = parsed.get("is_pooled_fund")
    is_combo = parsed.get("is_business_combination")

    if is_combo:
        deal_type, subtype = "M&A", "Business Combination (Form D)"
    elif is_fund:
        deal_type, subtype = "Fundraise", parsed.get("fund_type") or "Pooled Investment Fund"
    else:
        deal_type, subtype = "Fundraise", "Private Placement"

    headline_amount = offering if offering else sold
    investors = parsed.get("investor_count")
    securities = describe_securities(parsed.get("securities") or [])
    exemption = (parsed.get("exemptions") or ["Regulation D"])[0]

    if is_combo:
        descriptor = f"{_possessive_city(parsed.get('city'))} {'fund' if is_fund else 'company'}"
        summary = (
            f"{company}, {article(descriptor)} {descriptor}, filed a Form D tied to a business combination "
            f"(acquisition or merger); {money(sold)} of {securities} issued"
        )
    elif is_fund:
        target = "an open-ended (indefinite) raise" if parsed.get("offering_indefinite") else f"a {money(offering)} raise"
        descriptor = f"{_possessive_city(parsed.get('city'))} {(parsed.get('fund_type') or 'pooled investment fund').lower().replace('other ', '')}"
        summary = f"{company}, {article(descriptor)} {descriptor}, disclosed {target}; {money(sold)} sold"
    else:
        raw_industry = parsed.get("industry") or ""
        industry = INDUSTRY_PHRASES.get(raw_industry, raw_industry.lower())
        descriptor = f"{_possessive_city(parsed.get('city'))} {industry + ' ' if industry else ''}company"
        target = "an indefinite-size" if parsed.get("offering_indefinite") else f"a {money(offering)}"
        summary = (
            f"{company}, {article(descriptor)} {descriptor}, filed {target} "
            f"{securities} offering under {exemption}; {money(sold)} sold"
        )
    if investors:
        summary += f" to {int(investors)} investor{'s' if investors != 1 else ''}"
    summary += "."
    if parsed.get("is_amendment"):
        summary += " (Amended filing.)"

    file_num = hit.file_nums[0] if hit.file_nums else None
    deal_id = f"D-{cik}-{file_num}" if file_num else f"D-{hit.accession}"
    return {
        "id": deal_id,
        "type": deal_type,
        "subtype": subtype,
        "form": "D/A" if parsed.get("is_amendment") else "D",
        "accession": hit.accession,
        "company": company,
        "cik": cik,
        "ticker": None,
        "city": parsed.get("city"),
        "state": parsed.get("state"),
        "industry": parsed.get("industry"),
        "sector": sector_for_form_d(parsed.get("industry")),
        "filed": hit.file_date,
        "event_date": parsed.get("date_of_first_sale"),
        "amount": headline_amount,
        "amount_sold": sold,
        "amount_is_estimate": False,
        "summary": summary,
        "excerpt": None,
        "counterparty": None,
        "items": [],
        "related_persons": parsed.get("related_persons", [])[:12],
        "details": {
            "total_offering_amount": offering,
            "offering_indefinite": parsed.get("offering_indefinite"),
            "total_remaining": parsed.get("total_remaining"),
            "investor_count": investors,
            "minimum_investment": parsed.get("minimum_investment"),
            "securities": parsed.get("securities"),
            "exemptions": parsed.get("exemptions"),
            "entity_type": parsed.get("entity_type"),
            "jurisdiction": parsed.get("jurisdiction"),
            "year_of_inc": parsed.get("year_of_inc"),
            "revenue_range": parsed.get("revenue_range"),
            "fund_type": parsed.get("fund_type"),
            "is_pooled_fund": bool(is_fund),
            "has_non_accredited": parsed.get("has_non_accredited"),
            "sales_commissions": parsed.get("sales_commissions"),
            "first_sale_yet_to_occur": parsed.get("first_sale_yet_to_occur"),
            "file_number": file_num,
        },
        "url": filing_index_url(cik, hit.accession),
        "doc_url": document_url(cik, hit.accession, doc_name),
        "filings": [{"accession": hit.accession, "filed": hit.file_date, "form": "D/A" if parsed.get("is_amendment") else "D", "amount_sold": sold}],
    }


def build_8k_deal(hit: FilingHit, analysis: dict) -> dict:
    entity = hit.entities[0]
    cik = (entity.get("cik") or hit.ciks[0]).lstrip("0")
    company = display_name(entity["name"])
    ticker = pick_ticker(entity.get("tickers") or [], entity["name"])
    sector, industry = sector_for_sic(hit.sics[0] if hit.sics else None)
    who = f"{company} ({ticker})" if ticker else company
    counterparty = analysis.get("counterparty")
    amount = analysis.get("amount_mentioned")

    if analysis["subtype"] == "Acquisition/Disposition Completed":
        summary = f"{who} reported completing an acquisition or disposition of assets"
        summary += f" involving {counterparty}" if counterparty else ""
    elif analysis["type"] == "M&A":
        verb = "a definitive merger/acquisition agreement" if analysis["subtype"] == "Definitive Agreement" else "merger/acquisition activity"
        summary = f"{who} disclosed {verb}"
        summary += f" with {counterparty}" if counterparty else ""
    else:
        summary = f"{who} entered into a material definitive agreement"
        if analysis["subtype"] != "Material Agreement":
            summary += f" ({analysis['subtype'].lower()})"
    if amount and analysis["type"] == "M&A":
        summary += f"; filing cites a figure of ~{money(amount)}"
    summary = summary.rstrip(".") + "."

    city = entity.get("location", "").split(",")[0].strip() or None
    return {
        "id": f"8K-{hit.accession}",
        "type": analysis["type"],
        "subtype": analysis["subtype"],
        "form": hit.form or "8-K",
        "accession": hit.accession,
        "company": company,
        "cik": cik,
        "ticker": ticker,
        "city": city,
        "state": entity.get("state") or "MI",
        "industry": industry,
        "sector": sector,
        "filed": hit.file_date,
        "event_date": None,
        "amount": amount,
        "amount_sold": None,
        "amount_is_estimate": amount is not None,
        "summary": summary,
        "excerpt": analysis.get("excerpt"),
        "counterparty": counterparty,
        "items": analysis.get("items", []),
        "related_persons": [],
        "details": {"item_titles": analysis.get("item_titles", []), "sic": hit.sics[0] if hit.sics else None},
        "url": filing_index_url(cik, hit.accession),
        "doc_url": document_url(cik, hit.accession, hit.primary_document) if hit.primary_document else None,
    }


def build_13d_deal(hit: FilingHit, parsed: dict, subject: dict) -> dict:
    cik = (parsed.get("issuer_cik") or subject.get("cik") or hit.ciks[0]).lstrip("0")
    company = display_name(parsed.get("issuer_name") or subject["name"])
    ticker = pick_ticker(subject.get("tickers") or [], subject.get("name", ""))
    filers = [r["name"] for r in parsed.get("reporting_persons", [])] or [
        e["name"] for e in hit.entities[1:]
    ]
    lead = display_name(filers[0]) if filers else "An investor"
    pct = parsed.get("max_percent")
    who = f"{company} ({ticker})" if ticker else company
    pct_text = f"a {pct:g}% stake" if pct else "a 5%+ stake"
    summary = f"{lead}{' and others' if len(filers) > 1 else ''} reported {pct_text} in {who}"
    if parsed.get("is_amendment"):
        summary += f" (Schedule 13D/A amendment {parsed.get('amendment_no') or ''})".replace(" )", ")")
    summary = summary.rstrip(".") + "."
    sector, industry = sector_for_sic(hit.sics[0] if hit.sics else None)
    return {
        "id": f"13D-{hit.accession}",
        "type": "Stake",
        "subtype": "13D Amendment" if parsed.get("is_amendment") else "New 13D Position",
        "form": parsed.get("submission_type") or "SCHEDULE 13D",
        "accession": hit.accession,
        "company": company,
        "cik": cik,
        "ticker": ticker,
        "city": parsed.get("issuer_city") or subject.get("location", "").split(",")[0] or None,
        "state": parsed.get("issuer_state") or "MI",
        "industry": industry,
        "sector": sector,
        "filed": hit.file_date,
        "event_date": parsed.get("event_date"),
        "amount": None,
        "amount_sold": None,
        "amount_is_estimate": False,
        "summary": summary,
        "excerpt": parsed.get("purpose_excerpt"),
        "counterparty": lead if filers else None,
        "items": [],
        "related_persons": [
            {"name": display_name(r["name"]), "roles": [f"{r['percent_of_class']:g}% of class" if r.get("percent_of_class") is not None else "Reporting person"], "clarification": None}
            for r in parsed.get("reporting_persons", [])[:12]
        ],
        "details": {
            "percent_of_class": pct,
            "security_class": parsed.get("security_class"),
            "cusip": parsed.get("issuer_cusip"),
            "amendment_no": parsed.get("amendment_no"),
        },
        "url": filing_index_url(hit.ciks[0], hit.accession),
        "doc_url": document_url(hit.ciks[0], hit.accession, "primary_doc.xml"),
    }
