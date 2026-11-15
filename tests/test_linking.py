"""Deduplication / linking: many filings about one transaction become one deal."""

from pipeline.extraction.formd import parse_form_d
from pipeline.ingestion.edgar import FilingHit
from pipeline.models import field, val
from pipeline.sources.sec import analyze_ma_filing, formd_event
from pipeline.storage.linking import build_datasets, cluster_ma_events


def ma_event(acc, filed, *, cik="842517", name="ISABELLA BANK CORP", role=None, cp=None, agreement=None, status="Announced", items=("1.01",), form="8-K"):
    return {
        "event_id": acc, "kind": "sec_ma", "category": "M&A", "form": form, "items": list(items), "filed": filed,
        "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}-index.htm", "doc_url": f"https://x/{acc}.htm",
        "filer": {"name": name, "cik": cik, "tickers": ["ISBA"], "city": "Mt. Pleasant", "state": "MI", "sic": "6022", "inc_state": "MI"},
        "entities": [], "status": field(status, "u", f"{status} evidence"), "role": field(role, "u", "role evidence") if role else field(None),
        "counterparty": field(cp, "u", f"merger with {cp}") if cp else field(None),
        "agreement_date": field(agreement, "u", f"dated as of {agreement}") if agreement else field(None),
        "closing_date": field(None), "financials": {}, "advisors": [], "rationale": field(None), "sponsor_context": {},
        "excerpt": "excerpt",
    }


def test_announce_pending_close_become_one_deal():
    events = [
        ma_event("a1", "2026-06-15", role="acquirer", cp="Grand River Commerce, Inc.", agreement="2026-06-11"),
        ma_event("a2", "2026-09-21", cp="Grand River Commerce, Inc.", status="Pending", items=("8.01",)),
        ma_event("a3", "2026-11-02", role="acquirer", cp="Grand River Commerce, Inc.", agreement="2026-06-11", status="Closed", items=("2.01",)),
    ]
    deals = build_datasets(events)["deals"]
    assert len(deals) == 1
    d = deals[0]
    assert val(d["status"]) == "Closed"
    assert val(d["announcement_date"]) == "2026-06-11"
    assert val(d["target"]["name"]) == "Grand River Commerce, Inc."
    assert val(d["acquirer"]["name"]) == "Isabella Bank Corp"
    assert len(d["sources"]) == 3
    assert [t["date"] for t in d["timeline"]] == sorted(t["date"] for t in d["timeline"])


def test_different_agreements_by_same_filer_stay_separate():
    events = [
        ma_event("e1", "2026-03-03", name="ESPERION THERAPEUTICS INC", cik="1434868", role="acquirer", cp="Corstasis Therapeutics Inc.", agreement="2026-03-02"),
        ma_event("e2", "2026-05-01", name="ESPERION THERAPEUTICS INC", cik="1434868", role="target", cp="Essence Parent Inc.", agreement="2026-05-01"),
        ma_event("e3", "2026-07-13", name="ESPERION THERAPEUTICS INC", cik="1434868", role="target", cp="Essence Parent Inc.", agreement="2026-05-01", status="Closed", items=("2.01",)),
    ]
    clusters = cluster_ma_events(events)
    assert sorted(len(c) for c in clusters) == [1, 2]


def test_two_michigan_filers_on_one_deal_are_merged():
    events = [
        ma_event("m1", "2025-07-23", name="MERCANTILE BANK CORP", cik="1042729", role="acquirer", cp="Eastern Michigan Financial Corporation", agreement="2025-07-22"),
        ma_event("m2", "2025-07-23", name="EASTERN MICHIGAN FINANCIAL CORP", cik="9999", role="target", cp="Mercantile Bank Corporation", agreement="2025-07-22"),
    ]
    deals = build_datasets(events)["deals"]
    assert len(deals) == 1
    assert val(deals[0]["acquirer"]["name"]) == "Mercantile Bank Corp"
    assert deals[0]["michigan_link"] == "Both"


def test_unresolved_roles_are_flagged_not_guessed():
    deals = build_datasets([ma_event("u1", "2026-02-02", cp=None, items=("2.01",), status="Closed")])["deals"]
    d = deals[0]
    assert "roles_unresolved" in d["flags"]
    assert val(d["target"]["name"]) is None and val(d["acquirer"]["name"]) is None
    assert val(d["michigan_party"]["name"]) == "Isabella Bank Corp"
    assert val(d["michigan_party"]["county"]) == "Isabella County"


def test_closing_date_estimate_is_labelled():
    deals = build_datasets([ma_event("c1", "2026-02-05", role="acquirer", cp="Target Co., Inc.", status="Closed", items=("2.01",))])["deals"]
    close = deals[0]["closing_date"]
    assert close["value"] == "2026-02-05" and close["estimate"] is True


def test_real_8k_through_pipeline(fixture_text):
    hit = FilingHit(accession="0000842517-26-000040", form="8-K", file_date="2026-11-02", ciks=["0000842517"],
                    entities=[{"name": "ISABELLA BANK CORP", "tickers": ["ISBA"], "cik": "0000842517", "location": "Mt. Pleasant, MI", "state": "MI"}],
                    items=["2.01", "8.01", "9.01"], sics=["6022"], primary_document="isba.htm")
    event = analyze_ma_filing(hit, fixture_text("8k_isabella_bank_corp.htm"), "https://x/isba.htm")
    d = build_datasets([event])["deals"][0]
    assert d["title"] == "Isabella Bank Corp acquired Grand River Commerce, Inc."
    assert val(d["closing_date"]) == "2026-11-02"
    assert val(d["acquirer"]["region"]) == "Mid-Michigan"
    assert val(d["acquirer"]["gics_sub_industry"]) == "Regional Banks"
    assert d["acquirer"]["county"]["method"] == "derived"


def test_form_d_amendments_collapse_and_funds_route_to_capital_formation(fixture_text):
    def hit(acc, filed, cik):
        return FilingHit(accession=acc, form="D", file_date=filed, ciks=[cik], entities=[], file_nums=["021-1"], primary_document="primary_doc.xml")
    xml_op = fixture_text("form_d_operating_company.xml")
    e1 = formd_event(hit("d1", "2026-06-01", "0002163797"), xml_op, "u1")
    e2 = formd_event(hit("d2", "2026-11-06", "0002163797"), xml_op, "u2")
    fund = formd_event(hit("f1", "2026-11-01", "0009999999"), fixture_text("form_d_pooled_fund.xml"), "u3")
    out = build_datasets([e1, e2, fund])
    assert len(out["deals"]) == 1 and len(out["capital_formation"]) == 1
    deal = out["deals"][0]
    assert len(deal["sources"]) == 2 and val(deal["announcement_date"]) == "2026-06-01"
    assert val(deal["deal_type"]) == "Venture Round"
    assert deal["financials"]["amount_raised"]["source_text"] == "<totalAmountSold>166500</totalAmountSold>"
    assert val(out["capital_formation"][0]["category"]) == "Venture Capital Fund"
    assert parse_form_d(xml_op)["state"] == "MI"
