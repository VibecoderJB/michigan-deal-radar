"""Presentation helpers shared by the pipeline and reports: names, money, tickers."""

from __future__ import annotations

import re

_ACRONYMS = {
    "LLC", "LP", "L.P.", "LLLP", "II", "III", "IV", "VI", "VII", "USA", "US", "REIT", "DTE", "GM", "BV", "N.A.",
    "PLLC", "UWM", "AI", "ABS", "CMS", "NV", "AG", "SA", "PLC", "LTD.", "UFP", "ESOP", "SPV", "MSV", "CVC", "GC",
}
_LOWER = {"of", "and", "the", "for", "in", "a"}


def _title_word(word: str) -> str:
    bare = word.strip(",.()/")
    if bare.upper() in _ACRONYMS or any(ch.isdigit() for ch in bare) or (bare.count(".") >= 1 and len(bare) <= 5):
        return word
    if bare.lower() in _LOWER:
        return word.lower()
    return "-".join(part.capitalize() for part in word.split("-"))


def display_name(name: str | None) -> str | None:
    """Title-case SHOUTY EDGAR names, keep acronyms, drop EDGAR state suffixes like '/MI/'."""
    if not name:
        return None
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\s*/[A-Za-z]{2,3}/?$", "", name)
    letters = [c for c in name if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.7:
        return name
    words = [_title_word(w) for w in name.split(" ")]
    if words:
        words[0] = words[0][:1].upper() + words[0][1:]
    return " ".join(words)


def pick_ticker(tickers: list[str] | None, company: str | None) -> str | None:
    """Prefer the common-stock ticker: the one that matches the company name."""
    if not tickers:
        return None
    letters = re.sub(r"[^A-Z]", "", (company or "").upper())
    for t in tickers:
        if letters.startswith(t):
            return t
    return min(tickers, key=lambda t: (("-" in t or "." in t), len(t)))


def money(value: float | None, undisclosed: str = "an undisclosed amount") -> str:
    """Compact currency for prose: 1_250_000 -> '$1.3M'."""
    if value is None:
        return undisclosed
    for threshold, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= threshold:
            return f"${value / threshold:,.1f}{suffix}".replace(".0" + suffix, suffix)
    return f"${value:,.0f}"


def money_mm(value: float | None) -> str:
    """Banking format: $ millions with one decimal ('$45.7'). Not disclosed -> 'n.d.'."""
    return "n.d." if value is None else f"${value / 1e6:,.1f}"


def multiple(value: float | None) -> str:
    return "n.d." if value is None else f"{value:.1f}x"


def article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


_STANDARD_SECURITIES = {"Equity", "Debt", "Options/Warrants", "Security to be Acquired", "Pooled Fund Interests", "Tenant-in-Common", "Mineral Property"}


def describe_securities(securities: list[str] | None) -> str:
    """Short phrase for Form D securities, e.g. 'equity' or 'SAFE'."""
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
