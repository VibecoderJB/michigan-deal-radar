"""Merge news/press-release items into SEC-backed deals, or create news-sourced deals.

A news item joins an existing deal when either party name matches and the dates are within
120 days. Otherwise items about the same parties are grouped into one news-sourced deal.
News never overwrites a value an SEC filing already disclosed; it only fills gaps.
"""

from __future__ import annotations

from ..extraction.entities import buyer_type, same_entity
from ..models import SCHEMA_VERSION, deal_confidence, field, is_disclosed, undisclosed, val
from .linking import _days, deal_summary, deal_title, named_party, stable_id, unknown_party

STATUS_RANK = {"Rumored": 0, "Announced": 1, "Pending": 2, "Closed": 3, "Terminated": 4}


def _source(item: dict) -> dict:
    return {"url": item["url"], "title": item["title"], "publisher": item.get("publisher"), "kind": item["source_kind"],
            "date": item["filed"], "confidence": item["confidence"], "accession": item["event_id"]}


def _matches(deal: dict, ex: dict, when: str) -> bool:
    names = [val(deal["target"]["name"]), val(deal["acquirer"]["name"])]
    t, a = val(ex.get("target")), val(ex.get("acquirer"))
    hit = (t and any(same_entity(t, n) for n in names if n)) or (a and t and any(same_entity(a, n) for n in names if n))
    anchor = val(deal.get("announcement_date")) or ""
    return bool(hit) and bool(anchor) and _days(anchor, when) <= 120


def link_news(deals: list[dict], news: list[dict]) -> list[dict]:
    news_deals: list[dict] = []
    for item in sorted(news, key=lambda i: i["filed"]):
        ex = item.get("extracted")
        if not ex:
            continue
        deal = next((d for d in deals + news_deals if _matches(d, ex, item["filed"])), None)
        if deal:
            deal["sources"].append(_source(item))
            deal["timeline"].append({"date": item["filed"], "status": val(ex["status"]), "event": f"{item['publisher']}: {item['title']}",
                                     "source_url": item["url"], "source_text": item["title"]})
            deal["timeline"].sort(key=lambda t: t["date"])
            fin = deal["financials"]
            if is_disclosed(ex.get("value")) and not any(is_disclosed(fin.get(k)) for k in ("enterprise_value", "transaction_value", "equity_value", "amount_raised")):
                fin["transaction_value" if deal["category"] == "M&A" else "amount_raised"] = ex["value"]
            if STATUS_RANK.get(val(ex["status"]), 0) > STATUS_RANK.get(val(deal["status"]), 0) and item["source_kind"] == "Press release":
                deal["status"] = ex["status"]
            deal["confidence"] = deal_confidence(deal["sources"])
            if deal.get("deal_id", "").startswith("NEWS"):
                deal["summary"] = deal_summary(deal)
            continue
        news_deals.append(_new_deal(item, ex))
    return deals + news_deals


def _new_deal(item: dict, ex: dict) -> dict:
    target = named_party(ex["target"]) if is_disclosed(ex.get("target")) else unknown_party("Not named in headline")
    acquirer = named_party(ex["acquirer"]) if is_disclosed(ex.get("acquirer")) else unknown_party("Not named in headline")
    bt = buyer_type(val(acquirer["name"]), item["title"])
    acquirer["type"] = field(bt[0], item["url"], bt[1], "derived") if bt else undisclosed()
    acquirer["is_add_on"] = field(None)
    acquirer["platform"] = undisclosed()
    acquirer["sponsor"] = undisclosed()
    financing = ex["category"] == "Financing"
    if financing:
        rnd = (val(ex.get("round")) or "").lower()
        dtype = "Venture Round" if rnd.startswith(("series", "seed", "pre-seed")) else "Growth Equity"
        deal_type = field(dtype, item["url"], item["title"], note="classified from headline wording")
    else:
        dtype = "PE Buyout" if bt and bt[0] == "Financial Sponsor" else "Acquisition"
        deal_type = field(dtype, item["url"], item["title"], "derived")
    financials = {k: undisclosed() for k in ("enterprise_value", "equity_value", "transaction_value", "price_per_share", "revenue", "ebitda", "ev_revenue", "ev_ebitda", "consideration")}
    if financing:
        financials["amount_raised"] = ex.get("value") or undisclosed()
    else:
        financials["transaction_value"] = ex.get("value") or undisclosed()
    src = _source(item)
    deal = {
        "deal_id": stable_id("NEWS", item["url"]),
        "schema_version": SCHEMA_VERSION,
        "category": "Financing" if financing else "M&A",
        "deal_type": deal_type,
        "status": ex["status"],
        "announcement_date": field(item["filed"], item["url"], f"{item['publisher']}, published {item['filed']}", "filing_metadata", note="publication date"),
        "closing_date": undisclosed(),
        "target": target,
        "acquirer": acquirer,
        "seller": None,
        "advisors": [],
        "financials": financials,
        "rationale": undisclosed(),
        "michigan_link": "Party",
        "michigan_reference": item.get("michigan_reference"),
        "focus_sector": None,
        "sources": [src],
        "confidence": item["confidence"],
        "timeline": [{"date": item["filed"], "status": val(ex["status"]), "event": f"{item['publisher']}: {item['title']}",
                      "source_url": item["url"], "source_text": item["title"]}],
        "flags": ["news_only"] + (["single_unconfirmed_report"] if item["confidence"] == "Low" else []),
        "legacy_ids": [],
    }
    deal["title"] = deal_title(deal)
    deal["summary"] = deal_summary(deal)
    return deal
