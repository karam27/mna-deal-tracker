"""A polite HTTP client: identifies itself, rate-limits, and retries transient errors."""

from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)


class PoliteSession:
    """requests.Session wrapper with a minimum delay between calls and automatic retries.

    Retries cover rate limiting (429) and server errors (5xx) with exponential backoff,
    so a single flaky response does not break the whole pipeline run.
    """

    def __init__(self, user_agent: str, min_interval: float = 1.0, timeout: int = 30):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        retry = Retry(
            total=4,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.min_interval = min_interval
        self.timeout = timeout
        self._last_call = 0.0

    def get(self, url: str, **kwargs) -> requests.Response:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        log.debug("GET %s", url)
        response = self.session.get(url, timeout=self.timeout, **kwargs)
        self._last_call = time.monotonic()
        response.raise_for_status()
        return response
