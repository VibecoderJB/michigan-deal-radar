"""Rule-based extraction of deal terms from filing and press-release text.

Each extractor works sentence by sentence and returns a provenance ``field`` whose
``source_text`` is the exact sentence the value came from. If no rule fires, the field
is left undisclosed. We never guess a number.

The extractors here are deliberately conservative: a value is only taken from a sentence
that names what the value *is* ("enterprise value of", "per share in cash", "EBITDA of").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from ..models import FieldValue, field, undisclosed
from .htmltext import flatten

# ----------------------------------------------------------------------------- basics

_SENTENCE_SPLIT = re.compile(
    r"(?<!\bInc)(?<!\bCorp)(?<!\bCo)(?<!\bLtd)(?<!\bNo)(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<!\bU\.S)(?<!\bL\.P)(?<!\bN\.A)(?<!\bSt)"
    r"(?<!\bJr)(?<!\bSr)(?<=[.;])\s+(?=[A-Z(\"“])"
)
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s*,\s*(\d{4})",
    re.I,
)
MONEY_RE = re.compile(
    r"(?:US)?\$\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*(?P<unit>billion|million|thousand|bn|mm|m|b)\b)?",
    re.I,
)
_UNITS = {"billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "mm": 1e6, "m": 1e6, "thousand": 1e3}


def _title_like(line: str) -> bool:
    words = [w for w in re.findall(r"[A-Za-z][\w'’&-]*", line) if w.lower() not in {"to", "and", "of", "the", "for", "in", "a", "an", "on", "with"}]
    return bool(words) and sum(w[0].isupper() for w in words) / len(words) >= 0.8


def _paragraphs(text: str) -> list[str]:
    """Re-join hard-wrapped lines; short un-punctuated lines (headings) stay separate."""
    paras: list[str] = []
    buf: list[str] = []
    for raw in text.split("\n"):
        line = flatten(raw)
        if not line:
            continue
        heading = 8 <= len(line) < 90 and not re.search(r"[.;:,\"”)]$", line) and (_title_like(line) or re.match(r"Item \d", line))
        if heading:
            if buf:
                paras.append(" ".join(buf))
                buf = []
            paras.append(line)
            continue
        buf.append(line)
        if re.search(r"[.!?:;\"”]$", line):
            paras.append(" ".join(buf))
            buf = []
    if buf:
        paras.append(" ".join(buf))
    return paras


def sentences(text: str) -> list[str]:
    """Split plain text into sentences (abbreviation-aware). Keeps sentences of 25-1,200 chars."""
    out = []
    for block in _paragraphs(text):
        for s in _SENTENCE_SPLIT.split(block):
            s = s.strip()
            if 25 <= len(s) <= 1200:
                out.append(s)
    return out


def parse_date(s: str) -> str | None:
    """First 'Month D, YYYY' date in ``s`` as ISO, or None."""
    m = _DATE_RE.search(s)
    if not m:
        return None
    try:
        return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()
    except ValueError:
        return None


def money_value(match: re.Match) -> float | None:
    try:
        n = float(match.group("num").replace(",", ""))
    except ValueError:
        return None
    unit = (match.group("unit") or "").lower()
    return n * _UNITS.get(unit, 1)


def first_money(s: str, minimum: float = 1.0) -> float | None:
    for m in MONEY_RE.finditer(s):
        v = money_value(m)
        if v is not None and v >= minimum:
            return v
    return None


# ----------------------------------------------------------------------------- parties

@dataclass
class Party:
    """How a document refers to the Michigan filer."""

    name: str
    aliases: set[str]

    @classmethod
    def from_text(cls, name: str, text: str) -> "Party":
        aliases = {"the Company", "the Registrant", "the Corporation"}
        first = re.split(r"[\s,]", name.strip())[0]
        if len(first) > 2:
            aliases.update({first, first.capitalize()} if first.isupper() and len(first) > 4 else {first})
        head = "(?i:" + re.escape(first) + ")"
        # e.g. Isabella Bank Corporation, a Michigan corporation ("Isabella")
        m = re.search(head + r"[^()]{0,120}?\(\s*(?:the\s+)?[\"“]\s*([A-Z][\w&.\-' ]{1,40}?)\s*[\"”]", text[:20000])
        if m and m.group(1).lower() not in {"company", "registrant"}:
            aliases.add(m.group(1).strip())
        return cls(name=name, aliases=aliases)

    def pattern(self) -> str:
        return "(?:" + "|".join(re.escape(a) for a in sorted(self.aliases, key=len, reverse=True)) + ")"


_PARTY_NAME = r"(?P<name>[A-Z][\w&.,'’\- ]{2,80}?,? (?:Inc|Incorporated|Corporation|Corp|Company|LLC|L\.L\.C|L\.P|LP|Ltd|Limited|plc|N\.V|S\.A|GmbH|AG|Holdings|Bancorp|Bancshares|Group|Co)\b\.?)"
_COUNTERPARTY_RE = re.compile(
    r"(?i:(?:merger|combination|transaction|acquisition|agreement\s*[\"”]?\s*\)?)\s+(?:with|of)|by and (?:among|between)|acquired by|to be acquired by|sale (?:of [^.]{0,80}? )?to)\s+"
    + _PARTY_NAME
)


_DEF_NAME_RE = re.compile(
    r"(?:^|[,;(]\s*|\band\s+|\bwith\s+|\bamong\s+)(?P<full>[A-Z][\w&.'’\- ]{1,60}?,? (?:Inc|Incorporated|Corporation|Corp|Company|LLC|L\.L\.C|L\.P|LP|Ltd|Limited|plc|N\.V|S\.A|GmbH|AG|Holdings|Bancorp|Bancshares|Group|Co)\b\.?)"
)


def resolve_defined_term(term: str, text: str) -> str | None:
    """'Noble' -> 'Noble Africa LLC' using the document's definition: Noble Africa LLC, ... ("Noble")."""
    marker = re.search(r"\(\s*(?:the\s+)?[\"“]" + re.escape(term) + r"[\"”]", text[:200000])
    if not marker:
        return None
    window = text[max(0, marker.start() - 300): marker.start()]
    names = [flatten(m.group("full")).strip(" ,") for m in _DEF_NAME_RE.finditer(window)]
    names = [n for n in names if not re.match(r"(?:a |an |the )?(?:Delaware|Michigan|Nevada|Ohio|Maryland|Texas|Cayman)\b", n, re.I)]
    term_key = term.split()[0].lower()
    for n in reversed(names):
        if n.lower().startswith(term_key):
            return n
    return names[-1] if names else None


