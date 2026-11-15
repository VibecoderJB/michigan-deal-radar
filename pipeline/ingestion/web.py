"""Polite HTTP client for non-SEC public sources (wire RSS, news RSS, firm pages).

* Checks robots.txt before every fetch and refuses disallowed URLs.
* One request per host every ``WEB_MIN_INTERVAL_SECONDS``; retries with backoff on 429/5xx.
* Identifies itself with a descriptive User-Agent that links to the project.
"""

from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests

from .. import config

log = logging.getLogger(__name__)


class RobotsDisallowed(RuntimeError):
    pass


class WebClient:
    def __init__(self, user_agent: str = config.WEB_USER_AGENT, min_interval: float = config.WEB_MIN_INTERVAL_SECONDS) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.8"})
        self.user_agent = user_agent
        self.min_interval = min_interval
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = self.session.get(f"{base}/robots.txt", timeout=15)
                if resp.status_code >= 400:
                    rp = None  # no robots.txt: crawling allowed by convention
                else:
                    rp.parse(resp.text.splitlines())
            except requests.RequestException as exc:
                log.warning("robots.txt unreachable for %s (%s); skipping host", base, exc)
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(["User-agent: *", "Disallow: /"])  # fail closed
            self._robots[base] = rp
        return self._robots[base]

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        return True if rp is None else rp.can_fetch(self.user_agent, url)

    def get(self, url: str) -> requests.Response:
        if not self.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        host = urlsplit(url).netloc
        wait = self.min_interval - (time.monotonic() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        last_exc: Exception | None = None
        for attempt in range(3):
            self._last[host] = time.monotonic()
            try:
                resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT_SECONDS)
                if resp.status_code == 200:
                    return resp
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {resp.status_code} for {url}")
                last_exc = requests.HTTPError(f"HTTP {resp.status_code}")
            except requests.RequestException as exc:
                last_exc = exc
            time.sleep(2 ** (attempt + 1))
        raise requests.HTTPError(f"Giving up on {url}: {last_exc}")
