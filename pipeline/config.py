"""Central configuration. Values can be overridden with environment variables.

The SEC requires every automated request to carry a User-Agent that names a person
and a contact email. That value is personal, so it is never stored in the repo:

* GitHub Actions: repository secret ``SEC_USER_AGENT``
* Local runs: the ``SEC_USER_AGENT`` environment variable, or a one-line file at
  ``~/.config/michigan-deal-radar/sec_user_agent`` (path overridable via ``SEC_USER_AGENT_FILE``)

Example value: ``MichiganDealRadar/2.0 (Jane Doe; jane@example.com)``
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MDR_DATA_DIR", ROOT_DIR / "data"))
BRIEFINGS_DIR = DATA_DIR / "briefings"
BACKUP_DIR = DATA_DIR / "backup"
QUALITY_DIR = DATA_DIR / "quality"
CONFIG_DIR = ROOT_DIR / "config"
REPORTS_DIR = Path(os.environ.get("MDR_REPORTS_DIR", ROOT_DIR / "_site" / "reports"))

DEALS_FILE = DATA_DIR / "deals.json"                      # M&A + financings (v2 schema)
CAPITAL_FORMATION_FILE = DATA_DIR / "capital_formation.json"  # pooled-fund & real-estate Form Ds
OWNERSHIP_FILE = DATA_DIR / "ownership.json"              # Schedule 13D stakes
EVIDENCE_FILE = DATA_DIR / "evidence.json"                # extracted SEC/news events (the audit trail)
EVIDENCE_TEXT_DIR = DATA_DIR / "evidence_text"            # gzipped filing text for offline re-extraction
META_FILE = DATA_DIR / "meta.json"

USER_AGENT_FILE = Path(
    os.environ.get("SEC_USER_AGENT_FILE", Path.home() / ".config" / "michigan-deal-radar" / "sec_user_agent")
)


def sec_user_agent() -> str:
    """Return the SEC User-Agent from the environment or the local config file."""
    value = os.environ.get("SEC_USER_AGENT", "").strip()
    if not value and USER_AGENT_FILE.exists():
        value = USER_AGENT_FILE.read_text(encoding="utf-8").strip()
    if "@" not in value:
        raise RuntimeError(
            "SEC_USER_AGENT is not set. SEC fair-access rules require a User-Agent with your name and "
            "email, e.g. 'MichiganDealRadar/2.0 (Jane Doe; jane@example.com)'. Set the SEC_USER_AGENT "
            f"environment variable (GitHub: repository secret) or write it to {USER_AGENT_FILE}."
        )
    return value


# SEC fair-access policy: identify yourself and stay under 10 requests/second.
# https://www.sec.gov/os/accessing-edgar-data
MAX_REQUESTS_PER_SECOND = 6.0  # deliberately well below the 10 req/s ceiling
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 4

# Polite defaults for non-SEC sources (press-release wires, news RSS, firm sites).
WEB_USER_AGENT = "MichiganDealRadar/2.0 (+https://github.com/VibecoderJB/michigan-deal-radar)"
WEB_MIN_INTERVAL_SECONDS = 2.0  # per host

STATE_CODE = "MI"
STATE_NAME = "Michigan"

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

DEFAULT_LOOKBACK_DAYS = 10
BACKFILL_DAYS = 730  # 24 months

# Optional LLM gap-fill (GitHub Models; free inside GitHub Actions via GITHUB_TOKEN).
LLM_ENABLED = os.environ.get("MDR_LLM", "0") == "1"
LLM_ENDPOINT = os.environ.get("MDR_LLM_ENDPOINT", "https://models.github.ai/inference/chat/completions")
LLM_MODEL = os.environ.get("MDR_LLM_MODEL", "openai/gpt-4o-mini")
LLM_MAX_CALLS_PER_RUN = int(os.environ.get("MDR_LLM_MAX_CALLS", "40"))