def merger_sub_target(text: str, party: Party) -> tuple[str, str] | None:
    """When the filer owns the merger sub, the target is what the merger sub merges into."""
    p = party.pattern()
    for s in sentences(text):
        if not re.search(r"Merger Sub(?:sidiary)?\b.{0,200}?wholly[- ]owned subsidiary of " + p, s) and "Merger Sub" not in s:
            continue
        m = re.search(r"Merger Sub(?:sidiary)? (?:will |shall )?(?:merge|merged|be merged) with and into (?:the )?(?P<term>[A-Z][\w&.\-' ]{1,60}?)(?=[,(;.]| with | and )", s)
        if not m:
            continue
        term = m.group("term").strip()
        if re.fullmatch(p, term) or term.lower() in {"company", "the company"}:
            continue
        full = resolve_defined_term(term, text) or term
        return full, s
    return None


def find_counterparty(text: str, party: Party) -> tuple[str, str] | None:
    """Return (name, sentence) of the other side of the deal."""
    own = {re.sub(r"[^a-z]", "", a.lower())[:8] for a in party.aliases | {party.name}}
    for s in sentences(text):
        for m in _COUNTERPARTY_RE.finditer(s):
            name = flatten(m.group("name")).strip(" ,")
            key = re.sub(r"[^a-z]", "", name.lower())[:8]
            if key in own or "merger sub" in name.lower() or name.lower().startswith(("the ", "a ")):
                continue
            return name, s
    return None


