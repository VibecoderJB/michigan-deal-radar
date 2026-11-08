from datetime import date

from pipeline.edgar import _merge_hit, month_windows, parse_display_name, parse_index_documents


def test_parse_display_name_with_tickers():
    d = parse_display_name("DTE ENERGY CO  (DTB, DTE, DTG)  (CIK 0000936340)")
    assert d == {"name": "DTE ENERGY CO", "tickers": ["DTB", "DTE", "DTG"], "cik": "0000936340"}


def test_parse_display_name_without_tickers():
    d = parse_display_name("Krabby Co Inc.  (CIK 0002163797)")
    assert d["name"] == "Krabby Co Inc." and d["tickers"] == [] and d["cik"] == "0002163797"


def test_month_windows_cover_range_without_gaps():
    windows = list(month_windows(date(2026, 1, 1), date(2026, 3, 15)))
    assert windows[0][0] == date(2026, 1, 1)
    assert windows[-1][1] == date(2026, 3, 15)
    for (_, end), (start, _) in zip(windows, windows[1:]):
        assert (start - end).days == 1


def test_merge_hit_groups_documents_by_accession():
    store = {}
    base = {"adsh": "0001-26-1", "form": "8-K", "file_date": "2026-11-01", "ciks": ["1"], "display_names": ["ACME CORP  (ACME)  (CIK 0000000001)"], "biz_locations": ["Detroit, MI"], "items": ["1.01"]}
    _merge_hit(store, {"_id": "0001-26-1:ex99.htm", "_source": {**base, "file_type": "EX-99.1"}})
    _merge_hit(store, {"_id": "0001-26-1:acme-8k.htm", "_source": {**base, "file_type": "8-K"}})
    hit = store["0001-26-1"]
    assert hit.primary_document == "acme-8k.htm"
    assert hit.documents == ["ex99.htm", "acme-8k.htm"]
    assert hit.entities[0]["state"] == "MI" and hit.entities[0]["tickers"] == ["ACME"]


def test_parse_filing_index(fixture_text):
    docs = parse_index_documents(fixture_text("filing_index.htm"))
    assert docs[0] == ("xbrl-20261023.htm", "8-K")
    assert any(t == "EX-99.2" for _, t in docs)
