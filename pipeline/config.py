"""Central configuration. Values can be overridden with environment variables."""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MDR_DATA_DIR", ROOT_DIR / "data"))
BRIEFINGS_DIR = DATA_DIR / "briefings"

# SEC fair-access policy: identify yourself and stay under 10 requests/second.
# https://www.sec.gov/os/accessing-edgar-data
USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "MichiganDealRadar/1.0 (student research project; jacksonrbond@gmail.com)",
)
MAX_REQUESTS_PER_SECOND = 6.0  # deliberately well below the 10 req/s ceiling
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 4

STATE_CODE = "MI"
STATE_NAME = "Michigan"

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

# Daily runs look back this many days so late-indexed filings are not missed.
DEFAULT_LOOKBACK_DAYS = 10
BACKFILL_DAYS = 365
