import pytest

from pipeline.formd import parse_form_d
from pipeline.xmlutil import ParseError


def test_operating_company(fixture_text):
    d = parse_form_d(fixture_text("form_d_operating_company.xml"))
    assert d["issuer_name"] == "Krabby Co Inc."
    assert d["city"] == "Berkley"
    assert d["state"] == "MI"
    assert d["industry"] == "Other Technology"
    assert d["is_pooled_fund"] is False
    assert d["total_offering_amount"] == 1_500_000
    assert d["total_amount_sold"] == 166_500
    assert d["date_of_first_sale"] == "2026-10-26"
    assert d["exemptions"] == ["Rule 506(b)"]
    assert "Simple Agreement for Future Equity (SAFE)" in d["securities"]
    assert [p["name"] for p in d["related_persons"]] == ["Fletcher Liverance", "Nicholas Clayton"]
    assert d["related_persons"][0]["roles"] == ["Executive Officer", "Director"]


def test_pooled_fund_with_indefinite_offering(fixture_text):
    d = parse_form_d(fixture_text("form_d_pooled_fund.xml"))
    assert d["is_pooled_fund"] is True
    assert d["fund_type"] == "Venture Capital Fund"
    assert d["is_amendment"] is True
    assert d["offering_indefinite"] is True
    assert d["total_offering_amount"] is None
    assert d["total_amount_sold"] == 42_500_000  # thousands separators handled
    assert d["first_sale_yet_to_occur"] is True
    assert d["date_of_first_sale"] is None
    assert d["investor_count"] == 57
    assert d["related_persons"][0]["name"] == "Jane Q Investor"
    assert "ICA 3(c)(1)" in d["exemptions"]


@pytest.mark.parametrize("bad", ["", "   ", "<not-xml", "<foo></foo>", "<edgarSubmission></edgarSubmission>"])
def test_malformed_documents_raise_parse_error(bad):
    with pytest.raises(ParseError):
        parse_form_d(bad)
