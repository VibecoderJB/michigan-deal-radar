from pipeline.eightk import analyze_8k, classify_agreement, extract_sections, find_counterparty, parse_amount


def test_completed_merger(fixture_text):
    r = analyze_8k(fixture_text("8k_isabella_bank_corp.htm"), ["2.01", "8.01", "9.01"], "ISABELLA BANK CORP")
    assert r["type"] == "M&A"
    assert r["subtype"] == "Acquisition/Disposition Completed"
    assert r["counterparty"] == "Grand River Commerce, Inc."
    assert r["excerpt"].startswith("Effective on November 2, 2026")
    assert len(r["excerpt"]) <= 421


def test_merger_agreement_under_item_101(fixture_text):
    r = analyze_8k(fixture_text("8k_endra_life_sciences_inc.htm"), ["1.01", "9.01"], "ENDRA Life Sciences Inc.")
    assert r["type"] == "M&A"
    assert r["subtype"] == "Definitive Agreement"
    assert r["counterparty"] == "ASP Isotopes Inc."


def test_non_ma_material_agreement_uppercase_heading(fixture_text):
    r = analyze_8k(fixture_text("8k_stoneridge_inc.htm"), ["1.01", "9.01"], "STONERIDGE INC")
    assert r["type"] == "Material Agreement"
    assert r["subtype"] == "Employment Agreement"
    assert r["amount_mentioned"] is None


def test_earnings_release_mentioning_merger_is_not_a_deal():
    html = "<p>Item 2.02 Results of Operations and Financial Condition</p><p>On November 4 the Company issued a press release, attached as Exhibit 99.1, which references the merger agreement.</p>"
    r = analyze_8k(html, ["2.02", "9.01"], "Example Corp")
    assert r["type"] is None


def test_section_extraction_ignores_short_cross_references():
    text = "Item 1.01 Entry into a Material Definitive Agreement.\nThe Company signed a credit agreement with a syndicate of lenders for a revolving facility.\nItem 2.03 See Item 1.01.\nItem 9.01 Financial Statements and Exhibits. Exhibit 10.1 Credit Agreement dated today."
    sections = extract_sections(text)
    assert "credit agreement" in sections["1.01"]
    assert "2.03" not in sections


def test_parse_amount_picks_largest_figure():
    assert parse_amount("a fee of $5,000,000 and total consideration of $1.2 billion") == 1.2e9
    assert parse_amount("approximately $350 million in cash") == 350e6
    assert parse_amount("$0.01 par value") is None
    assert parse_amount("") is None


def test_classify_agreement_kinds():
    assert classify_agreement("entered into a Credit Agreement with JPMorgan") == "Credit Facility"
    assert classify_agreement("an Indenture governing 5.25% senior notes") == "Debt Offering"
    assert classify_agreement("a supply agreement with a customer") == "Commercial Agreement"
    assert classify_agreement("something unusual") == "Material Agreement"


def test_counterparty_skips_self_and_merger_sub():
    text = "pursuant to the merger with Merger Sub Inc. and the transaction with Acme Widgets Corp."
    assert find_counterparty(text, "Example Holdings") == "Acme Widgets Corp."


def test_counterparty_after_defined_merger_agreement():
    text = 'entered into an Agreement and Plan of Merger (the "Merger Agreement") with HNI Corporation, an Iowa corporation'
    assert find_counterparty(text, "Steelcase Inc") == "HNI Corporation"


def test_credit_agreement_mentioning_merger_is_material_agreement():
    html = (
        "<p>Item 1.01 Entry into a Material Definitive Agreement.</p><p>On December 24, 2025, the Company entered into a "
        "Credit Agreement with U.S. Bank National Association providing a $100 million term loan. Proceeds will fund "
        "amounts payable under the Agreement and Plan of Merger with Example Financial Corp. described in prior filings, "
        "and for general corporate purposes of the combined company going forward.</p>"
    )
    r = analyze_8k(html, ["1.01", "9.01"], "Mercantile Bank Corp")
    assert r["type"] == "Material Agreement"
    assert r["subtype"] == "Credit Facility"


def test_notes_tender_offer_is_not_ma():
    html = (
        "<p>Item 1.01 Entry into a Material Definitive Agreement.</p><p>On June 16, 2026 the Company issued $1.0 billion "
        "of Senior Notes due 2031 under an indenture. Proceeds fund the tender offer for its outstanding 2027 notes.</p>"
    )
    assert analyze_8k(html, ["1.01", "2.03"], "Whirlpool Corp")["type"] == "Material Agreement"


def test_counterparty_with_spaced_quotes():
    text = 'entered into an Agreement and Plan of Merger (the " Merger Agreement ") with Motown Acquisition Corp., a Delaware corporation'
    assert find_counterparty(text, "Penske Automotive Group") == "Motown Acquisition Corp."