# ----------------------------------------------------------------------------- roles

def filer_role(text: str, party: Party, form: str = "") -> tuple[str, str] | None:
    """Decide whether the Michigan filer is the target, acquirer or seller.

    Returns (role, evidence sentence) or None when the text is ambiguous.
    """
    f = form.upper()
    if f.startswith(("DEFM14A", "PREM14A", "SC 14D9", "DEFM14C")):
        return "target", f"Filed {form} (merger proxy / recommendation statement filed by the target company)"
    p = party.pattern()
    target_rules = [
        rf"(?:acquisition of|acquire|to acquire|will acquire|completed (?:its|the) (?:previously announced )?acquisition of) {p}\b",
        rf"{p} (?:will be|was|has been|is being) acquired",
        rf"{p}(?:'s)? (?:will )?(?:become|became|continu\w+ as) an? (?:direct |indirect )?wholly[- ]owned subsidiary of",
        rf"with and into {p},? with {p} (?:as the )?(?:continuing|surviving)\b.{{0,160}}wholly[- ]owned subsidiary of",
        rf"wholly[- ]owned subsidiary of (?:Parent|Buyer|Purchaser|Acquir\w+|Holdings)\b.{{0,80}}(?:merge|merged) with and into {p}",
        rf"(?:Merger Sub|Buyer|Purchaser) (?:will )?(?:merge|merged) with and into {p}",
        rf"(?:holders|shareholders|stockholders) of {p}(?:'s)?.{{0,40}}(?:will )?(?:receive|be entitled|converted)",
        r"(?:each|every) (?:issued and )?outstanding share of (?:the )?Company(?:'s)? (?:common )?stock.{0,120}(?:converted|cancelled|right to receive)",
    ]
    acquirer_rules = [
        rf"{p} (?:has )?(?:completed|consummated|closed) (?:its|the) (?:previously announced )?(?:acquisition|purchase) of",
        rf"with and into {p},? with {p} (?:continuing |surviving )(?!.{{0,160}}subsidiary of)",
        rf"(?:Merger Sub|Merger Subsidiary).{{0,160}}wholly[- ]owned subsidiary of {p}",
        rf"{p}.{{0,120}}(?:agreed to|will|to) (?:acquire|purchase) (?:all|substantially all|100%|the outstanding)",
        rf"{p} (?:purchased|acquired) (?:all|substantially all|100%) of the",
        rf"(?:a |an )?(?:direct |indirect )?wholly[- ]owned subsidiary of {p}.{{0,40}}(?:purchased|acquired|acquire)",
        rf"shares of {p}(?:'s)? common stock.{{0,80}}(?:exchange ratio|for each)",
    ]
    seller_rules = [
        rf"{p}.{{0,80}}(?:completed|consummated|closed) (?:the|its) (?:previously announced )?(?:sale|divestiture|disposition) of",
        rf"{p}.{{0,80}}(?:agreed to sell|will sell|to sell)(?! and issue)(?!.{{0,60}}(?:shares|securities|notes|warrants|private placement|offering))",
        r"\bcarve[- ]out\b",
    ]
    scores: dict[str, tuple[int, str]] = {}
    for s in sentences(text)[:400]:
        for role, rules in (("target", target_rules), ("acquirer", acquirer_rules), ("seller", seller_rules)):
            if any(re.search(r, s, re.I if role == "seller" else 0) for r in rules):
                n, ev = scores.get(role, (0, s))
                scores[role] = (n + 1, ev)
    if f.startswith("S-4") and "acquirer" not in scores:
        scores["acquirer"] = (1, f"Filed {form} (registration of shares issued in a business combination)")
    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda kv: kv[1][0], reverse=True)
    if len(ranked) > 1 and ranked[0][1][0] == ranked[1][1][0]:
        return None  # tie: ambiguous
    role, (_, evidence) = ranked[0]
    return role, evidence


