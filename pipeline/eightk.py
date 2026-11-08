"""Rule-based analysis of 8-K current reports.

We care about three signals:
* Item 1.01 - Entry into a Material Definitive Agreement
* Item 2.01 - Completion of Acquisition or Disposition of Assets
* Merger/acquisition language anywhere in the body of the 8-K
"""

from __future__ import annotations

import re

from .htmltext import clip, flatten, html_to_text

ITEM_TITLES = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure/Election of Directors or Officers",
    "5.03": "Amendments to Articles or Bylaws",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}

DEAL_ITEMS = {"1.01", "2.01"}

# Strong M&A language: an agreement to combine with, buy, or sell a business.
STRONG_MA_PATTERNS = [
    r"agreement and plan of (?:merger|reorganization)",
    r"\bplan of merger\b",
    r"\bmerger agreement\b",
    r"business combination agreement",
    r"(?:stock|share|equity|asset|membership interests?) purchase agreement",
    r"completed (?:its|the) (?:previously announced )?(?:acquisition|merger|sale|divestiture)",
    r"definitive agreement to (?:acquire|be acquired|sell|merge)",
]
# Weaker signals: only count when the filing isn't primarily a financing.
WEAK_MA_PATTERNS = [r"\btender offer\b", r"\bhas acquired\b", r"\bmerged with and into\b"]
STRONG_MA_RE = re.compile("|".join(STRONG_MA_PATTERNS), re.I)
MA_RE = re.compile("|".join(STRONG_MA_PATTERNS + WEAK_MA_PATTERNS), re.I)
FINANCING_RE = re.compile(
    r"credit agreement|credit facility|loan agreement|indenture|notes due|senior notes|term loan|revolving", re.I
)
LEAD_CHARS = 600  # the opening of Item 1.01 says what the agreement mainly is

# Sub-classification of non-M&A material agreements.
AGREEMENT_KINDS = [
    ("Credit Facility", r"credit agreement|credit facility|revolving|term loan|loan agreement|loan and security"),
    ("Debt Offering", r"indenture|senior notes|convertible notes|note purchase agreement|underwriting agreement"),
    ("Equity Financing", r"securities purchase agreement|subscription agreement|registered direct|private placement|at[- ]the[- ]market|sales agreement|warrant"),
    ("Employment Agreement", r"employment agreement|separation agreement|retention agreement|severance"),
    ("Real Estate / Lease", r"\blease\b|purchase and sale agreement"),
    ("Securitization", r"receivables purchase|servicing agreement|indenture trustee|asset[- ]backed"),
    ("Commercial Agreement", r"supply agreement|license agreement|collaboration|master services|distribution agreement|joint venture"),
]

_AMOUNT_RE = re.compile(
    r"\$\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?P<unit>billion|million|thousand)?",
    re.I,
)
_UNIT = {"billion": 1e9, "million": 1e6, "thousand": 1e3}
_COUNTERPARTY_RE = re.compile(
    r"(?i:(?:merger|combination|transaction|acquisition|agreement\s*\"?\s*\)?)\s+(?:with|of)|by and (?:among|between))\s+"
    r"(?P<name>[A-Z][\w&.'\- ]{2,70}?,? (?:Inc|Incorporated|Corporation|Corp|Company|LLC|L\.L\.C|L\.P|LP|Ltd|Limited|plc|N\.V|S\.A|GmbH|AG|Holdings|Bancorp|Co)\b\.?)",
)
_ITEM_HEADING_RE = re.compile(r"\bItem\s*(\d\.\d{2})\b\.?", re.I)


def extract_sections(text: str) -> dict[str, str]:
    """Map item number -> section text (first occurrence of each heading)."""
    sections: dict[str, str] = {}
    matches = list(_ITEM_HEADING_RE.finditer(text))
    for i, match in enumerate(matches):
        item = match.group(1)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end(): end].strip()
        # Skip cross-references such as "as described in Item 1.01 above".
        if item in sections or len(body) < 40:
            continue
        sections[item] = body
    return sections


