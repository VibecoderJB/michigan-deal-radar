from datetime import date

from pipeline.briefing import build_briefing, generate_briefings, week_start
from pipeline.store import known_accessions, merge_deals


def deal(id_, filed, type_="Fundraise", amount=1e6, sold=5e5, accession=None, **extra):
    d = {"id": id_, "type": type_, "subtype": "Private Placement", "company": f"Co {id_}", "ticker": None,
         "city": "Detroit", "sector": "Technology", "industry": "Other Technology", "filed": filed,
         "amount": amount, "amount_sold": sold, "summary": f"Co {id_} did a deal.", "details": {},
         "accession": accession or f"acc-{id_}-{filed}", "counterparty": None}
    d.update(extra)
    return d


def test_merge_keeps_latest_amendment_and_history():
    original = deal("D-1-021", "2026-01-05", sold=1e6, accession="a1", filings=[{"accession": "a1", "filed": "2026-01-05", "form": "D", "amount_sold": 1e6}])
    amended = deal("D-1-021", "2026-06-01", sold=3e6, accession="a2", filings=[{"accession": "a2", "filed": "2026-06-01", "form": "D/A", "amount_sold": 3e6}])
    merged = merge_deals([original], [amended])
    assert len(merged) == 1
    assert merged[0]["amount_sold"] == 3e6
    assert merged[0]["first_filed"] == "2026-01-05"
    assert [f["accession"] for f in merged[0]["filings"]] == ["a1", "a2"]
    assert known_accessions(merged) == {"a1", "a2"}


def test_merge_ignores_older_duplicate():
    newer = deal("X", "2026-06-01", sold=3e6, accession="a2")
    older = deal("X", "2026-01-01", sold=1e6, accession="a1")
    assert merge_deals([newer], [older])[0]["amount_sold"] == 3e6


def test_week_start_is_monday():
    assert week_start(date(2026, 11, 8)) == date(2026, 11, 2)
    assert week_start(date(2026, 11, 2)) == date(2026, 11, 2)


def test_briefing_contents():
    deals = [
        deal("a", "2026-11-02", amount=10e6, sold=4e6),
        deal("b", "2026-11-03", amount=2e6, sold=2e6, details={"is_pooled_fund": True}, subtype="Venture Capital Fund"),
        deal("c", "2026-11-04", type_="M&A", amount=None, sold=None, subtype="Acquisition/Disposition Completed", ticker="ISBA", counterparty="Grand River Commerce, Inc."),
        deal("old", "2026-10-20", amount=1e6, sold=1e6),
    ]
    b = build_briefing(deals, date(2026, 11, 2))
    assert b["week_end"] == "2026-11-08"
    assert b["stats"]["deal_count"] == 3
    assert b["stats"]["capital_raised"] == 6_000_000
    assert b["stats"]["fund_count"] == 1
    assert b["top_deals"][0]["id"] == "a"
    assert [d["id"] for d in b["new_funds"]] == ["b"]
    assert [d["id"] for d in b["notable_ma"]] == ["c"]
    assert len(b["talking_points"]) == 3
    topics = [t["topic"] for t in b["talking_points"]]
    assert topics[:2] == ["Capital formation", "M&A"]
    assert "Grand River Commerce" in b["talking_points"][1]["text"]


def test_empty_week_still_produces_briefing():
    b = build_briefing([deal("x", "2026-01-05")], date(2026, 11, 2))
    assert b["stats"]["deal_count"] == 0
    assert b["headline"] == "No Michigan deal filings this week"


def test_generate_briefings_only_completed_weeks(tmp_path):
    deals = [deal("a", "2026-10-13"), deal("b", "2026-10-28"), deal("c", "2026-11-06")]
    written = generate_briefings(deals, today=date(2026, 11, 8), out_dir=tmp_path)
    assert written == ["2026-10-19", "2026-10-26"]  # partial first week skipped, current week not done
    assert generate_briefings(deals, today=date(2026, 11, 9), out_dir=tmp_path) == ["2026-11-02"]  # Monday run
    assert (tmp_path / "index.json").exists()
