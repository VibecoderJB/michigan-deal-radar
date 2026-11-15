"""Deal data model (schema v2) with field-level provenance.

Every datum is a *Field*::

    {"value": 45700000, "source_url": "https://www.sec.gov/...", "source_text": "aggregate
     consideration of approximately $45.7 million", "method": "rule"}

* ``value`` is ``None`` when the source does not disclose it: the UI renders "Not disclosed".
* ``source_text`` is the exact text the value came from (verbatim, whitespace-normalized).
* ``method`` says how we got it:
    - ``filing_metadata``  structured EDGAR data (form type, filing date, XML element)
    - ``rule``             rule-based extraction from document text
    - ``derived``          computed from other sourced fields (e.g. EV/EBITDA, county from city)
    - ``llm_verified``     extracted by an LLM *and* its quote was found verbatim in the source
* ``estimate`` is True only for values we computed or inferred; the UI labels them "Est."
"""

from __future__ import annotations

from typing import Any, TypedDict

SCHEMA_VERSION = 2
NOT_DISCLOSED = "Not disclosed"

DEAL_TYPES = (
    "Acquisition",
    "Merger",
    "PE Buyout",
    "Add-on",
    "Growth Equity",
    "Venture Round",
    "Recapitalization",
    "Divestiture / Carve-out",
    "IPO",
    "Debt Raise",
)
MA_TYPES = {"Acquisition", "Merger", "PE Buyout", "Add-on", "Divestiture / Carve-out", "Recapitalization"}
FINANCING_TYPES = {"Growth Equity", "Venture Round", "Debt Raise", "IPO"}
STATUSES = ("Rumored", "Announced", "Pending", "Closed", "Terminated")
BUYER_TYPES = ("Strategic", "Financial Sponsor", "Family Office")
CONFIDENCE_LEVELS = ("High", "Medium", "Low")
METHODS = ("filing_metadata", "rule", "derived", "llm_verified")


class FieldValue(TypedDict, total=False):
    value: Any
    source_url: str | None
    source_text: str | None
    method: str
    estimate: bool
    note: str


def field(
    value: Any = None,
    source_url: str | None = None,
    source_text: str | None = None,
    method: str = "rule",
    *,
    estimate: bool = False,
    note: str | None = None,
) -> FieldValue:
    """Build a provenance-carrying field. Empty strings are treated as not disclosed."""
    if isinstance(value, str) and not value.strip():
        value = None
    if method not in METHODS:
        raise ValueError(f"unknown extraction method {method!r}")
    out: FieldValue = {
        "value": value,
        "source_url": source_url if value is not None else None,
        "source_text": source_text if value is not None else None,
        "method": method,
    }
    if estimate:
        out["estimate"] = True
    if note:
        out["note"] = note
    return out


def undisclosed() -> FieldValue:
    return {"value": None, "source_url": None, "source_text": None, "method": "rule"}


def val(f: FieldValue | dict | None, default: Any = None) -> Any:
    """Read a field's value safely (``None``/missing -> default)."""
    if not f:
        return default
    v = f.get("value")
    return default if v is None else v


def is_disclosed(f: FieldValue | dict | None) -> bool:
    return bool(f) and f.get("value") is not None


class Source(TypedDict, total=False):
    url: str
    title: str
    publisher: str
    kind: str          # "SEC 8-K", "SEC DEFM14A", "Press release", "News"
    date: str          # YYYY-MM-DD
    confidence: str    # High | Medium | Low
    accession: str


def source_confidence(kind: str) -> str:
    """High = SEC filing or official press release; Medium = reputable news; Low = other."""
    k = kind.lower()
    if k.startswith("sec ") or k == "press release":
        return "High"
    if k == "news":
        return "Medium"
    return "Low"


def deal_confidence(sources: list[Source]) -> str:
    """A deal is as strong as its best source (High = SEC/official release, Medium = news)."""
    levels = [s.get("confidence", "Low") for s in sources]
    if "High" in levels:
        return "High"
    if "Medium" in levels:
        return "Medium"
    return "Low"
