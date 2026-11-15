"""Weekly "Michigan Deal Flow" briefing data (JSON). Pure templates + arithmetic, no AI.

The same JSON drives the in-app Briefing tab and the weekly PDF.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from .. import config
from ..analytics.metrics import amount_raised, deal_date, disclosed_value, is_ma, league_tables
from ..models import val
from ..storage.store import read_json, utc_now, write_json
from ..textutil import money


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _in(d: dict, start: date, end: date) -> bool:
    dt = deal_date(d)
    return bool(dt) and start.isoformat() <= dt <= end.isoformat()


def _brief(d: dict) -> dict:
    return {
        "deal_id": d["deal_id"],
        "title": d.get("title"),
        "summary": d.get("summary"),
        "deal_type": val(d.get("deal_type")),
        "status": val(d.get("status")),
        "target": val(d["target"]["name"]),
        "acquirer": val(d["acquirer"]["name"]),
        "value": disclosed_value(d) if is_ma(d) else amount_raised(d),
        "value_label": "Disclosed value" if is_ma(d) else "Amount raised",
        "sector": d.get("focus_sector"),
        "region": val(d["target"].get("region")) or val(d["acquirer"].get("region")),
        "confidence": d.get("confidence"),
    }


def _pct(cur: float, base: float) -> float | None:
    return round((cur - base) / base * 100, 1) if base else None


def _week_stats(deals: list[dict], cf: list[dict], own: list[dict], start: date, end: date) -> dict:
    week = [d for d in deals if _in(d, start, end)]
    ma = [d for d in week if is_ma(d)]
    fin = [d for d in week if d.get("category") == "Financing"]
    funds = [c for c in cf if start.isoformat() <= c["filed"] <= end.isoformat()]
    return {
        "ma_deals": len(ma),
        "ma_disclosed_value": round(sum(disclosed_value(d) or 0 for d in ma)),
        "ma_with_value": sum(1 for d in ma if disclosed_value(d)),
        "financings": len(fin),
        "financing_raised": round(sum(amount_raised(d) or 0 for d in fin)),
        "fund_raises": len(funds),
        "fund_capital_raised": round(sum(val(c.get("amount_raised")) or 0 for c in funds)),
        "stakes": sum(1 for o in own if start.isoformat() <= o["filed"] <= end.isoformat()),
    }


def _trend(change: float | None) -> str:
    if change is None:
        return ""
    if abs(change) < 5:
        return " (in line with the trailing 4-week average)"
    return f" ({'up' if change > 0 else 'down'} {abs(change):.0f}% vs. the trailing 4-week average)"


def talking_points(ma: list[dict], fin: list[dict], funds: list[dict], stats: dict, trailing: dict, sector_counts: Counter) -> list[dict]:
    """Exactly three networking talking points, chosen by priority from what happened."""
    out: list[dict] = []
    if ma:
        lead = max(ma, key=lambda d: (disclosed_value(d) or 0, val(d["status"]) == "Closed"))
        value = disclosed_value(lead)
        out.append({
            "topic": "M&A",
            "text": (f"{lead['title']}{' for ' + money(value) if value else ''}. "
                     f"{'It was one of ' + str(len(ma)) + ' Michigan M&A deals this week. ' if len(ma) > 1 else ''}"
                     f"Ask how buyers are underwriting Michigan {(lead.get('focus_sector') or 'middle-market').lower()} assets right now."),
            "deal_ids": [d["deal_id"] for d in ma[:3]],
        })
    if fin:
        lead = max(fin, key=lambda d: amount_raised(d) or 0)
        out.append({
            "topic": "Private capital",
            "text": (f"Michigan companies reported {money(stats['financing_raised'])} raised across {stats['financings']} financings"
                     f"{_trend(_pct(stats['financing_raised'], trailing['financing_raised']))}. The largest: {lead['title']}. "
                     f"Good question: are founders favoring equity or debt in today's market?"),
            "deal_ids": [lead["deal_id"]],
        })
    if funds:
        lead = max(funds, key=lambda c: val(c.get("amount_raised")) or 0)
        out.append({
            "topic": "Fund formation",
            "text": (f"{len(funds)} Michigan-based fund vehicle{'s' if len(funds) > 1 else ''} reported {money(stats['fund_capital_raised'])} raised, "
                     f"led by {val(lead['name'])} ({val(lead['category'])}). Ask what LPs want from Michigan sponsors this year."),
            "deal_ids": [],
        })
    if sector_counts:
        sector, n = sector_counts.most_common(1)[0]
        out.append({
            "topic": "Sector watch",
            "text": f"{sector} was the most active Michigan sector this week with {n} deal{'s' if n > 1 else ''}. Ask contacts whether that is showing up in their pipelines.",
            "deal_ids": [],
        })
    out.append({
        "topic": "Deal flow",
        "text": (f"{stats['ma_deals'] + stats['financings']} Michigan deals this week vs. a trailing average of "
                 f"{trailing['ma_deals'] + trailing['financings']:.0f}. Ask whether pipelines are building or deal timelines are stretching."),
        "deal_ids": [],
    })
    return out[:3]


def build_briefing(deals: list[dict], cf: list[dict], own: list[dict], start: date) -> dict:
    end = start + timedelta(days=6)
    week = sorted((d for d in deals if _in(d, start, end)), key=lambda d: deal_date(d), reverse=True)
    ma = [d for d in week if is_ma(d)]
    fin = [d for d in week if d.get("category") == "Financing"]
    funds = [c for c in cf if start.isoformat() <= c["filed"] <= end.isoformat()]
    stats = _week_stats(deals, cf, own, start, end)
    prior = [_week_stats(deals, cf, own, start - timedelta(weeks=i), start - timedelta(weeks=i) + timedelta(days=6)) for i in range(1, 5)]
    trailing = {k: sum(p[k] for p in prior) / 4 for k in stats}
    sector_counts = Counter(d.get("focus_sector") for d in week if d.get("focus_sector"))

    year_ago = date(end.year - 1, end.month, min(end.day, 28)).isoformat()
    lt = league_tables([d for d in deals if year_ago <= deal_date(d) <= end.isoformat()], top=5)

    commentary = []
    for sector, n in sector_counts.most_common():
        names = [d["title"] for d in week if d.get("focus_sector") == sector][:2]
        commentary.append({"sector": sector, "deals": n, "text": f"{n} deal{'s' if n > 1 else ''}: " + "; ".join(names) + "."})

    notable_ma = sorted(ma, key=lambda d: (disclosed_value(d) or 0, val(d["status"]) == "Closed"), reverse=True)[:6]
    top_fin = sorted(fin, key=lambda d: amount_raised(d) or 0, reverse=True)[:5]
    top_funds = sorted(funds, key=lambda c: val(c.get("amount_raised")) or 0, reverse=True)[:5]
    sources = []
    seen = set()
    for d in notable_ma + top_fin:
        for s in d.get("sources") or []:
            if s["url"] not in seen:
                seen.add(s["url"])
                sources.append({"title": s.get("title"), "url": s["url"], "kind": s.get("kind"), "date": s.get("date"), "deal_id": d["deal_id"]})

    total = stats["ma_deals"] + stats["financings"]
    if notable_ma:
        headline = f"{stats['ma_deals']} Michigan M&A deal{'s' if stats['ma_deals'] != 1 else ''}, {stats['financings']} financings; {notable_ma[0]['title']}"
    elif total:
        headline = f"{total} Michigan deals; {money(stats['financing_raised'])} raised in private financings"
    else:
        headline = "A quiet week for Michigan deal filings"

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "generated_at": utc_now(),
        "headline": headline,
        "stats": stats,
        "trailing_4wk": {k: round(v, 1) for k, v in trailing.items()},
        "change_vs_trailing": {k: _pct(stats[k], trailing[k]) for k in ("ma_deals", "financings", "financing_raised")},
        "notable_ma": [_brief(d) for d in notable_ma],
        "top_financings": [_brief(d) for d in top_fin],
        "fund_raises": [{"id": c["id"], "name": val(c["name"]), "category": val(c["category"]), "amount_raised": val(c["amount_raised"]),
                         "city": val(c.get("city"))} for c in top_funds],
        "league_snapshot": {"window": [year_ago, end.isoformat()], **{k: lt[k] for k in ("acquirers", "sponsors", "financial_advisors", "legal_advisors")}},
        "sector_commentary": commentary,
        "talking_points": talking_points(notable_ma, top_fin, top_funds, stats, trailing, sector_counts),
        "sources": sources,
    }


def generate_briefings(deals: list[dict], cf: list[dict], own: list[dict], today: date, coverage_start: date,
                       out_dir: Path | None = None, force: bool = False) -> list[str]:
    """Write a briefing for every completed Mon-Sun week that doesn't have one yet.

    The pipeline runs daily, so Monday's run publishes the week that just ended.
    """
    out_dir = out_dir or config.BRIEFINGS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    start = week_start(coverage_start)
    if start < coverage_start:
        start += timedelta(weeks=1)
    last = week_start(today) - timedelta(weeks=1)
    written = []
    cursor = start
    while cursor <= last:
        path = out_dir / f"{cursor.isoformat()}.json"
        existing = read_json(path, {}) or {}
        if force or not path.exists() or existing.get("schema_version") != 2:
            write_json(path, {"schema_version": 2, **build_briefing(deals, cf, own, cursor)})
            written.append(cursor.isoformat())
        cursor += timedelta(weeks=1)
    write_index(out_dir)
    return written


def write_index(out_dir: Path) -> None:
    weeks = []
    for path in sorted(out_dir.glob("????-??-??.json"), reverse=True):
        b = read_json(path, {}) or {}
        if b.get("schema_version") != 2:
            continue
        s = b.get("stats", {})
        weeks.append({"week_start": b["week_start"], "week_end": b["week_end"], "headline": b["headline"],
                      "ma_deals": s.get("ma_deals", 0), "financings": s.get("financings", 0), "financing_raised": s.get("financing_raised", 0)})
    write_json(out_dir / "index.json", {"generated_at": utc_now(), "weeks": weeks})
