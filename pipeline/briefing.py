"""Weekly briefing generator: pure templates + arithmetic over deals.json."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from . import config
from .deals import DEAL_TYPES, money
from .store import read_json, utc_now, write_json


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _parse(day: str | None) -> date | None:
    try:
        return date.fromisoformat(day[:10]) if day else None
    except ValueError:
        return None


def deals_in_range(deals: list[dict], start: date, end: date) -> list[dict]:
    return [d for d in deals if (f := _parse(d.get("filed"))) and start <= f <= end]


def _brief(deal: dict) -> dict:
    keys = ("id", "company", "ticker", "type", "subtype", "city", "sector", "amount", "amount_sold", "amount_is_estimate", "summary", "filed")
    return {k: deal.get(k) for k in keys}


def _pct_change(current: float, baseline: float) -> float | None:
    if not baseline:
        return None
    return round((current - baseline) / baseline * 100, 1)


def _stats(week: list[dict]) -> dict:
    raises = [d for d in week if d["type"] == "Fundraise"]
    return {
        "deal_count": len(week),
        "by_type": {t: sum(1 for d in week if d["type"] == t) for t in DEAL_TYPES},
        "capital_raised": round(sum(d.get("amount_sold") or 0 for d in raises)),
        "capital_targeted": round(sum(d.get("amount") or 0 for d in raises)),
        "fund_count": sum(1 for d in raises if (d.get("details") or {}).get("is_pooled_fund")),
    }


def _trend_word(change: float | None) -> str:
    if change is None:
        return ""
    if abs(change) < 5:
        return ", roughly in line with the prior 4-week average"
    return f", {'up' if change > 0 else 'down'} {abs(change):.0f}% vs. the prior 4-week average"


def build_talking_points(week: list[dict], stats: dict, trailing: dict, ytd: list[dict], year: int) -> list[dict]:
    """Return exactly three talking points, chosen by priority from what happened."""
    candidates: list[dict] = []
    raises = sorted(
        (d for d in week if d["type"] == "Fundraise" and not (d.get("details") or {}).get("is_pooled_fund")),
        key=lambda d: d.get("amount") or 0,
        reverse=True,
    )
    funds = sorted(
        (d for d in week if (d.get("details") or {}).get("is_pooled_fund")),
        key=lambda d: d.get("amount") or 0,
        reverse=True,
    )
    mna = [d for d in week if d["type"] == "M&A"]
    stakes = sorted((d for d in week if d["type"] == "Stake"), key=lambda d: (d.get("details") or {}).get("percent_of_class") or 0, reverse=True)

    if raises:
        lead = raises[0]
        capital_change = _pct_change(stats["capital_raised"], trailing["capital_raised"])
        candidates.append({
            "topic": "Capital formation",
            "text": (
                f"Michigan issuers reported {money(stats['capital_raised'])} sold across "
                f"{stats['by_type']['Fundraise']} Form D filings this week{_trend_word(capital_change)}. "
                f"The largest was {lead['company']} ({lead.get('city') or 'Michigan'}, {lead.get('industry') or 'private company'}) "
                f"targeting {money(lead.get('amount'))}. Good question to ask: are founders in "
                f"{(lead.get('sector') or 'this sector').lower()} favoring equity rounds over venture debt right now?"
            ),
            "deal_ids": [lead["id"]],
        })

    if mna:
        lead = max(mna, key=lambda d: (d.get("amount") or 0, d["subtype"] == "Acquisition/Disposition Completed"))
        name = f"{lead['company']} ({lead['ticker']})" if lead.get("ticker") else lead["company"]
        partner = f" with {lead['counterparty']}" if lead.get("counterparty") else ""
        action = "closed a transaction" if lead["subtype"] == "Acquisition/Disposition Completed" else "disclosed a deal"
        more = f" It was one of {len(mna)} M&A filings this week." if len(mna) > 1 else ""
        candidates.append({
            "topic": "M&A",
            "text": (
                f"{name} {action}{partner}.{more} Use it to ask how buyers are valuing Michigan "
                f"{(lead.get('sector') or 'middle-market').lower()} assets and whether consolidation is accelerating."
            ),
            "deal_ids": [d["id"] for d in mna[:3]],
        })

    if funds:
        total = sum(d.get("amount_sold") or 0 for d in funds)
        lead = funds[0]
        candidates.append({
            "topic": "Fund formation",
            "text": (
                f"{len(funds)} Michigan-based pooled fund{'s' if len(funds) > 1 else ''} filed Form Ds, reporting "
                f"{money(total)} raised so far — led by {lead['company']} ({lead.get('subtype') or 'private fund'}). "
                f"A natural opener: what are LPs asking Michigan sponsors for in today's fundraising market?"
            ),
            "deal_ids": [d["id"] for d in funds[:3]],
        })

    if stakes:
        lead = stakes[0]
        candidates.append({
            "topic": "Ownership moves",
            "text": (
                f"{lead['summary']} Schedule 13D filers can push for strategic change, so it's worth asking "
                f"whether shareholders see a sale or restructuring on the table."
            ),
            "deal_ids": [lead["id"]],
        })

    sector_counts = Counter(d.get("sector") or "Other" for d in week if d.get("sector") not in (None, "Other"))
    if sector_counts:
        sector, count = sector_counts.most_common(1)[0]
        share = round(count / len(week) * 100)
        candidates.append({
            "topic": "Sector watch",
            "text": (
                f"{sector} was the most active sector with {count} of {len(week)} filings ({share}%). "
                f"Ask contacts what's driving the activity, and whether it's showing up in their pipeline."
            ),
            "deal_ids": [d["id"] for d in week if d.get("sector") == sector][:3],
        })

    ytd_raises = [d for d in ytd if d["type"] == "Fundraise"]
    if ytd_raises:
        by_month = defaultdict(float)
        for d in ytd_raises:
            by_month[d["filed"][:7]] += d.get("amount_sold") or 0
        busiest = max(by_month, key=by_month.get)
        month_name = date.fromisoformat(busiest + "-01").strftime("%B")
        candidates.append({
            "topic": "Year to date",
            "text": (
                f"Year to date, Michigan private issuers have reported {money(sum(by_month.values()))} sold across "
                f"{len(ytd_raises)} Form D offerings in {year}, with {month_name} the busiest month so far."
            ),
            "deal_ids": [],
        })

    if len(week) < max(3, trailing["deal_count"] * 0.6):
        candidates.append({
            "topic": "Deal flow",
            "text": (
                f"A quieter week: {len(week)} Michigan filings vs. a trailing average of {trailing['deal_count']:.0f}. "
                f"Ask whether that's seasonal or whether pipelines are building for next quarter."
            ),
            "deal_ids": [],
        })

    return candidates[:3]


def build_briefing(deals: list[dict], start: date) -> dict:
    end = start + timedelta(days=6)
    week = deals_in_range(deals, start, end)
    stats = _stats(week)

    prior = [_stats(deals_in_range(deals, start - timedelta(weeks=i), start - timedelta(weeks=i) + timedelta(days=6))) for i in range(1, 5)]
    trailing = {
        "deal_count": sum(p["deal_count"] for p in prior) / 4,
        "capital_raised": sum(p["capital_raised"] for p in prior) / 4,
    }
    ytd = deals_in_range(deals, date(end.year, 1, 1), end)

    ranked = sorted((d for d in week if d.get("amount")), key=lambda d: d["amount"], reverse=True)
    funds = [d for d in week if (d.get("details") or {}).get("is_pooled_fund")]
    mna = [d for d in week if d["type"] in ("M&A", "Stake")]
    agreements = [d for d in week if d["type"] == "Material Agreement"]

    sectors = defaultdict(lambda: {"count": 0, "amount": 0.0})
    for d in week:
        sectors[d.get("sector") or "Other"]["count"] += 1
        sectors[d.get("sector") or "Other"]["amount"] += d.get("amount_sold") or 0
    top_sectors = sorted(({"sector": k, **v} for k, v in sectors.items()), key=lambda s: (-s["count"], -s["amount"]))[:5]

    if ranked:
        headline = f"{stats['deal_count']} Michigan deals, {money(stats['capital_raised'])} raised — led by {ranked[0]['company']}"
    elif week:
        headline = f"{stats['deal_count']} Michigan filings this week"
    else:
        headline = "No Michigan deal filings this week"

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "generated_at": utc_now(),
        "headline": headline,
        "stats": stats,
        "trailing_4wk": {k: round(v, 1) for k, v in trailing.items()},
        "change_vs_trailing": {
            "deal_count_pct": _pct_change(stats["deal_count"], trailing["deal_count"]),
            "capital_raised_pct": _pct_change(stats["capital_raised"], trailing["capital_raised"]),
        },
        "top_deals": [_brief(d) for d in ranked[:5]],
        "new_funds": [_brief(d) for d in sorted(funds, key=lambda d: d.get("amount") or 0, reverse=True)[:6]],
        "notable_ma": [_brief(d) for d in mna[:8]],
        "material_agreements": [_brief(d) for d in agreements[:6]],
        "top_sectors": top_sectors,
        "talking_points": build_talking_points(week, stats, trailing, ytd, end.year),
    }


def generate_briefings(deals: list[dict], today: date, out_dir: Path | None = None, force: bool = False, coverage_start: date | None = None) -> list[str]:
    """Write a briefing for every completed Mon-Sun week that doesn't have one yet.

    Runs daily, so on Mondays it naturally produces the briefing for the week
    that just ended. Returns the week_start strings that were (re)written.
    """
    out_dir = out_dir or config.BRIEFINGS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    filed_dates = [f for d in deals if (f := _parse(d.get("filed")))]
    if not filed_dates:
        return []
    first = coverage_start or min(filed_dates)
    start = week_start(first)
    if start < first:  # skip a partial first week
        start += timedelta(weeks=1)
    last_completed = week_start(today) - timedelta(weeks=1)

    written = []
    cursor = start
    while cursor <= last_completed:
        path = out_dir / f"{cursor.isoformat()}.json"
        if force or not path.exists():
            write_json(path, build_briefing(deals, cursor))
            written.append(cursor.isoformat())
        cursor += timedelta(weeks=1)
    write_index(out_dir)
    return written


def write_index(out_dir: Path) -> None:
    entries = []
    for path in sorted(out_dir.glob("????-??-??.json"), reverse=True):
        b = read_json(path, {})
        entries.append({
            "week_start": b.get("week_start"),
            "week_end": b.get("week_end"),
            "headline": b.get("headline"),
            "deal_count": b.get("stats", {}).get("deal_count", 0),
            "capital_raised": b.get("stats", {}).get("capital_raised", 0),
        })
    write_json(out_dir / "index.json", {"generated_at": utc_now(), "weeks": entries})