# ----------------------------------------------------------------------------- financials

FIN_PATTERNS: dict[str, re.Pattern] = {
    "enterprise_value": re.compile(r"enterprise value of (?:approximately |about |roughly )?" + MONEY_RE.pattern, re.I),
    "equity_value": re.compile(r"equity value of (?:approximately |about |roughly )?" + MONEY_RE.pattern, re.I),
    "transaction_value": re.compile(
        r"(?:(?:aggregate|total) (?:purchase price|consideration|transaction value|deal value|merger consideration|cash consideration)"
        r"|transaction (?:is )?valued at|valued at|purchase price of)[^.$]{0,60}?" + MONEY_RE.pattern,
        re.I,
    ),
    "price_per_share": re.compile(r"(?:US)?\$\s?(?P<num>\d{1,4}(?:\.\d{1,4})?)(?P<unit>)\s+(?:in cash )?per share", re.I),
    "revenue": re.compile(
        r"(?:annual|annualized|trailing[- ]twelve[- ]month|TTM|20\d\d) (?:net )?(?:revenues?|sales) of (?:approximately |about |over |more than )?"
        + MONEY_RE.pattern + r"|generat\w+ (?:approximately |about |over )?" + MONEY_RE.pattern.replace("?P<num>", "?P<num2>").replace("?P<unit>", "?P<unit2>")
        + r" (?:in|of) (?:annual )?(?:revenues?|sales)",
        re.I,
    ),
    "ebitda": re.compile(r"(?:adjusted )?EBITDA of (?:approximately |about )?" + MONEY_RE.pattern, re.I),
}
_MULTIPLE_RE = re.compile(r"(?P<x>\d{1,2}(?:\.\d{1,2})?)\s?(?:x|times)\s+(?:(?:its|the|trailing|forward|estimated|adjusted|20\d\dE?|LTM|TTM)\s+){0,3}(?P<metric>EBITDA|revenue|sales)", re.I)


def _match_value(m: re.Match) -> float | None:
    gd = m.groupdict()
    num = gd.get("num") or gd.get("num2")
    unit = (gd.get("unit") or gd.get("unit2") or "").lower()
    if not num:
        return None
    try:
        return float(num.replace(",", "")) * _UNITS.get(unit, 1)
    except ValueError:
        return None


def extract_financials(text: str, url: str) -> dict[str, FieldValue]:
    """Disclosed deal financials, each with the sentence it came from."""
    out: dict[str, FieldValue] = {}
    sents = sentences(text)
    for key, pattern in FIN_PATTERNS.items():
        for s in sents:
            m = pattern.search(s)
            if not m:
                continue
            v = _match_value(m)
            if v is None or (key != "price_per_share" and v < 100_000):
                continue
            if key == "price_per_share" and (v < 0.5 or re.search(r"par value", s[max(0, m.start() - 40): m.end() + 10], re.I)):
                continue
            out[key] = field(round(v, 4) if key == "price_per_share" else v, url, s)
            break
    for s in sents:
        m = _MULTIPLE_RE.search(s)
        if m and "EBITDA" in m.group("metric").upper() and "ev_ebitda" not in out:
            out["ev_ebitda"] = field(float(m.group("x")), url, s, note="multiple stated in source")
        elif m and m.group("metric").lower() in ("revenue", "sales") and "ev_revenue" not in out:
            out["ev_revenue"] = field(float(m.group("x")), url, s, note="multiple stated in source")
    consideration = extract_consideration(sents, url)
    if consideration:
        out["consideration"] = consideration
    return out


