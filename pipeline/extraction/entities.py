"""Entity names: normalization, fuzzy matching, and buyer-type classification."""

from __future__ import annotations

import difflib
import re
from functools import lru_cache
from pathlib import Path

import yaml

from .. import config
from .terms import SPONSOR_NAME_RE

_SUFFIX_RE = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|llc|l\.l\.c|lp|l\.p|llp|ltd|limited|plc|pllc|p\.l\.c|holdings?|group|"
    r"bancorp|bancshares|n\.a|the)\b\.?",
    re.I,
)

FIRM_CATEGORIES = ("private_equity", "venture_capital", "family_offices", "investment_banks", "law_firms", "corporate_acquirers")


def normalize_name(name: str | None) -> str:
    """Comparable key: 'Grand River Commerce, Inc.' -> 'grand river commerce'."""
    if not name:
        return ""
    s = re.sub(r"\s*/[A-Za-z]{2,3}/?$", "", name)
    s = s.replace("&", " and ")
    s = _SUFFIX_RE.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def same_entity(a: str | None, b: str | None, threshold: float = 0.86) -> bool:
    """True when two names refer to the same company (prefix or fuzzy match on normalized names)."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long_ = sorted((na, nb), key=len)
    if len(short) >= 5 and (long_.startswith(short + " ") or long_ == short):
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= threshold


@lru_cache(maxsize=1)
def firms() -> dict[str, list[dict]]:
    path = config.CONFIG_DIR / "firms.yml"
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {k: data.get(k) or [] for k in FIRM_CATEGORIES}


def firm_category(name: str | None) -> tuple[str, dict] | None:
    """Match a name against the watchlist (name or alias)."""
    if not name:
        return None
    for category, entries in firms().items():
        for entry in entries:
            for candidate in [entry["name"], *(entry.get("aliases") or [])]:
                if same_entity(name, candidate, 0.9) or normalize_name(candidate) in normalize_name(name).split(" and "):
                    return category, entry
    return None


def canonical_firm(name: str) -> str:
    """Collapse advisor name variants ('Goldman Sachs' / 'Goldman Sachs & Co. LLC') for league tables."""
    hit = firm_category(name)
    if hit and hit[0] in ("investment_banks", "law_firms", "private_equity", "venture_capital"):
        return hit[1]["name"]
    return re.sub(r"\s+", " ", name).strip(" ,.")


def buyer_type(name: str | None, context_text: str = "") -> tuple[str, str] | None:
    """Classify a buyer as Financial Sponsor / Family Office / Strategic, with the reason.

    Returns None when there is no evidence either way (the field stays undisclosed
    rather than defaulting to 'Strategic').
    """
    if not name:
        return None
    hit = firm_category(name)
    if hit:
        cat = hit[0]
        if cat in ("private_equity", "venture_capital"):
            return "Financial Sponsor", f"{hit[1]['name']} is on the Deal Radar sponsor watchlist"
        if cat == "family_offices":
            return "Family Office", f"{hit[1]['name']} is on the Deal Radar family-office watchlist"
        if cat == "corporate_acquirers":
            return "Strategic", f"{hit[1]['name']} is an operating company on the Deal Radar watchlist"
    if re.search(r"family office", context_text, re.I) and normalize_name(name) in normalize_name(context_text):
        return "Family Office", "source describes the buyer as a family office"
    if SPONSOR_NAME_RE.search(name):
        return "Financial Sponsor", f"name pattern indicates an investment firm: {name}"
    if re.search(r"(?:private equity|investment) firm\s+" + re.escape(name.split(",")[0]), context_text, re.I):
        return "Financial Sponsor", "source describes the buyer as a private equity/investment firm"
    return None
