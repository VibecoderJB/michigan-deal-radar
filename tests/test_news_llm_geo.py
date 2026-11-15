"""News RSS parsing/extraction, LLM quote verification, geography and GICS mapping."""

from pipeline.extraction import llm
from pipeline.ingestion.web import WebClient
from pipeline.models import val
from pipeline.reference import geo, gics
from pipeline.sources import news
from pipeline.storage.news_linking import link_news

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Wire</title>
<item><title>Huron Capital Acquires Great Lakes Fabrication, a Grand Rapids Manufacturer</title><link>https://wire.example/a</link>
<pubDate>Tue, 03 Nov 2026 13:00:00 GMT</pubDate><description>&lt;p&gt;Transaction valued at $45 million.&lt;/p&gt;</description></item>
<item><title>Texas firm opens new office in Dallas</title><link>https://wire.example/b</link><pubDate>Tue, 03 Nov 2026 13:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Ann Arbor startup raises $12 million Series A</title>
<link href="https://news.example/c"/><published>2026-11-02T10:00:00Z</published><summary>The Ann Arbor company raised funding.</summary></entry></feed>"""


def test_parse_rss_and_atom():
    items = news.parse_feed(RSS) + news.parse_feed(ATOM)
    assert [i["link"] for i in items] == ["https://wire.example/a", "https://wire.example/b", "https://news.example/c"]
    assert items[0]["published"] == "2026-11-03"
    assert items[0]["summary"] == "Transaction valued at $45 million."


def test_michigan_and_deal_language_filter():
    feed = {"publisher": "PR Newswire", "kind": "press_release"}
    kept, dropped = (news.item_record(feed, i) for i in news.parse_feed(RSS))
    assert dropped is None
    assert kept["michigan_reference"] in ("Grand Rapids", "Huron Capital")
    assert kept["confidence"] == "High"
    ex = kept["extracted"]
    assert val(ex["acquirer"]) == "Huron Capital"
    assert val(ex["target"]).startswith("Great Lakes Fabrication")
    assert val(ex["value"]) == 45e6 and val(ex["status"]) == "Closed"


def test_financing_headline_and_rumor_confidence():
    ex = news.extract_deal("Ann Arbor startup Acme Robotics raises $12 million Series A", "", "u")
    assert ex["category"] == "Financing" and val(ex["round"]) == "Series A"
    rumor = news.item_record({"publisher": "Crain's", "kind": "news"},
                             {"title": "Detroit supplier Acme reportedly in talks as Big Corp to acquire Acme", "link": "u2", "published": "2026-11-01", "summary": ""})
    assert rumor["confidence"] == "Low"


def test_paywalled_feed_stores_headline_only():
    rec = news.item_record({"publisher": "Crain's Detroit Business", "kind": "news", "paywalled": True},
                           {"title": "Detroit's Acme acquires Beta Corp", "link": "u", "published": "2026-11-01", "summary": "Full paywalled lede text"})
    assert rec["summary"] == "" and rec["confidence"] == "Medium"


def test_news_creates_deal_and_links_to_existing():
    feed = {"publisher": "PR Newswire", "kind": "press_release"}
    item = news.item_record(feed, news.parse_feed(RSS)[0])
    deals = link_news([], [item])
    assert len(deals) == 1
    d = deals[0]
    assert val(d["deal_type"]) == "PE Buyout"  # Huron Capital is on the sponsor watchlist
    assert d["confidence"] == "High" and "news_only" in d["flags"]
    follow = dict(item, event_id="N-2", url="https://news.example/z", source_kind="News", confidence="Medium", publisher="Crain's", filed="2026-11-05")
    assert len(link_news(deals, [follow])) == 1
    assert len(deals[0]["sources"]) == 2


def test_robots_disallow_is_respected():
    client = WebClient()
    import urllib.robotparser
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(["User-agent: *", "Disallow: /rss"])
    client._robots["https://news.example"] = rp
    assert not client.allowed("https://news.example/rss/search?q=x")
    assert client.allowed("https://news.example/about")


SOURCE = "On June 11, 2026, Isabella Bank Corporation entered into an agreement to acquire Grand River Commerce, Inc. for cash and stock."


def test_llm_answer_accepted_only_with_verbatim_quote():
    good = {"filer_role": "acquirer", "counterparty": "Grand River Commerce, Inc.", "quote": SOURCE}
    assert llm.verify(good, SOURCE)
    assert not llm.verify({**good, "quote": "Isabella agreed to buy Grand River Commerce, Inc. for cash."}, SOURCE)  # paraphrase
    assert not llm.verify({**good, "counterparty": "Grand River Bank"}, SOURCE)  # name not in quote
    assert not llm.verify({**good, "filer_role": "seller"}, SOURCE)  # role unsupported by quote


def test_llm_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert llm.fill_roles(SOURCE, "Isabella", "u") is None


def test_geo_lookup_city_zip_and_fuzzy():
    assert geo.locate("Grand Rapids").county == "Kent County"
    assert geo.locate("Mt Pleasant").region == "Mid-Michigan"
    assert geo.locate("Farmington Hill").county == "Oakland County"  # typo in filing, fuzzy match
    loc = geo.locate("Nowhere Township", zip_code="49301")
    assert loc.county == "Kent County" and loc.method == "zip"
    assert len(geo.all_counties()) == 83


def test_gics_mapping_and_focus_sectors():
    assert gics.from_sic("3714") == ("Consumer Discretionary", "Automotive Parts & Equipment")
    assert gics.focus_sector(*gics.from_sic("3714")) == "Automotive & Mobility"
    assert gics.from_sic("6022") == ("Financials", "Regional Banks")
    assert gics.focus_sector(*gics.from_form_d("Other Technology")) == "Software & Technology"
    assert gics.focus_sector(*gics.from_sic("7363")) == "Business Services"
    assert gics.from_sic(None) is None