def extract_consideration(sents: list[str], url: str) -> FieldValue | None:
    for s in sents:
        low = s.lower()
        if not re.search(r"consideration|per share|exchange ratio|will receive|right to receive|purchase price", low):
            continue
        cash = bool(re.search(r"\bin cash\b|all[- ]cash|cash consideration|\$[\d.,]+ (?:in cash )?per share", low))
        stock = bool(re.search(r"shares? of [^.]{0,60}common stock|exchange ratio|stock[- ]for[- ]stock|all[- ]stock", low))
        if cash and stock:
            return field("Cash & Stock", url, s)
        if cash:
            return field("Cash", url, s)
        if stock:
            return field("Stock", url, s)
    return None


# ----------------------------------------------------------------------------- dates & status

def agreement_date(text: str, url: str) -> FieldValue:
    """Date the definitive agreement was signed (links filings about the same deal).

    Prefers the original agreement over amendments ("First Amendment ... dated as of ...").
    """
    month = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s*\d{4}"
    agreement = r"(?:agreement and plan of (?:merger|reorganization)|merger agreement|(?:stock|share|equity|asset|unit|membership interests?) purchase agreement|business combination agreement|arrangement agreement)"
    sents = [s for s in sentences(text) if re.search(agreement, s, re.I)]
    for s in sents:
        # "dated as of X" where the 45 chars before it don't mention an amendment
        for m in re.finditer(r"dated (?:as of )?(" + month + r")", s):
            if not re.search(r"amendment", s[max(0, m.start() - 45): m.start()], re.I):
                return field(parse_date(m.group(1)), url, s)
        m = re.search(r"\b[Oo]n (" + month + r").{0,220}?entered into (?:an? |the )?" + agreement, s, re.I)
        if m and not re.search(r"entered into (?:an? |the )?(?:first |second )?amendment", s[m.start():m.end() + 30], re.I):
            return field(parse_date(m.group(1)), url, s)
    return undisclosed()


def closing_date(text: str, url: str) -> FieldValue:
    for s in sentences(text):
        if not re.search(r"\b(?:completed|consummated|closed|effective)\b", s, re.I):
            continue
        if not re.search(r"merger|acquisition|transaction|sale|purchase", s, re.I):
            continue
        m = re.search(r"(?:Effective (?:on|as of)|On) ((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\s*,\s*\d{4})", s)
        if m:
            return field(parse_date(m.group(1)), url, s)
    return undisclosed()


STATUS_PATTERNS = [
    ("Terminated", r"terminat\w+ (?:the |its )?(?:merger|purchase|transaction|business combination) agreement|agreement (?:was|has been) terminated"),
    ("Closed", r"\b(?:completed|consummated|closed) (?:the|its) (?:previously announced )?(?:merger|acquisition|sale|transaction|business combination)|\bmerged with and into\b"),
    ("Pending", r"(?:shareholders|stockholders) (?:of [^.]{0,40})?approved|received (?:all )?(?:required )?regulatory approval|special meeting|expected to close|subject to (?:customary )?closing conditions"),
    ("Announced", r"entered into (?:an?|the) (?:definitive )?(?:agreement and plan of merger|merger agreement|[\w ]{0,30}purchase agreement|business combination agreement)"),
]


def status_from_text(text: str) -> tuple[str, str] | None:
    """Most advanced deal status evidenced by the text (Terminated > Closed > Pending > Announced)."""
    sents = sentences(text)
    for status, pattern in STATUS_PATTERNS:
        for s in sents:
            if re.search(pattern, s, re.I):
                return status, s
    return None


# ----------------------------------------------------------------------------- rationale

_RATIONALE_RE = re.compile(
    r"\b(?:strategic|expand\w*|strengthen\w*|complement\w*|accelerat\w*|positions?|enhanc\w*|broaden\w*|extend\w*|"
    r"scale|footprint|capabilit\w+|combined company|combination (?:will|creates|brings)|adds?|diversif\w+)\b",
    re.I,
)
_BOILERPLATE_RE = re.compile(r"forward-looking|safe harbor|risks and uncertainties|should not place undue|no assurance|"
                             r"statements (?:that|which) are not historical|anticipated timing|expected to|may differ materially|"
                             r"incorporated (?:herein )?by reference|Exhibit \d|Item \d\.\d\d", re.I)


