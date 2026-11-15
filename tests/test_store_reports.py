"""Storage, v1 migration, analytics, briefing, quality report and Excel export."""

from datetime import date

from openpyxl import load_workbook

from pipeline.analytics.metrics import league_tables, precedent_transactions, snapshot
from pipeline.analytics.quality import quality_report
from pipeline.models import field, val
from pipeline.reporting.briefing import build_briefing, generate_briefings, week_start
from pipeline.reporting.excel import build_workbook
from pipeline.storage.linking import build_datasets
from pipeline.storage.migrate_v1 import migrate
from pipeline.storage.store import merge_evidence

from .test_linking import ma_event


def deals_fixture():
    events = [
        ma_event("a1", "2026-06-15", role="acquirer", cp="Grand River Commerce, Inc.", agreement="2026-06-11"),
        ma_event("a3", "2026-11-02", role="acquirer", cp="Grand River Commerce, Inc.", agreement="2026-06-11", status="Closed", items=("2.01",)),
        ma_event("b1", "2026-11-03", name="ROCKWELL MEDICAL INC", cik="1041024", role="acquirer", cp="Vantive Limited", agreement="2026-11-02"),
    ]
    events[2]["financials"] = {"enterprise_value": field(500e6, "u", "enterprise value of $500 million"), "ebitda": field(50e6, "u", "EBITDA of $50 million")}
    events[2]["advisors"] = [{"firm": "Houlihan Lokey", "role": "financial", "client": None, "people": [], "source_url": "u", "source_text": "q", "method": "rule"}]
    return build_datasets(events)["deals"]


def test_merge_evidence_keeps_verified_llm_fills():
    old = [{"event_id": "x", "filed": "2026-01-01", "llm": {"role": field("target", "u", "q", "llm_verified")}}]
    new = [{"event_id": "x", "filed": "2026-01-01"}]
    assert merge_evidence(old, new)[0]["llm"]["role"]["value"] == "target"


def test_derived_multiple_and_precedents():
    deals = deals_fixture()
    rock = next(d for d in deals if "Rockwell" in d["title"])
    assert rock["financials"]["ev_ebitda"]["value"] == 10.0
    assert rock["financials"]["ev_ebitda"]["method"] == "derived"
    prec = precedent_transactions(deals)
    assert prec["ev_ebitda"]["median"] == 10.0 and prec["ev_ebitda"]["n"] == 1


def test_league_tables_count_acquirers_and_advisors():
    lt = league_tables(deals_fixture())
    assert {r["name"] for r in lt["acquirers"]} == {"Isabella Bank Corp", "Rockwell Medical Inc"}
    assert lt["financial_advisors"][0]["name"] == "Houlihan Lokey"


def test_briefing_and_generation(tmp_path):
    deals = deals_fixture()
    b = build_briefing(deals, [], [], date(2026, 11, 2))
    assert b["stats"]["ma_deals"] == 1  # Rockwell announced Nov 2 (Isabella announced in June)
    assert len(b["talking_points"]) == 3
    assert b["sources"] and all(s["url"] for s in b["sources"])
    written = generate_briefings(deals, [], [], date(2026, 11, 16), date(2026, 10, 20), out_dir=tmp_path)
    assert written == ["2026-10-26", "2026-11-02", "2026-11-09"]
    assert week_start(date(2026, 11, 15)) == date(2026, 11, 9)


def test_quality_report_flags_and_migration_coverage():
    deals = deals_fixture() + build_datasets([ma_event("u1", "2026-02-02", items=("2.01",), status="Closed")])["deals"]
    q = quality_report(deals, set(), 4, [], {}, [{"a1"}, {"zzz"}], {"a1", "a3", "b1", "u1"})
    assert q["duplicates_merged"] == 1
    assert q["flagged_for_review_count"] == 1
    assert q["v1_migration"] == {"v1_records": 2, "covered_in_v2_evidence": 1, "not_covered": [["zzz"]]}


def test_v1_migration_converts_form_d_and_8k():
    v1 = [
        {"id": "D-1-021", "form": "D", "type": "Fundraise", "subtype": "Private Placement", "accession": "acc1", "company": "Krabby Co Inc.",
         "cik": "2163797", "city": "Berkley", "state": "MI", "industry": "Other Technology", "filed": "2026-11-06", "event_date": "2026-10-26",
         "amount": 1500000.0, "amount_sold": 166500.0, "details": {"total_offering_amount": 1500000.0, "year_of_inc": "2026", "securities": ["Equity"]},
         "url": "https://x", "doc_url": "https://x/primary_doc.xml", "related_persons": []},
        {"id": "8K-acc2", "form": "EX-99.1", "type": "M&A", "accession": "acc2", "company": "Steelcase Inc", "cik": "1050825", "ticker": "SCS",
         "city": "Grand Rapids", "filed": "2025-11-25", "items": ["8.01"], "details": {"sic": "2522"},
         "excerpt": 'Steelcase Inc. entered into an Agreement and Plan of Merger (the "Merger Agreement") with HNI Corporation, an Iowa corporation.',
         "url": "https://y", "doc_url": "https://y/doc.htm"},
    ]
    events = migrate(v1, existing_ids=set())
    assert {e["kind"] for e in events} == {"sec_formd", "sec_ma"}
    assert all(e["migrated_from_v1"] for e in events)
    out = build_datasets(events)
    assert val(out["deals"][0]["deal_type"]) in ("Venture Round", "Acquisition")
    assert migrate(v1, existing_ids={"acc1", "acc2"}) == []


def test_excel_banking_format(tmp_path):
    deals = deals_fixture()
    analytics = snapshot(deals, [], [], date(2026, 11, 15))
    path = build_workbook(deals, [], analytics, tmp_path / "out.xlsx", "2026-11-06")
    wb = load_workbook(path)
    assert wb.sheetnames[:3] == ["Cover", "M&A", "Precedents"]
    ws = wb["M&A"]
    assert ws.freeze_panes == "B5"
    header = [c.value for c in ws[4]]
    ev_col = header.index("EV ($M)") + 1
    row = next(r for r in ws.iter_rows(min_row=5) if r[2].value == "Vantive Limited")
    assert row[ev_col - 1].value == 500.0 and row[ev_col - 1].number_format.startswith("$#,##0.0")
    mult = row[header.index("EV / EBITDA")]
    assert mult.value == 10.0 and mult.number_format == '0.0"x"'
    assert row[-1].hyperlink is not None
    assert any(c.value == "Not disclosed" for c in row)