def _strip_heading(body: str, item: str) -> str:
    title = ITEM_TITLES.get(item)
    if title and body.lower().startswith(title.lower()[:20]):
        body = body.split("\n", 1)[1] if "\n" in body else body[len(title):]
    return body.lstrip(" .:-\n")


def parse_amount(text: str) -> float | None:
    """Largest dollar figure mentioned in ``text`` (e.g. "$1.2 billion")."""
    best = None
    for match in _AMOUNT_RE.finditer(text or ""):
        try:
            value = float(match.group("num").replace(",", ""))
        except ValueError:
            continue
        unit = (match.group("unit") or "").lower()
        value *= _UNIT.get(unit, 1)
        if value >= 100_000 and (best is None or value > best):
            best = value
    return best


def find_counterparty(text: str, company: str = "") -> str | None:
    company_key = re.sub(r"[^a-z]", "", (company or "").lower())[:8]
    for match in _COUNTERPARTY_RE.finditer(text or ""):
        name = flatten(match.group("name")).strip(" ,")
        key = re.sub(r"[^a-z]", "", name.lower())[:8]
        if company_key and key == company_key:
            continue
        if "merger sub" in name.lower():
            continue
        return name
    return None


def classify_agreement(text: str) -> str:
    for label, pattern in AGREEMENT_KINDS:
        if re.search(pattern, text, re.I):
            return label
    return "Material Agreement"


def analyze_8k(raw_html: str, items: list[str], company: str = "") -> dict:
    """Classify an 8-K and pull an excerpt.

    Returns a dict with ``type`` set to ``"M&A"``, ``"Material Agreement"`` or
    ``None`` (not deal-related, e.g. an earnings release mentioning a merger).
    """
    text = html_to_text(raw_html)
    sections = extract_sections(text)
    items = [i for i in items if i]

    focus_item = next((i for i in ("2.01", "1.01", "8.01", "7.01") if i in sections), None)
    body = _strip_heading(sections[focus_item], focus_item) if focus_item else ""
    deal_text = " ".join(sections.get(i, "") for i in ("2.01", "1.01", "8.01"))
    has_ma_language = bool(MA_RE.search(deal_text))

    section_101 = sections.get("1.01", "")
    lead_101 = section_101[:LEAD_CHARS]
    ma_hit, fin_hit = STRONG_MA_RE.search(lead_101), FINANCING_RE.search(lead_101)
    if "2.01" in items:
        deal_type, subtype = "M&A", "Acquisition/Disposition Completed"
    elif "1.01" in items and ma_hit and (not fin_hit or ma_hit.start() < fin_hit.start()):
        deal_type, subtype = "M&A", "Definitive Agreement"
    elif "1.01" in items and fin_hit:
        # e.g. a credit agreement that mentions the merger it helps fund
        deal_type, subtype = "Material Agreement", classify_agreement(lead_101)
    elif "1.01" in items and has_ma_language:
        deal_type, subtype = "M&A", "Definitive Agreement"
    elif STRONG_MA_RE.search(deal_text) and ("8.01" in items or "7.01" in items):
        deal_type, subtype = "M&A", "Deal Announcement"
    elif "1.01" in items:
        deal_type, subtype = "Material Agreement", classify_agreement(section_101 or body)
    else:
        deal_type, subtype = None, None

    excerpt = clip(body, 420) if body else clip(text[:2000], 300)
    amount_scope = sections.get("2.01") or sections.get("1.01") or body
    return {
        "type": deal_type,
        "subtype": subtype,
        "items": items,
        "item_titles": [ITEM_TITLES.get(i, f"Item {i}") for i in items],
        "excerpt": excerpt,
        "amount_mentioned": parse_amount(amount_scope) if deal_type == "M&A" else None,
        "counterparty": find_counterparty(deal_text, company) if deal_type == "M&A" else None,
        "has_ma_language": has_ma_language,
    }
