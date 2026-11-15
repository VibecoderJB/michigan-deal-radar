"""Press-release wire and Michigan business-news RSS ingestion.

Only feed-provided fields are stored (headline, link, date, summary). Article pages are
never fetched. Items are kept when they (a) reference Michigan and (b) use deal language;
deal parties/terms are extracted from the headline and summary with rules.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache

import yaml

from .. import config
from ..extraction.entities import firms
from ..extraction.terms import MONEY_RE, money_value
from ..ingestion.web import RobotsDisallowed, WebClient
from ..models import field, source_confidence
from ..reference import geo

log = logging.getLogger(__name__)

DEAL_LANGUAGE = re.compile(
    r"\b(acquir\w*|acquisition|merger|merges?|merging|buys|bought|to buy|sells?|sold|sale of|divest\w*|invest(?:s|ment|ed)? in|"
    r"raises?|raised|funding|financing round|series [a-e]\b|seed round|recapitaliz\w+|growth equity|private equity|"
    r"portfolio company|add-on|platform (?:acquisition|investment)|takes? private|go(?:es|ing)? public|IPO)\b",
    re.I,
)
VALUE_LANGUAGE = re.compile(r"\b(valued at|transaction value|purchase price|consideration|deal (?:is )?worth|for \$)", re.I)
RUMOR = re.compile(r"\b(in talks|exploring (?:a )?sale|considering (?:a )?sale|weighs? sale|reportedly|people familiar|rumou?red|may sell|eyes)\b", re.I)
_TAG_RE = re.compile(r"<[^>]+>")

_PARTY = r"(?P<{g}>[A-Z0-9][\w&.,'’\- ]{{1,80}}?)"
HEADLINE_PATTERNS = [
    ("Closed", "M&A", re.compile(_PARTY.format(g="acq") + r",? (?i:(?:has )?(?:acquires|acquired|completes (?:the )?acquisition of|closes (?:the )?acquisition of|buys|bought|has purchased|purchases)) " + _PARTY.format(g="tgt") + r"(?=$|[,;:]| for | in | from | to | as | expanding| strengthening| adding)")),
    ("Announced", "M&A", re.compile(_PARTY.format(g="acq") + r",? (?i:to acquire|agrees to acquire|will acquire|announces (?:agreement to acquire|acquisition of|definitive agreement to acquire)|signs (?:definitive )?agreement to acquire|to buy) " + _PARTY.format(g="tgt") + r"(?=$|[,;:]| for | in | from | to | as )")),
    ("Closed", "M&A", re.compile(_PARTY.format(g="tgt") + r",? (?i:acquired by|sold to|joins|has been acquired by) " + _PARTY.format(g="acq") + r"(?=$|[,;:]| for | in | as )")),
    ("Announced", "M&A", re.compile(_PARTY.format(g="tgt") + r",? (?i:to be acquired by|agrees to be acquired by|to sell to|enters agreement to be acquired by) " + _PARTY.format(g="acq") + r"(?=$|[,;:]| for | in | as )")),
    ("Closed", "Financing", re.compile(_PARTY.format(g="tgt") + r",? (?i:raises|secures|closes|lands|announces) (?:a )?(?P<amt>\$[\d.,]+\s?(?:million|billion|M|B)\b)?[^.]{0,40}?(?P<round>(?i:Series [A-E]\d?|seed|pre-seed|growth|funding|financing|investment))")),
    ("Closed", "Financing", re.compile(_PARTY.format(g="acq") + r",? (?i:invests in|makes (?:a |an )?(?:strategic |growth |minority )?investment in|leads (?:\$[\d.,]+\s?(?:million|billion|M|B) )?investment in) " + _PARTY.format(g="tgt") + r"(?=$|[,;:]| to | as | for )")),
]


@dataclass
class NewsResult:
    items: list[dict] = dc_field(default_factory=list)
    errors: list[dict] = dc_field(default_factory=list)
    feeds: list[dict] = dc_field(default_factory=list)


def load_feeds() -> list[dict]:
    path = config.CONFIG_DIR / "sources.yml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("feeds", [])


@lru_cache(maxsize=1)
def michigan_terms() -> list[tuple[str, re.Pattern]]:
    """'Michigan', larger Michigan cities, and Michigan-based watchlist firms."""
    data = geo._data()
    cities = sorted({c["name"] for c in data["cities"].values() if (c.get("population") or 0) >= 25000}, key=len, reverse=True)
    names = ["Michigan", "Mich.", "Upper Peninsula", "Metro Detroit", "West Michigan", *cities]
    for entries in firms().values():
        names += [e["name"] for e in entries if "MI" in (e.get("hq") or "")]
    return [(n, re.compile(r"\b" + re.escape(n) + r"\b")) for n in dict.fromkeys(names)]


def michigan_reference(text: str) -> str | None:
    for name, pattern in michigan_terms():
        if pattern.search(text):
            return name
    return None


def _clean(s: str | None) -> str:
    s = html.unescape(_TAG_RE.sub(" ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).date().isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def parse_feed(xml_text: str) -> list[dict]:
    """RSS 2.0 or Atom -> [{title, link, published, summary}]."""
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    items = []
    for it in root.iter("item"):
        items.append({"title": _clean(it.findtext("title")), "link": (it.findtext("link") or "").strip(),
                      "published": _date(it.findtext("pubDate") or it.findtext("date")), "summary": _clean(it.findtext("description"))[:600]})
    for it in root.iter("entry"):
        link_el = it.find("link")
        items.append({"title": _clean(it.findtext("title")), "link": (link_el.get("href") if link_el is not None else "") or "",
                      "published": _date(it.findtext("published") or it.findtext("updated")), "summary": _clean(it.findtext("summary"))[:600]})
    return [i for i in items if i["title"] and i["link"]]


def _trim_party(name: str) -> str:
    name = re.sub(r"^(?:Michigan(?:-based)?|Detroit(?:-based)?|Grand Rapids(?:-based)?|Ann Arbor(?:-based)?)\s+", "", name.strip(" ,"))
    name = re.sub(r"\s+(?:Inc|LLC|Corp)\.?$", lambda m: m.group(0), name)
    return name.strip(" ,'’\"")


def extract_deal(title: str, summary: str, url: str) -> dict | None:
    """Rule-based deal extraction from a headline (summary used only for value/round)."""
    for status, category, pattern in HEADLINE_PATTERNS:
        m = pattern.search(title)
        if not m:
            continue
        gd = m.groupdict()
        acq = _trim_party(gd["acq"]) if gd.get("acq") else None
        tgt = _trim_party(gd["tgt"]) if gd.get("tgt") else None
        if (acq and len(acq) < 2) or (tgt and len(tgt) < 2):
            continue
        out = {
            "category": category,
            "status": field("Rumored" if RUMOR.search(title) else status, url, title),
            "acquirer": field(acq, url, title) if acq else field(None),
            "target": field(tgt, url, title) if tgt else field(None),
            "value": field(None),
            "round": field(gd.get("round"), url, title) if gd.get("round") else field(None),
        }
        for text in (title, summary):
            for mm in MONEY_RE.finditer(text):
                v = money_value(mm)
                if v and v >= 100_000 and (DEAL_LANGUAGE.search(text) or VALUE_LANGUAGE.search(text)):
                    out["value"] = field(v, url, text)
                    break
            if out["value"]["value"]:
                break
        return out
    return None


def item_record(feed: dict, raw: dict) -> dict | None:
    text = f"{raw['title']} {raw['summary']}"
    mi = michigan_reference(text)
    if not mi or not DEAL_LANGUAGE.search(text):
        return None
    kind = "Press release" if feed.get("kind") == "press_release" else "News"
    extracted = extract_deal(raw["title"], raw["summary"], raw["link"])
    return {
        "event_id": "N-" + hashlib.sha1(raw["link"].encode()).hexdigest()[:12],
        "kind": "news",
        "url": raw["link"],
        "title": raw["title"],
        "summary": raw["summary"] if not feed.get("paywalled") else "",
        "publisher": feed.get("publisher"),
        "source_kind": kind,
        "confidence": "Low" if extracted and extracted["status"]["value"] == "Rumored" else source_confidence(kind),
        "filed": raw.get("published") or date.today().isoformat(),
        "michigan_reference": mi,
        "extracted": extracted,
    }


def collect_news(known: set[str], client: WebClient | None = None) -> NewsResult:
    result = NewsResult()
    client = client or WebClient()
    for feed in load_feeds():
        status = {"name": feed["name"], "url": feed["url"], "ok": False, "items": 0, "kept": 0}
        try:
            raw_items = parse_feed(client.get(feed["url"]).text)
            status.update(ok=True, items=len(raw_items))
            for raw in raw_items:
                rec = item_record(feed, raw)
                if rec and rec["event_id"] not in known:
                    result.items.append(rec)
                    status["kept"] += 1
        except RobotsDisallowed as exc:
            status["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - one broken feed never stops the run
            status["error"] = f"{type(exc).__name__}: {exc}"[:200]
            result.errors.append({"source": feed["name"], "accession": None, "error": status["error"]})
        result.feeds.append(status)
    return result
