"""Deal analytics shared by the dashboard snapshot, weekly/quarterly reports and the README.

Conventions:
* "Disclosed value" sums only values a source states (EV, else transaction value, else
  equity value). Undisclosed deals count toward deal counts, never toward value.
* Periods use the announcement date (falling back to the first filing date).
* Medians/means of multiples use only deals with a disclosed or arithmetically derived multiple.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date

from ..extraction.entities import canonical_firm, firm_category
from ..models import MA_TYPES, val
from ..reference.gics import FOCUS_SECTORS


def deal_date(d: dict) -> str:
    return (val(d.get("announcement_date")) or "")[:10]


def quarter(iso: str) -> str:
    y, m = int(iso[:4]), int(iso[5:7])
    return f"{y}-Q{(m - 1) // 3 + 1}"


def disclosed_value(d: dict) -> float | None:
    f = d.get("financials") or {}
    return val(f.get("enterprise_value")) or val(f.get("transaction_value")) or val(f.get("equity_value"))


def amount_raised(d: dict) -> float | None:
    return val((d.get("financials") or {}).get("amount_raised"))


def is_ma(d: dict) -> bool:
    return d.get("category") == "M&A" and val(d.get("deal_type")) in MA_TYPES | {"Acquisition", "Merger"}


def in_window(d: dict, start: str, end: str) -> bool:
    dt = deal_date(d)
    return bool(dt) and start <= dt <= end


def period_series(deals: list[dict], period: str = "quarter") -> list[dict]:
    """Count and disclosed value per month/quarter/year, split M&A vs financings."""
    key = {"month": lambda s: s[:7], "quarter": quarter, "year": lambda s: s[:4]}[period]
    rows: dict[str, dict] = defaultdict(lambda: {"ma_count": 0, "ma_value": 0.0, "ma_disclosed": 0, "fin_count": 0, "fin_raised": 0.0})
    for d in deals:
        dt = deal_date(d)
        if not dt:
            continue
        r = rows[key(dt)]
        if is_ma(d):
            r["ma_count"] += 1
            v = disclosed_value(d)
            if v:
                r["ma_value"] += v
                r["ma_disclosed"] += 1
        elif d.get("category") == "Financing":
            r["fin_count"] += 1
            r["fin_raised"] += amount_raised(d) or 0
    return [{"period": k, **v} for k, v in sorted(rows.items())]


def _party_name(d: dict, role: str) -> str | None:
    p = d.get(role) or {}
    return val(p.get("name")) if p else None


def league_tables(deals: list[dict], top: int = 10) -> dict[str, list[dict]]:
    acquirers: Counter = Counter()
    acquirer_value: dict[str, float] = defaultdict(float)
    sponsors: Counter = Counter()
    advisors: dict[str, Counter] = {"financial": Counter(), "legal": Counter(), "lender": Counter()}
    recent: dict[str, list[str]] = defaultdict(list)
    for d in deals:
        if not is_ma(d):
            continue
        a = _party_name(d, "acquirer")
        # Form D "business combination" notices name the issuer but not the target, and one
        # offering can fund several acquisitions; they count in deal flow, not in league tables.
        if a and not any(s.get("kind") == "SEC Form D" for s in d.get("sources") or []):
            acquirers[a] += 1
            acquirer_value[a] += disclosed_value(d) or 0
            recent[a].append(d["deal_id"])
        sp = val((d.get("acquirer") or {}).get("sponsor"))
        if sp:
            sponsors[canonical_firm(sp)] += 1
        elif val((d.get("acquirer") or {}).get("type")) == "Financial Sponsor" and a:
            sponsors[canonical_firm(a)] += 1
        for adv in d.get("advisors") or []:
            advisors.setdefault(adv["role"], Counter())[canonical_firm(adv["firm"])] += 1
            recent[canonical_firm(adv["firm"])].append(d["deal_id"])

    def table(counter: Counter, value: dict | None = None) -> list[dict]:
        return [{"name": n, "deals": c, **({"disclosed_value": value[n]} if value else {}), "recent_deal_ids": recent.get(n, [])[:5]}
                for n, c in counter.most_common(top)]

    return {
        "acquirers": table(acquirers, acquirer_value),
        "sponsors": table(sponsors),
        "financial_advisors": table(advisors["financial"]),
        "legal_advisors": table(advisors["legal"]),
        "lenders": table(advisors["lender"]),
    }


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "median": None, "mean": None, "low": None, "high": None}
    return {"n": len(values), "median": round(statistics.median(values), 2), "mean": round(statistics.fmean(values), 2),
            "low": round(min(values), 2), "high": round(max(values), 2)}


def precedent_transactions(deals: list[dict]) -> dict:
    """M&A deals with a disclosed value or multiple; summary statistics for multiples."""
    rows = []
    for d in deals:
        if not is_ma(d):
            continue
        f = d.get("financials") or {}
        if not (disclosed_value(d) or val(f.get("ev_ebitda")) or val(f.get("ev_revenue"))):
            continue
        rows.append(d)
    rows.sort(key=deal_date, reverse=True)
    return {
        "deal_ids": [d["deal_id"] for d in rows],
        "ev_ebitda": _stats([val(d["financials"]["ev_ebitda"]) for d in rows if val(d["financials"].get("ev_ebitda"))]),
        "ev_revenue": _stats([val(d["financials"]["ev_revenue"]) for d in rows if val(d["financials"].get("ev_revenue"))]),
        "value": _stats([disclosed_value(d) for d in rows if disclosed_value(d)]),
    }


def sector_trends(deals: list[dict], as_of: date) -> list[dict]:
    """Deal counts by focus sector: latest full quarter vs prior quarter and same quarter last year."""
    q_end_month = ((as_of.month - 1) // 3) * 3  # last month of previous quarter
    y, m = (as_of.year, q_end_month) if q_end_month else (as_of.year - 1, 12)
    latest_q = f"{y}-Q{(m - 1) // 3 + 1}"
    prev_q = f"{y}-Q{(m - 1) // 3}" if m > 3 else f"{y - 1}-Q4"
    yoy_q = f"{y - 1}-Q{(m - 1) // 3 + 1}"
    counts: dict[str, Counter] = defaultdict(Counter)
    for d in deals:
        if d.get("category") not in ("M&A", "Financing") or not deal_date(d):
            continue
        counts[d.get("focus_sector") or "Other"][quarter(deal_date(d))] += 1
    out = []
    for sector in (*FOCUS_SECTORS, "Other"):
        c = counts.get(sector, Counter())
        cur, prev, yoy = c[latest_q], c[prev_q], c[yoy_q]
        out.append({
            "sector": sector, "quarter": latest_q, "deals": cur, "prior_quarter": prev, "year_ago_quarter": yoy,
            "qoq_pct": round((cur - prev) / prev * 100, 1) if prev else None,
            "yoy_pct": round((cur - yoy) / yoy * 100, 1) if yoy else None,
            "trailing_4q": sum(c[q] for q in _last_quarters(latest_q, 4)),
        })
    return out


def _last_quarters(q: str, n: int) -> list[str]:
    y, k = int(q[:4]), int(q[-1])
    out = []
    for _ in range(n):
        out.append(f"{y}-Q{k}")
        k -= 1
        if k == 0:
            y, k = y - 1, 4
    return out


def sponsor_activity(deals: list[dict]) -> dict:
    platform = add_on = 0
    by_quarter: dict[str, Counter] = defaultdict(Counter)
    for d in deals:
        t = val(d.get("deal_type"))
        if t not in ("PE Buyout", "Add-on"):
            continue
        q = quarter(deal_date(d)) if deal_date(d) else "n.d."
        if t == "Add-on":
            add_on += 1
            by_quarter[q]["add_on"] += 1
        else:
            platform += 1
            by_quarter[q]["platform"] += 1
    return {"platform": platform, "add_on": add_on, "by_quarter": {k: dict(v) for k, v in sorted(by_quarter.items())}}


def county_counts(deals: list[dict]) -> dict[str, int]:
    out: Counter = Counter()
    for d in deals:
        for role in ("target", "acquirer", "michigan_party"):
            p = d.get(role) or {}
            county = val(p.get("county")) if p else None
            if county:
                out[county] += 1
                break
    return dict(out.most_common())


def whos_active(deals: list[dict], top: int = 25) -> list[dict]:
    """Banks, PE firms and law firms appearing most often on Michigan deals, with public deal-team names."""
    firms: dict[str, dict] = {}
    for d in sorted(deals, key=deal_date, reverse=True):
        involved: list[tuple[str, str, list[str]]] = []
        for adv in d.get("advisors") or []:
            involved.append((canonical_firm(adv["firm"]), {"financial": "Investment bank", "legal": "Law firm", "lender": "Lender"}[adv["role"]], adv.get("people") or []))
        acq = d.get("acquirer") or {}
        if val(acq.get("type")) == "Financial Sponsor" and val(acq.get("name")):
            involved.append((canonical_firm(val(acq.get("sponsor")) or val(acq["name"])), "Private equity", []))
        for name, kind, people in involved:
            cat = firm_category(name)
            if cat:
                kind = {"investment_banks": "Investment bank", "law_firms": "Law firm", "private_equity": "Private equity",
                        "venture_capital": "Venture capital", "family_offices": "Family office"}.get(cat[0], kind)
            f = firms.setdefault(name, {"name": name, "kind": kind, "deals": 0, "recent_deal_ids": [], "people": set(), "michigan_based": bool(cat and "MI" in (cat[1].get("hq") or ""))})
            f["deals"] += 1
            if len(f["recent_deal_ids"]) < 5:
                f["recent_deal_ids"].append(d["deal_id"])
            f["people"].update(people)
    ranked = sorted(firms.values(), key=lambda f: (-f["deals"], f["name"]))[:top]
    for f in ranked:
        f["people"] = sorted(f["people"])
    return ranked


def headline_stats(deals: list[dict], capital_formation: list[dict], ownership: list[dict], start: str, end: str) -> dict:
    ma = [d for d in deals if is_ma(d) and in_window(d, start, end)]
    fin = [d for d in deals if d.get("category") == "Financing" and in_window(d, start, end)]
    cf = [c for c in capital_formation if start <= c["filed"] <= end]
    values = [disclosed_value(d) for d in ma if disclosed_value(d)]
    return {
        "window": [start, end],
        "ma_deals": len(ma),
        "ma_closed": sum(1 for d in ma if val(d["status"]) == "Closed"),
        "ma_with_disclosed_value": len(values),
        "ma_disclosed_value": round(sum(values)),
        "financings": len(fin),
        "financing_raised": round(sum(amount_raised(d) or 0 for d in fin)),
        "venture_rounds": sum(1 for d in fin if val(d["deal_type"]) == "Venture Round"),
        "fund_raises": len(cf),
        "fund_capital_raised": round(sum(val(c.get("amount_raised")) or 0 for c in cf)),
        "stakes_13d": sum(1 for o in ownership if start <= o["filed"] <= end),
        "high_confidence_share": round(sum(1 for d in ma + fin if d.get("confidence") == "High") / max(1, len(ma + fin)) * 100, 1),
    }


def snapshot(deals: list[dict], capital_formation: list[dict], ownership: list[dict], as_of: date) -> dict:
    """Precomputed analytics for the app's default views, reports and the README."""
    end = as_of.isoformat()
    start_12 = date(as_of.year - 1, as_of.month, min(as_of.day, 28)).isoformat()
    start_24 = date(as_of.year - 2, as_of.month, min(as_of.day, 28)).isoformat()
    return {
        "as_of": end,
        "last_12_months": headline_stats(deals, capital_formation, ownership, start_12, end),
        "last_24_months": headline_stats(deals, capital_formation, ownership, start_24, end),
        "by_month": period_series(deals, "month"),
        "by_quarter": period_series(deals, "quarter"),
        "by_year": period_series(deals, "year"),
        "league_tables": league_tables([d for d in deals if in_window(d, start_24, end)]),
        "precedents": precedent_transactions(deals),
        "sector_trends": sector_trends(deals, as_of),
        "sponsor_activity": sponsor_activity(deals),
        "counties": county_counts(deals),
        "whos_active": whos_active(deals),
    }
