"""Rule-based deal-term extraction, tested on real SEC filings (tests/fixtures) and edge cases."""

import pytest

from pipeline.extraction import terms as T
from pipeline.extraction.htmltext import html_to_text


@pytest.fixture
def isabella(fixture_text):
    text = html_to_text(fixture_text("8k_isabella_bank_corp.htm"))
    return text, T.Party.from_text("Isabella Bank Corp", text)


@pytest.fixture
def endra(fixture_text):
    text = html_to_text(fixture_text("8k_endra_life_sciences_inc.htm"))
    return text, T.Party.from_text("ENDRA Life Sciences Inc.", text)


def test_party_aliases_include_defined_term(isabella):
    _, party = isabella
    assert "Isabella" in party.aliases and "the Company" in party.aliases


def test_uppercase_edgar_name_still_matches_text():
    party = T.Party.from_text("ISABELLA BANK CORP", 'Isabella Bank Corporation, a Michigan corporation ("Isabella")')
    assert "Isabella" in party.aliases


def test_completed_merger_role_and_counterparty(isabella):
    text, party = isabella
    role, evidence = T.filer_role(text, party, "8-K")
    assert role == "acquirer"
    assert "completed its previously announced merger" in evidence
    target = T.merger_sub_target(text, party)
    assert target[0] == "Grand River Commerce, Inc."


def test_agreement_and_closing_dates(isabella):
    text, _ = isabella
    assert T.agreement_date(text, "u")["value"] == "2026-06-11"
    close = T.closing_date(text, "u")
    assert close["value"] == "2026-11-02"
    assert close["source_text"].startswith("Effective on November 2, 2026")


def test_amendment_date_is_not_the_agreement_date(endra):
    text, _ = endra
    f = T.agreement_date(text, "u")
    assert f["value"] == "2026-06-25"  # original agreement, not the October 1 amendment


def test_merger_sub_target_resolves_defined_term(endra):
    text, party = endra
    assert T.filer_role(text, party, "8-K")[0] == "acquirer"
    assert T.merger_sub_target(text, party)[0] == "Noble Africa LLC"


def test_resolve_defined_term_skips_state_of_incorporation():
    text = '("ASPI"), a Delaware corporation, Noble Africa LLC, a Delaware limited liability company ("Noble"), and'
    assert T.resolve_defined_term("Noble", text) == "Noble Africa LLC"


def test_target_role_when_filer_is_acquired():
    text = ('On May 1, 2026, Esperion Therapeutics, Inc. (the "Company") entered into an Agreement and Plan of Merger (the "Merger Agreement") '
            'with Essence Parent Inc., a Delaware corporation ("Parent"). Merger Sub will merge with and into the Company, with the Company '
            'surviving as a wholly owned subsidiary of Parent.')
    party = T.Party.from_text("Esperion Therapeutics, Inc.", text)
    assert T.filer_role(text, party, "8-K")[0] == "target"
    assert T.find_counterparty(text, party)[0] == "Essence Parent Inc."
    assert T.agreement_date(text, "u")["value"] == "2026-05-01"


def test_private_placement_is_not_a_divestiture():
    text = "The Company agreed to sell and issue to the investor in a private placement offering 1,000,000 shares of common stock."
    party = T.Party.from_text("Example Corp", text)
    assert T.filer_role(text, party, "8-K") is None


def test_merger_proxy_filer_is_target():
    party = T.Party.from_text("Example Corp", "")
    assert T.filer_role("", party, "DEFM14A")[0] == "target"


def test_financials_require_labelled_values():
    text = (
        "The transaction values the company at an enterprise value of approximately $1.2 billion. "
        "Holders will receive $45.50 per share in cash. Each share has a par value of $0.01 per share. "
        "The business generated annual revenue of approximately $300 million and adjusted EBITDA of $100 million. "
        "The purchase price represents 12.0x trailing EBITDA."
    )
    fin = T.extract_financials(text, "u")
    assert fin["enterprise_value"]["value"] == 1.2e9
    assert fin["price_per_share"]["value"] == 45.5
    assert fin["revenue"]["value"] == 300e6
    assert fin["ebitda"]["value"] == 100e6
    assert fin["ev_ebitda"]["value"] == 12.0
    assert fin["consideration"]["value"] == "Cash"
    assert "enterprise value" in fin["enterprise_value"]["source_text"]


def test_par_value_is_never_a_price(isabella):
    text, _ = isabella
    assert "price_per_share" not in T.extract_financials(text, "u")


def test_unlabelled_dollar_amounts_are_ignored():
    assert T.extract_financials("The Company paid $5,000,000 in fees and has $2 billion of assets.", "u") == {}


def test_advisor_extraction_with_roles_and_people():
    text = ("Houlihan Lokey is serving as exclusive financial advisor to the Company, and Honigman LLP is serving as legal counsel. "
            "Robert W. Baird & Co. acted as financial advisor to Parent. The deal team was led by Jane Smith and John Doe.")
    party = T.Party.from_text("Example Corp", text)
    found = {(a["firm"], a["role"]) for a in T.extract_advisors(text, "u", party)}
    assert ("Houlihan Lokey", "financial") in found
    assert ("Honigman LLP", "legal") in found
    assert ("Robert W. Baird & Co.", "financial") in found


def test_opinion_heading_identifies_financial_advisor():
    text = "THE MERGER\nOpinion of Goldman Sachs & Co. LLC\nGoldman Sachs rendered its opinion to the board."
    advisors = T.extract_advisors(text, "u", T.Party.from_text("X Corp", text))
    assert any(a["firm"] == "Goldman Sachs & Co. LLC" and a["role"] == "financial" for a in advisors)


def test_rationale_is_verbatim_and_skips_boilerplate():
    text = ("This press release contains forward-looking statements about the combination will expand margins. "
            "The acquisition expands Acme's footprint across the Midwest and adds advanced machining capabilities.")
    f = T.extract_rationale(text, "u")
    assert f["value"].startswith("The acquisition expands Acme's footprint")
    assert f["source_text"] == f["value"]


def test_add_on_detection():
    text = "Precision Parts, a portfolio company of Huron Capital, has acquired Great Lakes Fab."
    ctx = T.extract_sponsor_context(text, "u")
    assert ctx["platform"]["value"] == "Precision Parts"
    assert ctx["sponsor"]["value"] == "Huron Capital"
    assert ctx["is_add_on"]["value"] is True


def test_status_priority():
    assert T.status_from_text("The parties terminated the merger agreement on June 1, 2026.")[0] == "Terminated"
    assert T.status_from_text("At the special meeting, shareholders approved the merger.")[0] == "Pending"
