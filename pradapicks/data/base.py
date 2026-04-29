from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

log = logging.getLogger(__name__)


class HTTPProvider:
    """Tiny shared HTTP layer with retries."""

    base_url: str = ""
    timeout: float = 12.0
    headers: dict[str, str] = {}

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"User-Agent": "Pradapicks/0.1", **self.headers},
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.3, min=0.3, max=3),
        retry=retry_if_exception_type((httpx.TransportError,)),
        reraise=True,
    )
    def _get(self, url: str, params: dict | None = None) -> Any:
        r = self._client.get(url, params=params)
        # Don't burn retries on 4xx — those are auth/block/blob, not transient.
        if r.status_code == 429:
            raise httpx.HTTPStatusError("rate limited", request=r.request, response=r)
        if 500 <= r.status_code < 600:
            r.raise_for_status()
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._client.close()


class SportProvider(HTTPProvider):
    """Interface every per-sport provider implements."""

    sport: str = ""

    # Each returns lists of dicts shaped for the DB layer.
    def fetch_schedule(self, on: date) -> list[dict]:
        raise NotImplementedError

    def fetch_player_box_scores(self, on: date) -> list[dict]:
        raise NotImplementedError

    def fetch_team_box_scores(self, on: date) -> list[dict]:
        raise NotImplementedError

    # The list of prop markets the model supports for this sport.
    @property
    def supported_markets(self) -> list[str]:
        return []
