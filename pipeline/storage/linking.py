"""Build the published datasets from evidence events.

* M&A: SEC events about the same transaction are clustered into one deal (by the
  merger agreement's signing date, then by counterparty name, then by "closing follows
  announcement"), so a deal announced in June and closed in November is one record with a
  timeline instead of three rows. Filings by *both* parties (two Michigan public companies)
  are merged too.
* Financings: Form D offerings (operating companies) and 8-K credit facilities/notes.
* Capital formation: pooled-fund and real-estate Form Ds (kept out of deal counts).
* Ownership: Schedule 13D stakes.

Everything is deterministic: the same evidence always produces the same datasets.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date

from ..extraction.entities import buyer_type, canonical_firm, normalize_name, same_entity
from ..models import (
    NOT_DISCLOSED,
    SCHEMA_VERSION,
    FieldValue,
    Source,
    deal_confidence,
    field,
    is_disclosed,
    source_confidence,
    undisclosed,
    val,
)
from ..reference import geo, gics
from ..textutil import describe_securities, display_name, money, pick_ticker

CENSUS_URL = geo.CENSUS_COUNTIES_URL
STATUS_RANK = {"Rumored": 0, "Announced": 1, "Pending": 2, "Closed": 3, "Terminated": 4}


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)


def stable_id(prefix: str, anchor: str) -> str:
    return f"{prefix}-{hashlib.sha1(anchor.encode()).hexdigest()[:10]}"


# ----------------------------------------------------------------------------- parties

def _location_fields(city: str | None, zip_code: str | None, url: str, quote: str | None) -> dict[str, FieldValue]:
    out: dict[str, FieldValue] = {
        "city": field(city, url, quote, "filing_metadata"),
        "state": field("MI" if city or zip_code else None, url, quote, "filing_metadata"),
        "county": undisclosed(),
        "region": undisclosed(),
    }
    loc = geo.locate(city, zip_code)
    if loc:
        basis = f"{city or ''} {('ZIP ' + str(zip_code)) if loc.method == 'zip' else ''}".strip()
        out["county"] = field(loc.county, CENSUS_URL, f"{basis} -> {loc.county} (Census county boundaries; matched by {loc.method})", "derived")
        out["region"] = field(loc.region, CENSUS_URL, f"{loc.county} -> {loc.region} (Deal Radar region definition)", "derived")
    return out


def _industry_fields_from_sic(sic: str | None, url: str) -> dict[str, FieldValue]:
    mapped = gics.from_sic(sic)
    if not mapped:
        return {"gics_sector": undisclosed(), "gics_sub_industry": undisclosed(), "focus_sector": undisclosed()}
    quote = f"SEC SIC code {sic}"
    return {
        "gics_sector": field(mapped[0], url, quote, "derived", note=f"mapped from SIC {sic}"),
        "gics_sub_industry": field(mapped[1], url, quote, "derived", note=f"mapped from SIC {sic}"),
        "focus_sector": field(gics.focus_sector(*mapped), url, quote, "derived"),
    }


def filer_party(event: dict) -> dict:
    """A Michigan SEC filer as a deal party, every field sourced from EDGAR metadata."""
    f = event["filer"]
    url = event["url"]
    name = display_name(f["name"])
    ticker = pick_ticker(f.get("tickers"), f["name"])
    loc_quote = f"EDGAR business address: {f.get('city') or 'n/a'}, {f.get('state') or ''}".strip(", ")
    party = {
        "name": field(name, url, f"EDGAR filer: {f['name']} (CIK {f['cik']})", "filing_metadata"),
        "cik": f["cik"],
        "ticker": field(ticker, url, f"EDGAR ticker(s): {', '.join(f.get('tickers') or [])}", "filing_metadata"),
        "public_private": field("Public", url, f"Listed ticker(s): {', '.join(f['tickers'])}", "filing_metadata")
        if f.get("tickers") else field(None),
        **_location_fields(f.get("city") if f.get("state") == "MI" else None, None, url, loc_quote),
        **_industry_fields_from_sic(f.get("sic"), url),
    }
    if f.get("state") and f.get("state") != "MI":
        party["state"] = field(f["state"], url, loc_quote, "filing_metadata")
        party["city"] = field(f.get("city"), url, loc_quote, "filing_metadata")
    party["hq"] = field(", ".join(x for x in (f.get("city"), f.get("state")) if x) or None, url, loc_quote, "filing_metadata")
    return party


_LISTING_RE = re.compile(r"\((?:NASDAQ|Nasdaq|NYSE(?: American)?|OTCQX|OTCQB|TSX)\s*:\s*([A-Z.]{1,6})\)")


def named_party(name_field: FieldValue) -> dict:
    """A counterparty known only by name from filing text."""
    name = val(name_field)
    quote = name_field.get("source_text") or ""
    listing = None
    if name:
        m = re.search(re.escape(name.split(",")[0]) + r"[^.]{0,40}?" + _LISTING_RE.pattern, quote)
        listing = m.group(1) if m else None
    empty = {k: undisclosed() for k in ("city", "state", "county", "region", "hq", "gics_sector", "gics_sub_industry", "focus_sector")}
    return {
        "name": dict(name_field),
        "cik": None,
        "ticker": field(listing, name_field.get("source_url"), quote) if listing else undisclosed(),
        "public_private": field("Public", name_field.get("source_url"), quote) if listing else undisclosed(),
        **empty,
    }


def unknown_party(note: str) -> dict:
    p = named_party(undisclosed())
    p["name"]["note"] = note
    return p


# ----------------------------------------------------------------------------- M&A

class _Cluster:
    def __init__(self, event: dict):
        self.events: list[dict] = []
        self.add(event)

    def add(self, e: dict) -> None:
        self.events.append(e)

    @property
    def ciks(self) -> set[str]:
        return {e["filer"]["cik"] for e in self.events}

    @property
    def names(self) -> list[str]:
        return [e["filer"]["name"] for e in self.events]

    @property
    def counterparties(self) -> list[str]:
        return [val(e.get("counterparty")) for e in self.events if val(e.get("counterparty"))]

    @property
    def agreement_dates(self) -> set[str]:
        return {val(e.get("agreement_date")) for e in self.events if val(e.get("agreement_date"))}

    @property
    def last_filed(self) -> str:
        return max(e["filed"] for e in self.events)

    @property
    def status(self) -> str:
        return max((val(e.get("status"), "Announced") for e in self.events), key=lambda s: STATUS_RANK.get(s, 0))


def _related(c: _Cluster, e: dict) -> bool:
    """Same Michigan filer, or the other side of the deal (two Michigan filers)."""
    cik, name, cp = e["filer"]["cik"], e["filer"]["name"], val(e.get("counterparty"))
    if cik in c.ciks:
        return True
    if cp and any(same_entity(cp, n) for n in c.names):
        return True
    return any(same_entity(name, x) for x in c.counterparties)


def cluster_ma_events(events: list[dict]) -> list[list[dict]]:
    """Group M&A evidence events that describe the same transaction."""
    clusters: list[_Cluster] = []
    for e in sorted(events, key=lambda x: (x["filed"], x["event_id"])):
        ad = val(e.get("agreement_date"))
        cp = val(e.get("counterparty"))
        status = val(e.get("status"), "Announced")
        cands = [c for c in clusters if _related(c, e)]
        match = None
        if ad:
            match = next((c for c in cands if ad in c.agreement_dates), None)
        if match is None and cp:
            match = next(
                (c for c in reversed(cands)
                 if (any(same_entity(cp, x) for x in c.counterparties + [n for n in c.names if n != e["filer"]["name"]]))
                 and _days(e["filed"], c.last_filed) <= 730
                 and not (ad and c.agreement_dates and ad not in c.agreement_dates)),
                None,
            )
        if match is None and not ad and not cp and status in ("Closed", "Pending", "Terminated"):
            open_ = [c for c in cands if e["filer"]["cik"] in c.ciks and c.status not in ("Closed", "Terminated")
                     and _days(e["filed"], c.last_filed) <= 540]
            match = open_[-1] if open_ else None
        if match:
            match.add(e)
        else:
            clusters.append(_Cluster(e))
    return [c.events for c in clusters]


_EVENT_PRIORITY = {"2.01": 0, "DEFM14A": 1, "SC 14D9": 1, "S-4": 2, "SC TO-T": 2, "1.01": 3, "8.01": 4, "7.01": 5}


def _priority(e: dict) -> int:
    form = (e.get("form") or "").upper()
    keys = [form] + list(e.get("items") or [])
    return min((_EVENT_PRIORITY.get(k, 9) for k in keys), default=9)


def _event_label(e: dict) -> str:
    form = e.get("form") or ""
    items = [i for i in e.get("items") or [] if i in ("1.01", "1.02", "2.01", "7.01", "8.01")]
    labels = {"1.01": "definitive agreement", "1.02": "termination", "2.01": "completion", "7.01": "Reg FD", "8.01": "other events"}
    detail = ", ".join(f"Item {i} {labels[i]}" for i in items)
    return f"{display_name(e['filer']['name'])} {form}" + (f" ({detail})" if detail else "")


def _source_from_event(e: dict) -> Source:
    kind = f"SEC {e.get('form') or 'filing'}"
    src: Source = {"url": e["url"], "title": _event_label(e), "publisher": "SEC EDGAR", "kind": kind, "date": e["filed"],
                   "confidence": source_confidence(kind), "accession": e["event_id"]}
    return src


def build_ma_deal(events: list[dict]) -> dict:
    events = sorted((dict(e) for e in events), key=lambda e: (e["filed"], e["event_id"]))  # copies: evidence stays untouched
    by_priority = sorted(events, key=_priority)
    flags: list[str] = []

    # --- roles
    for e in by_priority:  # verified LLM gap-fill only where rules found nothing
        llm = e.get("llm") or {}
        if not val(e.get("role")) and val(llm.get("role")) not in (None, "unknown"):
            e["role"] = llm["role"]
            if not val(e.get("counterparty")) and val(llm.get("counterparty")):
                e["counterparty"] = llm["counterparty"]
    roles = [(val(e.get("role")), e) for e in by_priority if val(e.get("role"))]
    role_counts = Counter(r for r, _ in roles)
    target = acquirer = None
    seller = None
    role_evidence: FieldValue | None = None
    for role, e in roles:
        if role == "target" and target is None:
            target = filer_party(e)
            role_evidence = e["role"]
            if is_disclosed(e.get("counterparty")) and acquirer is None:
                acquirer = named_party(e["counterparty"])
        elif role == "acquirer" and (acquirer is None or acquirer.get("cik") is None):
            acquirer = filer_party(e)
            role_evidence = role_evidence or e["role"]
            if is_disclosed(e.get("counterparty")) and target is None:
                target = named_party(e["counterparty"])
        elif role == "seller" and seller is None:
            seller = filer_party(e)
            role_evidence = role_evidence or e["role"]
            if is_disclosed(e.get("counterparty")) and acquirer is None:
                acquirer = named_party(e["counterparty"])
    primary = by_priority[0]
    if target is None and acquirer is None and seller is None:
        flags.append("roles_unresolved")
    if seller is not None and target is None:
        target = unknown_party(f"Business divested by {val(seller['name'])}; name not stated in the filing")
    target = target or unknown_party("Not identified in the source text")
    acquirer = acquirer or unknown_party("Not identified in the source text")
    if len(role_counts) > 1 and len({e["filer"]["cik"] for _, e in roles}) == 1:
        flags.append("conflicting_role_signals")

    # --- sponsor / add-on context
    sponsor_ctx: dict[str, FieldValue] = {}
    for e in by_priority:
        for k, v in (e.get("sponsor_context") or {}).items():
            sponsor_ctx.setdefault(k, v)
    acq_name = val(acquirer["name"])
    context_text = " ".join(filter(None, [val(e.get("rationale")) or "" for e in events] + [e.get("excerpt") or "" for e in events]))
    bt = buyer_type(acq_name, context_text) if acq_name else None
    if sponsor_ctx.get("sponsor") and (not bt or bt[0] == "Strategic") and is_disclosed(sponsor_ctx.get("is_add_on")):
        acquirer["type"] = field("Financial Sponsor", sponsor_ctx["sponsor"]["source_url"], sponsor_ctx["sponsor"]["source_text"],
                                 note="buyer is a portfolio company of a financial sponsor")
    elif bt:
        acquirer["type"] = field(bt[0], primary["url"], bt[1], "derived")
    else:
        acquirer["type"] = undisclosed()
    acquirer["is_add_on"] = sponsor_ctx.get("is_add_on") or field(None)
    acquirer["platform"] = sponsor_ctx.get("platform") or undisclosed()
    acquirer["sponsor"] = sponsor_ctx.get("sponsor") or undisclosed()

    # --- deal type
    any_ev = by_priority[0]
    if seller is not None:
        deal_type = field("Divestiture / Carve-out", role_evidence["source_url"], role_evidence["source_text"])
    elif is_disclosed(acquirer["is_add_on"]):
        deal_type = field("Add-on", acquirer["is_add_on"]["source_url"], acquirer["is_add_on"]["source_text"])
    elif val(acquirer["type"]) == "Financial Sponsor":
        deal_type = field("PE Buyout", acquirer["type"]["source_url"], acquirer["type"]["source_text"], "derived")
    elif any(e.get("recapitalization") for e in events):
        e = next(e for e in events if e.get("recapitalization"))
        deal_type = field("Recapitalization", e["doc_url"], e.get("excerpt"))
    elif any(e.get("merger_of_equals") for e in events):
        deal_type = field("Merger", any_ev["doc_url"], "Described as a merger of equals in the filing")
    else:
        ev = role_evidence or any_ev.get("status")
        deal_type = field("Acquisition", (ev or {}).get("source_url") or any_ev["url"], (ev or {}).get("source_text") or any_ev.get("excerpt"),
                          "derived", note="default M&A type when no merger-of-equals, sponsor or divestiture indicators")

    # --- status & dates
    latest = max(events, key=lambda e: (e["filed"], STATUS_RANK.get(val(e.get("status"), "Announced"), 0)))
    status_event = max(events, key=lambda e: (STATUS_RANK.get(val(e.get("status"), "Announced"), 0) if val(e.get("status")) != "Terminated" or e is latest else -1, e["filed"]))
    status = dict(status_event["status"])
    agreement = next((e["agreement_date"] for e in events if is_disclosed(e.get("agreement_date"))), None)
    first = events[0]
    announcement = dict(agreement) if agreement else field(first["filed"], first["url"], f"{_event_label(first)} filed {first['filed']}",
                                                         "filing_metadata", note="date of first SEC filing about the deal")
    closing: FieldValue = undisclosed()
    if val(status) == "Closed":
        close_ev = next((e for e in reversed(events) if val(e.get("status")) == "Closed"), None)
        if close_ev and is_disclosed(close_ev.get("closing_date")):
            closing = dict(close_ev["closing_date"])
        elif close_ev:
            closing = field(close_ev["filed"], close_ev["url"], f"{_event_label(close_ev)} filed {close_ev['filed']}", "filing_metadata",
                            estimate=True, note="closing date not stated; 8-K filing date used (filed within 4 business days of closing)")

    # --- financials
    fin: dict[str, FieldValue] = {}
    for e in by_priority:
        for k, v in (e.get("financials") or {}).items():
            if is_disclosed(v):
                fin.setdefault(k, v)
    keys = ("enterprise_value", "equity_value", "transaction_value", "price_per_share", "revenue", "ebitda", "ev_revenue", "ev_ebitda", "consideration")
    financials = {k: fin.get(k) or undisclosed() for k in keys}
    ev_basis = val(financials["enterprise_value"])
    basis_name = "enterprise value"
    if ev_basis is None and val(financials["transaction_value"]) is not None:
        ev_basis, basis_name = val(financials["transaction_value"]), "transaction value (EV proxy)"
    for metric, mult in (("revenue", "ev_revenue"), ("ebitda", "ev_ebitda")):
        if not is_disclosed(financials[mult]) and ev_basis and val(financials[metric]):
            financials[mult] = field(
                round(ev_basis / val(financials[metric]), 2), financials[metric]["source_url"],
                f"{basis_name} {money(ev_basis)} / {metric} {money(val(financials[metric]))}", "derived",
                estimate=basis_name != "enterprise value", note=f"computed from disclosed {basis_name} and {metric}",
            )

    # --- advisors
    advisors: dict[tuple[str, str], dict] = {}
    for e in by_priority:
        for a in e.get("advisors") or []:
            firm = canonical_firm(a["firm"])
            key = (firm, a["role"])
            if key not in advisors:
                advisors[key] = {**a, "firm": firm}
            else:
                advisors[key]["people"] = sorted(set(advisors[key].get("people") or []) | set(a.get("people") or []))

    rationale = next((e["rationale"] for e in by_priority if is_disclosed(e.get("rationale"))), undisclosed())
    sources = [_source_from_event(e) for e in events]
    timeline = [
        {
            "date": e["filed"],
            "status": val(e.get("status")),
            "event": _event_label(e),
            "source_url": e["url"],
            "source_text": (e.get("status") or {}).get("source_text") or e.get("excerpt"),
        }
        for e in events
    ]
    if is_disclosed(agreement):
        timeline.insert(0, {"date": val(agreement), "status": "Announced", "event": "Definitive agreement signed",
                            "source_url": agreement["source_url"], "source_text": agreement["source_text"]})
    if is_disclosed(closing) and not closing.get("estimate"):
        timeline.append({"date": val(closing), "status": "Closed", "event": "Transaction completed",
                         "source_url": closing["source_url"], "source_text": closing["source_text"]})
    timeline.sort(key=lambda t: t["date"])

    mi_target = val(target["state"]) == "MI"
    mi_acquirer = val(acquirer["state"]) == "MI" or val(seller["state"]) == "MI" if seller else val(acquirer["state"]) == "MI"
    michigan_link = "Both" if mi_target and mi_acquirer else "Target" if mi_target else "Acquirer" if mi_acquirer else "Party"
    focus = val(target.get("focus_sector")) or val(acquirer.get("focus_sector"))
    for name in ("enterprise_value", "transaction_value", "equity_value"):
        if is_disclosed(financials[name]):
            break
    else:
        flags.append("value_not_disclosed")

    deal = {
        "deal_id": stable_id("MDR", events[0]["event_id"]),
        "schema_version": SCHEMA_VERSION,
        "category": "M&A",
        "deal_type": deal_type,
        "status": status,
        "announcement_date": announcement,
        "closing_date": closing,
        "target": target,
        "acquirer": acquirer,
        "seller": seller,
        "advisors": sorted(advisors.values(), key=lambda a: (a["role"], a["firm"])),
        "financials": financials,
        "rationale": rationale,
        "michigan_link": michigan_link,
        "focus_sector": focus,
        "sources": sources,
        "confidence": deal_confidence(sources),
        "timeline": timeline,
        "flags": flags,
        "legacy_ids": [f"8K-{e['event_id']}" for e in events],
    }
    deal["title"] = deal_title(deal)
    deal["summary"] = deal_summary(deal)
    return deal


def _name(party: dict | None, fallback: str = "Undisclosed party") -> str:
    return (val(party["name"]) if party else None) or fallback


def deal_title(d: dict) -> str:
    t, a, s = _name(d["target"], "undisclosed target"), _name(d["acquirer"], "undisclosed buyer"), d.get("seller")
    status = val(d["status"])
    if "roles_unresolved" in d["flags"]:
        parties = [p for p in {val(d["target"]["name"]), val(d["acquirer"]["name"])} if p]
        names = [display_name(src["title"].split(" SEC")[0]) for src in d["sources"][:1]]
        return f"{names[0] if names else 'Michigan company'}: M&A transaction" + (f" with {parties[0]}" if parties else "")
    if s:
        verb = {"Closed": "sold", "Terminated": "terminated sale of"}.get(status, "to sell")
        return f"{_name(s)} {verb} {t if val(d['target']['name']) else 'business'} to {a}"
    if d["category"] == "Financing":
        return f"{t}: {val(d['deal_type']).lower()}"
    verb = {"Closed": "acquired", "Terminated": "terminated deal for", "Pending": "to acquire", "Announced": "to acquire", "Rumored": "reportedly in talks for"}.get(status, "to acquire")
    return f"{a} {verb} {t}"


def deal_summary(d: dict) -> str:
    """One-sentence, template-built description (no AI)."""
    f = d["financials"]
    value = val(f.get("enterprise_value")) or val(f.get("transaction_value")) or val(f.get("equity_value"))
    bits = [deal_title(d)]
    if value:
        bits.append(f"for {money(value)}")
    cons = val(f.get("consideration"))
    if cons:
        bits.append(f"({cons.lower()})")
    date_s = val(d["closing_date"]) if val(d["status"]) == "Closed" else val(d["announcement_date"])
    s = " ".join(bits)
    if date_s:
        s += f"; {val(d['status']).lower()} {date_s}"
    return s + "."


# ----------------------------------------------------------------------------- financings

def _formd_groups(events: list[dict]) -> list[list[dict]]:
    groups: dict[str, list[dict]] = {}
    for e in sorted(events, key=lambda x: (x["filed"], x["event_id"])):
        key = f"{e['filer']['cik']}-{e.get('file_number') or e['event_id']}"
        groups.setdefault(key, []).append(e)
    return list(groups.values())


def _q(e: dict, *tags: str) -> str:
    quotes = e.get("quotes") or {}
    return "; ".join(q for q in (quotes.get(t) for t in tags) if q) or "Form D XML"


def build_formd_record(events: list[dict]) -> tuple[str, dict]:
    """Returns (dataset, record) where dataset is 'deals' or 'capital_formation'."""
    events = sorted(events, key=lambda e: (e["filed"], e["event_id"]))
    latest, first = events[-1], events[0]
    p = latest["parsed"]
    url = latest["doc_url"]
    issuer = display_name(p.get("issuer_name")) or display_name(latest["filer"]["name"])
    mapped = gics.from_form_d(p.get("industry"))
    industry_quote = _q(latest, "industryGroupType", "investmentFundType")
    loc = _location_fields(p.get("city"), p.get("zip"), url, _q(latest, "city", "zipCode"))
    raised = field(p.get("total_amount_sold"), url, _q(latest, "totalAmountSold"), "filing_metadata")
    if p.get("offering_indefinite"):
        size = {"value": None, "source_url": url, "source_text": _q(latest, "totalOfferingAmount"), "method": "filing_metadata", "note": "Indefinite"}
    else:
        size = field(p.get("total_offering_amount"), url, _q(latest, "totalOfferingAmount"), "filing_metadata")
    timeline = [{"date": e["filed"], "status": "Amended" if e["parsed"].get("is_amendment") else "Filed",
                 "event": f"Form {'D/A' if e['parsed'].get('is_amendment') else 'D'}: {money(e['parsed'].get('total_amount_sold'), 'n.d.')} sold",
                 "source_url": e["url"], "source_text": _q(e, "totalAmountSold")} for e in events]
    sources = [{"url": e["url"], "title": f"{issuer} Form {'D/A' if e['parsed'].get('is_amendment') else 'D'}", "publisher": "SEC EDGAR",
                "kind": "SEC Form D", "date": e["filed"], "confidence": "High", "accession": e["event_id"]} for e in events]
    people = [{"name": r["name"], "roles": r.get("roles", []), "source_url": url} for r in (p.get("related_persons") or [])[:12]]
    base_id = f"D-{latest['filer']['cik']}-{latest.get('file_number')}" if latest.get("file_number") else f"D-{first['event_id']}"

    if p.get("is_pooled_fund") or p.get("industry") in gics.REAL_ESTATE_FORM_D:
        category = p.get("fund_type") or ("Real Estate" if p.get("industry") in gics.REAL_ESTATE_FORM_D else "Pooled Investment Fund")
        rec = {
            "id": stable_id("CF", base_id),
            "name": field(issuer, url, _q(latest, "entityName"), "filing_metadata"),
            "cik": latest["filer"]["cik"],
            "category": field(category, url, industry_quote, "filing_metadata"),
            **{k: loc[k] for k in ("city", "county", "region")},
            "offering_size": size,
            "amount_raised": raised,
            "investor_count": field(p.get("investor_count"), url, _q(latest, "totalNumberAlreadyInvested"), "filing_metadata"),
            "first_sale_date": field(p.get("date_of_first_sale"), url, _q(latest, "value"), "filing_metadata"),
            "filed": latest["filed"],
            "first_filed": first["filed"],
            "people": people,
            "timeline": timeline,
            "sources": sources,
            "legacy_ids": [base_id],
        }
        return "capital_formation", rec

    sec = p.get("securities") or []
    within5 = (latest.get("quotes") or {}).get("withinFiveYears")
    if p.get("is_business_combination"):
        deal_type = field("Acquisition", url, _q(latest, "isBusinessCombinationTransaction"), "filing_metadata",
                          note="Form D securities issued in connection with a business combination")
        category = "M&A"
    elif sec and all(s == "Debt" for s in sec):
        deal_type = field("Debt Raise", url, _q(latest, "isDebtType"), "filing_metadata")
        category = "Financing"
    elif within5 and "true" in within5:
        deal_type = field("Venture Round", url, f"{within5}; {describe_securities(sec)}", "derived",
                          note="issuer incorporated within the last five years")
        category = "Financing"
    else:
        deal_type = field("Growth Equity", url, f"{within5 or 'year of incorporation > 5 years'}; {describe_securities(sec)}", "derived",
                          note="private placement by an issuer older than five years")
        category = "Financing"

    target = {
        "name": field(issuer, url, _q(latest, "entityName"), "filing_metadata"),
        "cik": latest["filer"]["cik"],
        "ticker": undisclosed(),
        "public_private": field("Private", url, "Form D (Regulation D exempt offering)", "filing_metadata",
                                note="Form D issuers are private offerings; the issuer may still have registered securities"),
        **loc,
        "hq": field(", ".join(x for x in (p.get("city"), p.get("state")) if x), url, _q(latest, "city"), "filing_metadata"),
        "gics_sector": field(mapped[0], url, industry_quote, "derived", note="mapped from Form D industry group") if mapped else undisclosed(),
        "gics_sub_industry": field(mapped[1], url, industry_quote, "derived", note="mapped from Form D industry group") if mapped else undisclosed(),
        "focus_sector": field(gics.focus_sector(*mapped), url, industry_quote, "derived") if mapped else undisclosed(),
    }
    acquirer = unknown_party("Form D does not identify investors")
    if category == "M&A":  # issuer is the acquirer paying with its securities
        target, acquirer = unknown_party("Target not named in Form D"), {**target}
    acquirer["type"] = undisclosed()
    acquirer["is_add_on"] = field(None)
    acquirer["platform"] = undisclosed()
    acquirer["sponsor"] = undisclosed()
    remaining = p.get("total_remaining")
    status = field("Closed", url, _q(latest, "totalRemaining"), "filing_metadata", note="offering fully sold") if remaining == 0 else \
        field("Announced", url, _q(latest, "totalRemaining"), "filing_metadata", note="offering open; sales continuing")
    financials = {k: undisclosed() for k in ("enterprise_value", "equity_value", "transaction_value", "price_per_share", "revenue", "ebitda", "ev_revenue", "ev_ebitda", "consideration")}
    financials["amount_raised"] = raised
    financials["offering_size"] = size
    financials["investor_count"] = field(p.get("investor_count"), url, _q(latest, "totalNumberAlreadyInvested"), "filing_metadata")
    deal = {
        "deal_id": stable_id("MDR", base_id),
        "schema_version": SCHEMA_VERSION,
        "category": category,
        "deal_type": deal_type,
        "status": status,
        "announcement_date": field(first["filed"], first["url"], f"Form D filed {first['filed']}", "filing_metadata", note="Form D filing date"),
        "closing_date": undisclosed(),
        "first_sale_date": field(p.get("date_of_first_sale"), url, _q(latest, "value"), "filing_metadata"),
        "target": target,
        "acquirer": acquirer,
        "seller": None,
        "advisors": [],
        "financials": financials,
        "rationale": undisclosed(),
        "michigan_link": "Acquirer" if category == "M&A" else "Target",
        "focus_sector": val(target.get("focus_sector")) or val(acquirer.get("focus_sector")),
        "people": people,
        "sources": sources,
        "confidence": "High",
        "timeline": timeline,
        "flags": [],
        "legacy_ids": [base_id],
    }
    deal["title"] = (f"{issuer}: {val(deal_type).lower()} ({money(val(raised), 'n.d.')} raised)" if category == "Financing"
                     else f"{issuer} issued securities in an acquisition (target not named)")
    deal["summary"] = deal["title"] + "."
    return "deals", deal


def build_debt_deal(e: dict) -> dict:
    borrower = filer_party(e)
    lenders = [canonical_firm(a["firm"]) for a in e.get("lenders") or []]
    investor = unknown_party("Lenders not named in the filing") if not lenders else named_party(
        field(", ".join(lenders), e["doc_url"], e["lenders"][0]["source_text"]))
    for k in ("type", "is_add_on", "platform", "sponsor"):
        investor[k] = undisclosed() if k != "is_add_on" else field(None)
    if lenders:
        investor["type"] = field("Lender", e["doc_url"], e["lenders"][0]["source_text"])
    financials = {k: undisclosed() for k in ("enterprise_value", "equity_value", "transaction_value", "price_per_share", "revenue", "ebitda", "ev_revenue", "ev_ebitda", "consideration")}
    financials["amount_raised"] = e.get("facility_amount") or undisclosed()
    src = _source_from_event(e)
    deal = {
        "deal_id": stable_id("MDR", e["event_id"]),
        "schema_version": SCHEMA_VERSION,
        "category": "Financing",
        "deal_type": field("Debt Raise", e["doc_url"], e.get("excerpt"), "rule", note=e.get("agreement_kind")),
        "status": e["status"],
        "announcement_date": field(e["filed"], e["url"], f"8-K filed {e['filed']}", "filing_metadata"),
        "closing_date": undisclosed(),
        "target": borrower,
        "acquirer": investor,
        "seller": None,
        "advisors": [{**a, "firm": canonical_firm(a["firm"])} for a in e.get("lenders") or []],
        "financials": financials,
        "rationale": undisclosed(),
        "michigan_link": "Target",
        "focus_sector": val(borrower.get("focus_sector")),
        "sources": [src],
        "confidence": "High",
        "timeline": [{"date": e["filed"], "status": "Closed", "event": _event_label(e), "source_url": e["url"], "source_text": e.get("excerpt")}],
        "flags": [],
        "legacy_ids": [f"8K-{e['event_id']}"],
    }
    amt = val(financials["amount_raised"])
    deal["title"] = f"{val(borrower['name'])}: {(e.get('agreement_kind') or 'debt financing').lower()}" + (f" ({money(amt)})" if amt else "")
    deal["summary"] = deal["title"] + "."
    return deal


# ----------------------------------------------------------------------------- ownership

def build_ownership_record(e: dict) -> dict:
    p = e["parsed"]
    subj = e.get("subject") or {}
    url = e["doc_url"]
    reporters = p.get("reporting_persons") or []
    return {
        "id": stable_id("OWN", e["event_id"]),
        "company": field(display_name(p.get("issuer_name")), url, f"<issuerName>{p.get('issuer_name')}</issuerName>", "filing_metadata"),
        "cik": (p.get("issuer_cik") or subj.get("cik") or "").lstrip("0"),
        "ticker": field(pick_ticker(subj.get("tickers"), subj.get("name")), e["url"], f"EDGAR ticker(s): {', '.join(subj.get('tickers') or [])}", "filing_metadata"),
        **{k: v for k, v in _location_fields(p.get("issuer_city"), None, url, f"Issuer address: {p.get('issuer_city')}, {p.get('issuer_state')}").items() if k in ("city", "county", "region")},
        "holders": [{"name": display_name(r["name"]), "percent_of_class": r.get("percent_of_class"), "shares": r.get("shares"), "type": r.get("type")} for r in reporters],
        "percent_of_class": field(p.get("max_percent"), url, f"<percentOfClass>{p.get('max_percent')}</percentOfClass>", "filing_metadata"),
        "event_date": field(p.get("event_date"), url, f"<dateOfEvent>{p.get('event_date')}</dateOfEvent>", "filing_metadata"),
        "purpose": field(p.get("purpose_excerpt"), url, p.get("purpose_excerpt"), "filing_metadata"),
        "amendment": p.get("is_amendment"),
        "amendment_no": p.get("amendment_no"),
        "filed": e["filed"],
        "sources": [{"url": e["url"], "title": f"{display_name(p.get('issuer_name'))} {p.get('submission_type')}", "publisher": "SEC EDGAR",
                     "kind": "SEC Schedule 13D", "date": e["filed"], "confidence": "High", "accession": e["event_id"]}],
        "legacy_ids": [f"13D-{e['event_id']}"],
    }


# ----------------------------------------------------------------------------- entry point

def build_datasets(events: list[dict], news: list[dict] | None = None) -> dict[str, list[dict]]:
    """Rebuild deals, capital formation and ownership datasets from all evidence."""
    ma_events = [e for e in events if e["kind"] == "sec_ma" and e.get("category") == "M&A"]
    debt_events = [e for e in events if e["kind"] == "sec_ma" and e.get("category") == "Material Agreement"
                   and e.get("agreement_kind") in ("Credit Facility", "Debt Offering")]
    deals = [build_ma_deal(c) for c in cluster_ma_events(ma_events)]
    deals += [build_debt_deal(e) for e in debt_events]
    capital_formation: list[dict] = []
    for group in _formd_groups([e for e in events if e["kind"] == "sec_formd"]):
        dataset, rec = build_formd_record(group)
        (deals if dataset == "deals" else capital_formation).append(rec)
    ownership = [build_ownership_record(e) for e in events if e["kind"] == "sec_13d"]

    if news:
        from .news_linking import link_news  # local import keeps the SEC path independent of news code
        deals = link_news(deals, news)

    def sort_key(d: dict) -> tuple:
        return (val(d.get("announcement_date")) or d.get("filed") or "", d.get("deal_id") or d.get("id"))

    return {
        "deals": sorted(deals, key=sort_key, reverse=True),
        "capital_formation": sorted(capital_formation, key=lambda r: (r["filed"], r["id"]), reverse=True),
        "ownership": sorted(ownership, key=lambda r: (r["filed"], r["id"]), reverse=True),
    }


__all__ = ["build_datasets", "cluster_ma_events", "build_ma_deal", "build_formd_record", "NOT_DISCLOSED", "normalize_name"]