def extract_rationale(text: str, url: str) -> FieldValue:
    """Quote the first sentence explaining *why* the deal was done (verbatim, never paraphrased)."""
    for s in sentences(text):
        if len(s) > 400 or _BOILERPLATE_RE.search(s) or not s[0].isupper():
            continue
        if _RATIONALE_RE.search(s) and re.search(r"acqui|merger|combin|transaction|partnership|investment", s, re.I):
            return field(s, url, s)
    return undisclosed()


# ----------------------------------------------------------------------------- advisors & sponsors

ADVISOR_ROLE_WORDS = {
    "financial": r"financial advisors?|investment bank(?:er)?s?|M&A advisors?|exclusive (?:financial )?advisor|sell[- ]side advisor|buy[- ]side advisor",
    "legal": r"legal (?:counsel|advisors?)|counsel",
    "lender": r"lead arranger|lenders?|committed financing|debt financing",
}
_FIRM_HINT = re.compile(
    r"\b(?:LLP|LLC|L\.L\.C\.|Inc\.?|& Co\.?|Partners|Securities|Capital|Group|Bank|Advisors|Advisory|Sachs|Morgan|Lazard|Jefferies|"
    r"Baird|Houlihan|Evercore|Stifel|Piper|Raymond James|KeyBanc|Moelis|Guggenheim|Centerview|Barclays|Citi\w*|BofA|Wells Fargo|"
    r"Huntington|Comerica|Fifth Third|Honigman|Dickinson Wright|Dykema|Miller Canfield|Warner Norcross|Clark Hill|Varnum|Bodman|"
    r"Butzel|Kirkland|Wachtell|Skadden|Sullivan|Jones Day|Latham|Sidley|Foley|Squire|Davis Polk|Cravath|Paul, Weiss|Ropes|Lewis)\b"
)
_ADVISOR_RE = re.compile(
    r"(?P<firms>[A-Z][\w&.,'’\- ]{1,90}?)\s+(?:is|are|was|were|served|serve|serves|acted|act|is acting|are acting|is serving|are serving|"
    r"has been retained|have been retained|will act|will serve|acting|serving)\s+as\s+(?:the\s+|its\s+|their\s+)?(?:exclusive\s+|lead\s+|sole\s+|co-)?"
    r"(?P<role>financial advisors?|legal (?:counsel|advisors?)|counsel|M&A advisors?|investment bank(?:er)?s?|lead arranger|placement agents?)"
    r"(?:\s+(?:to|for)\s+(?P<client>[A-Z][\w&.'’\- ]{1,60}?))?(?=[,.;]|\s+and\s|\s+in connection|\s+on\s|$)"
)
_LENDER_RE = re.compile(
    r"(?:(?:debt )?financing (?:was |is |will be )?(?:provided|arranged|led|committed) by|(?:debt|committed) financing from)\s+"
    r"(?P<firms>[A-Z][\w&.,'’\- ]{1,90}?)(?=[,.;]|\s+and\s+[a-z]|$)"
)
_TEAM_RE = re.compile(r"(?:deal )?team (?:was |is )?led by (?P<people>(?:[A-Z][a-z]+(?: [A-Z]\.)? [A-Z][a-zA-Z'\-]+(?:,? (?:and )?)?){1,4})")


def _split_firms(raw: str) -> list[str]:
    raw = re.sub(r"^(?:and|while|with|The)\s+", "", raw.strip())
    parts = re.split(r",\s+and\s+|\s+and\s+(?=[A-Z])|;\s*", raw)
    firms = []
    for p in parts:
        p = p.strip(" ,")
        if 2 < len(p) <= 80 and _FIRM_HINT.search(p) and not re.match(r"(?:The )?(?:Company|Registrant|Parent|Buyer)\b", p):
            firms.append(p)
    return firms


