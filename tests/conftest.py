from pathlib import Path

import pytest

from pipeline.edgar import FilingHit

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_text():
    def load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")
    return load


@pytest.fixture
def make_hit():
    def build(**overrides) -> FilingHit:
        values = dict(
            accession="0000000000-26-000001",
            form="8-K",
            file_date="2026-11-02",
            ciks=["0000052234"],
            entities=[{"name": "ISABELLA BANK CORP", "tickers": ["ISBA"], "cik": "0000052234", "location": "Mt. Pleasant, MI", "state": "MI"}],
            items=["2.01", "9.01"],
            sics=["6022"],
            file_nums=[],
            documents=["isba-20261102.htm"],
            primary_document="isba-20261102.htm",
        )
        values.update(overrides)
        return FilingHit(**values)
    return build
