"""One bad filing must never crash the run."""

from datetime import date

from pipeline import collectors
from pipeline.edgar import FilingHit


class FakeClient:
    def __init__(self, docs):
        self.docs = docs
        self.request_count = 0

    def get_text(self, url):
        for key, value in self.docs.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise RuntimeError(f"unexpected url {url}")


def _hit(acc, cik):
    return FilingHit(accession=acc, form="D", file_date="2026-11-02", ciks=[cik],
                     entities=[{"name": "X", "tickers": [], "cik": cik, "location": "Detroit, MI", "state": "MI"}],
                     file_nums=[f"021-{cik}"], primary_document="primary_doc.xml")


def test_bad_filing_is_logged_and_skipped(monkeypatch, fixture_text):
    good, broken, http_fail = _hit("0002163797-26-000001", "2163797"), _hit("0000000001-26-000002", "1"), _hit("0000000002-26-000003", "2")
    monkeypatch.setattr(collectors, "search_filings", lambda *a, **k: [good, broken, http_fail])
    client = FakeClient({
        "/2163797/": fixture_text("form_d_operating_company.xml"),
        "/1/": "<edgarSubmission><broken",
        "/2/": RuntimeError("HTTP 500"),
    })
    result = collectors.collect_form_d(client, date(2026, 11, 1), date(2026, 11, 8), known=set())
    assert [d["company"] for d in result.deals] == ["Krabby Co Inc."]
    assert {e["accession"] for e in result.errors} == {broken.accession, http_fail.accession}


def test_known_accessions_are_not_refetched(monkeypatch):
    hit = _hit("0000000001-26-000002", "1")
    monkeypatch.setattr(collectors, "search_filings", lambda *a, **k: [hit])
    result = collectors.collect_form_d(FakeClient({}), date(2026, 11, 1), date(2026, 11, 8), known={hit.accession})
    assert result.skipped == 1 and not result.errors
