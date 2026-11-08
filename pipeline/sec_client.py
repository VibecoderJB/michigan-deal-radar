"""A small, polite HTTP client for SEC EDGAR.

* Sends a descriptive User-Agent with a contact email (required by the SEC).
* Throttles to ``MAX_REQUESTS_PER_SECOND`` across all calls.
* Retries transient failures (429 / 5xx / connection errors) with backoff.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

from . import config

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SecError(RuntimeError):
    """Raised when EDGAR cannot be reached after all retries."""


class SecClient:
    def __init__(
        self,
        user_agent: str = config.USER_AGENT,
        max_rps: float = config.MAX_REQUESTS_PER_SECOND,
        session: requests.Session | None = None,
    ) -> None:
        if "@" not in user_agent:
            raise ValueError("SEC requires a contact email in the User-Agent")
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        )
        self._min_interval = 1.0 / max_rps
        self._last_request = 0.0
        self._lock = threading.Lock()
        self.request_count = 0

    def _throttle(self) -> None:
        with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def get(self, url: str, params: dict[str, Any] | None = None) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(config.MAX_RETRIES + 1):
            self._throttle()
            self.request_count += 1
            try:
                resp = self.session.get(
                    url, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS
                )
            except requests.RequestException as exc:
                last_error = exc
            else:
                if resp.status_code == 200:
                    return resp
                if resp.status_code not in RETRYABLE_STATUS:
                    raise SecError(f"HTTP {resp.status_code} for {resp.url}")
                last_error = SecError(f"HTTP {resp.status_code} for {resp.url}")
            backoff = 2 ** attempt
            log.warning("Retrying %s in %ss (%s)", url, backoff, last_error)
            time.sleep(backoff)
        raise SecError(f"Giving up on {url}: {last_error}")

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        return self.get(url, params).json()

    def get_text(self, url: str) -> str:
        resp = self.get(url)
        resp.encoding = resp.encoding or "utf-8"
        return resp.text