def extract_advisors(text: str, url: str, party: Party | None = None, extra_firms: list[str] | None = None) -> list[dict]:
    """Financial advisors, legal counsel and lenders named in the text, with quotes."""
    found: dict[tuple[str, str], dict] = {}
    for s in sentences(text):
        if _BOILERPLATE_RE.search(s) and "advisor" not in s.lower():
            continue
        for m in _ADVISOR_RE.finditer(s):
            role_raw = m.group("role").lower()
            role = "legal" if ("counsel" in role_raw or "legal" in role_raw) else "lender" if "arranger" in role_raw else "financial"
            client_raw = (m.group("client") or "").strip()
            client = "Michigan party" if party and client_raw and re.fullmatch(party.pattern() + r"\b.*", client_raw) else (client_raw or None)
            for firm in _split_firms(m.group("firms")):
                found.setdefault((firm, role), {"firm": firm, "role": role, "client": client, "people": [], "source_url": url, "source_text": s, "method": "rule"})
        for m in _LENDER_RE.finditer(s):
            for firm in _split_firms(m.group("firms")):
                found.setdefault((firm, "lender"), {"firm": firm, "role": "lender", "client": None, "people": [], "source_url": url, "source_text": s, "method": "rule"})
        t = _TEAM_RE.search(s)
        if t:
            people = [p.strip() for p in re.split(r",\s*(?:and\s+)?|\s+and\s+", t.group("people")) if p.strip()]
            for adv in found.values():
                if adv["source_text"] == s or adv["firm"] in s:
                    adv["people"] = sorted(set(adv["people"]) | set(people))
    # DEFM14A / S-4 headings: "Opinion of Goldman Sachs & Co. LLC"
    for m in re.finditer(r"Opinion of (?P<firm>[A-Z][\w&.,' ]{2,60}?(?:LLC|L\.L\.C\.|Inc\.|& Co\.|LP|L\.P\.|Incorporated))", text[:600000]):
        firm = flatten(m.group("firm"))
        found.setdefault((firm, "financial"), {"firm": firm, "role": "financial", "client": "Michigan party" if party else None,
                                               "people": [], "source_url": url, "source_text": flatten(m.group(0)), "method": "rule"})
    return list(found.values())


SPONSOR_NAME_RE = re.compile(
    r"\b(?:Capital Partners|Equity Partners|Private Equity|Capital Management|Investment Partners|Growth Partners|"
    r"Partners,? L\.?P\.?|Fund [IVXL]+\b|Capital,? (?:LLC|L\.P\.|LP)|Equity,? (?:LLC|L\.P\.|LP)|Holdings,? L\.?P\.?)",
)
_PORTFOLIO_RE = re.compile(
    r"(?P<platform>[A-Z][\w&.'’\- ]{2,60}?),?\s+(?:a|an)\s+(?:\w+\s+){0,2}portfolio company of\s+(?P<sponsor>[A-Z][\w&.'’\- ]{2,60}?)(?=[,.;)]|\s+and\s|$)"
)
_SPONSOR_CONTEXT_RE = re.compile(r"(?:affiliates of|funds (?:managed|advised) by|backed by|private equity firm|investment firm)\s+(?P<sponsor>[A-Z][\w&.'’\- ]{2,60}?)(?=[,.;)]|\s+and\s|$)")


def extract_sponsor_context(text: str, url: str) -> dict[str, FieldValue]:
    """Detect add-ons ("X, a portfolio company of Y") and sponsor-backed buyers."""
    out: dict[str, FieldValue] = {}
    for s in sentences(text):
        m = _PORTFOLIO_RE.search(s)
        if m:
            out["platform"] = field(flatten(m.group("platform")), url, s)
            out["sponsor"] = field(flatten(m.group("sponsor")), url, s)
            out["is_add_on"] = field(True, url, s)
            return out
        m = _SPONSOR_CONTEXT_RE.search(s)
        if m and "sponsor" not in out:
            out["sponsor"] = field(flatten(m.group("sponsor")), url, s)
    return out
