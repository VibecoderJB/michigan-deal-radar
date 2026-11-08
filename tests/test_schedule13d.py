import pytest

from pipeline.schedule13d import parse_schedule_13d
from pipeline.xmlutil import ParseError


def test_structured_13d_amendment(fixture_text):
    d = parse_schedule_13d(fixture_text("schedule_13d_amendment.xml"))
    assert d["issuer_name"] == "Hagerty, Inc."
    assert d["issuer_state"] == "MI"
    assert d["issuer_city"] == "Traverse City"
    assert d["is_amendment"] is True
    assert d["amendment_no"] == "6"
    assert d["event_date"] == "2026-09-11"
    assert d["reporting_persons"][0]["name"] == "MARKEL GROUP INC."
    assert d["max_percent"] == 42


def test_rejects_other_forms():
    with pytest.raises(ParseError):
        parse_schedule_13d("<edgarSubmission><submissionType>D</submissionType></edgarSubmission>")
