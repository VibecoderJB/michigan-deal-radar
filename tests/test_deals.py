from pipeline.deals import build_8k_deal, build_form_d_deal, display_name, is_abs_vehicle, money, pick_ticker
from pipeline.eightk import analyze_8k
from pipeline.formd import parse_form_d


def test_money_formatting():
    assert money(1_500_000) == "$1.5M"
    assert money(2_000_000_000) == "$2B"
    assert money(166_500) == "$166.5K"
    assert money(None) == "an undisclosed amount"


def test_display_name_titles_shouty_names():
    assert display_name("SUN COMMUNITIES INC") == "Sun Communities Inc"
    assert display_name("DTE ENERGY CO") == "DTE Energy Co"
    assert display_name("INDEPENDENT BANK CORP /MI/") == "Independent Bank Corp"
    assert display_name("Krabby Co Inc.") == "Krabby Co Inc."


def test_pick_ticker_prefers_common_stock():
    assert pick_ticker(["DTB", "DTE", "DTG"], "DTE ENERGY CO") == "DTE"
    assert pick_ticker(["ADC", "ADC-PA"], "AGREE REALTY CORP") == "ADC"
    assert pick_ticker([], "X") is None


def test_form_d_deal_record(fixture_text, make_hit):
    hit = make_hit(form="D", accession="0002163797-26-000001", ciks=["0002163797"], file_nums=["021-603899"], items=["06B"], sics=[])
    deal = build_form_d_deal(hit, parse_form_d(fixture_text("form_d_operating_company.xml")))
    assert deal["id"] == "D-2163797-021-603899"
    assert deal["type"] == "Fundraise" and deal["subtype"] == "Private Placement"
    assert deal["sector"] == "Technology"
    assert deal["amount"] == 1_500_000 and deal["amount_sold"] == 166_500
    assert deal["summary"].startswith("Krabby Co Inc., a Berkley-based technology company, filed a $1.5M SAFE offering")
    assert deal["url"].endswith("/2163797/000216379726000001/0002163797-26-000001-index.htm")


def test_pooled_fund_deal(fixture_text, make_hit):
    hit = make_hit(form="D/A", ciks=["0009999999"], file_nums=["021-1"], sics=[])
    deal = build_form_d_deal(hit, parse_form_d(fixture_text("form_d_pooled_fund.xml")))
    assert deal["subtype"] == "Venture Capital Fund"
    assert deal["sector"] == "Private Funds"
    assert deal["form"] == "D/A"
    assert deal["amount"] == 42_500_000  # falls back to amount sold when indefinite
    assert "an Ann Arbor-based venture capital fund" in deal["summary"]


def test_8k_deal_record(fixture_text, make_hit):
    hit = make_hit()
    analysis = analyze_8k(fixture_text("8k_isabella_bank_corp.htm"), hit.items, "ISABELLA BANK CORP")
    deal = build_8k_deal(hit, analysis)
    assert deal["id"] == "8K-0000000000-26-000001"
    assert deal["company"] == "Isabella Bank Corp" and deal["ticker"] == "ISBA"
    assert deal["sector"] == "Financial Services"
    assert deal["summary"].endswith("Grand River Commerce, Inc.")


def test_abs_trusts_are_excluded(make_hit):
    trust = make_hit(entities=[{"name": "FORD CREDIT FLOORPLAN MASTER OWNER TRUST A", "tickers": [], "cik": "1", "location": "Dearborn, MI", "state": "MI"}], sics=[])
    assert is_abs_vehicle(trust)
    assert is_abs_vehicle(make_hit(sics=["6189"]))
    assert not is_abs_vehicle(make_hit())
