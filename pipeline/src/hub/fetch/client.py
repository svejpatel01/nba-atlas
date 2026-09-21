"""Throttled, cached, retrying fetch layer over nba_api endpoint classes.

Every call to `fetch` first checks the raw cache; a hit returns instantly with
no network request and no throttle delay. A miss calls stats.nba.com, throttled
to about one request per second with jitter, retries on failure with
exponential backoff, and writes the raw response to cache before returning.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Protocol

from hub.fetch.cache import RawCache

logger = logging.getLogger("hub.fetch")


class FetchError(RuntimeError):
    """Raised when an endpoint call fails after all retries are exhausted."""


class _Endpoint(Protocol):
    """An nba_api endpoint instance, already called (get_request() has run)."""


class Throttle:
    """Sleeps as needed to keep calls to roughly one per second, plus jitter."""

    def __init__(self, min_interval: float = 1.0, jitter: float = 0.4) -> None:
        self.min_interval = min_interval
        self.jitter = jitter
        self._last_call: float | None = None

    def wait(self) -> None:
        if self._last_call is not None:
            elapsed = time.monotonic() - self._last_call
            delay = self.min_interval + random.uniform(0, self.jitter) - elapsed
            if delay > 0:
                time.sleep(delay)
        self._last_call = time.monotonic()


class NbaFetcher:
    def __init__(
        self,
        cache: RawCache,
        throttle: Throttle | None = None,
        max_retries: int = 5,
        backoff_base: float = 2.0,
        backoff_cap: float = 60.0,
        timeout: int = 30,
    ) -> None:
        self.cache = cache
        self.throttle = throttle or Throttle()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.timeout = timeout

    def fetch(
        self,
        endpoint_name: str,
        params: dict[str, Any],
        make_endpoint: callable[[], _Endpoint],
        extract: callable[[_Endpoint], dict[str, Any]],
    ) -> dict[str, Any]:
        """Fetch one endpoint call, using the cache when possible.

        `params` is the cache key (should include every parameter that
        affects the response). `make_endpoint` actually constructs and calls
        the nba_api endpoint class; `extract` pulls a JSON-serializable dict
        out of it. Both are only invoked on a cache miss. `extract` varies by
        endpoint: most nba_api endpoints normalize cleanly via
        `get_normalized_dict()`, but a few (e.g. PlayByPlayV3) return an empty
        normalized dict and need their raw `{headers, data}` dataset instead —
        see hub.fetch.nba for the per-endpoint choice.
        """
        cached = self.cache.get(endpoint_name, params)
        if cached is not None:
            logger.debug("cache hit: %s %s", endpoint_name, params)
            return cached

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self.throttle.wait()
            try:
                logger.info("fetching %s %s (attempt %d)", endpoint_name, params, attempt)
                endpoint = make_endpoint()
                payload = extract(endpoint)
                self.cache.put(endpoint_name, params, payload)
                return payload
            except Exception as exc:  # noqa: BLE001 - retry on anything, then raise a clear error
                last_error = exc
                if attempt < self.max_retries:
                    sleep_for = min(self.backoff_base**attempt, self.backoff_cap)
                    logger.warning(
                        "fetch failed for %s %s (attempt %d/%d): %s — retrying in %.1fs",
                        endpoint_name,
                        params,
                        attempt,
                        self.max_retries,
                        exc,
                        sleep_for,
                    )
                    time.sleep(sleep_for)

        raise FetchError(
            f"Giving up on {endpoint_name} {params} after {self.max_retries} attempts: "
            f"{last_error}. Is stats.nba.com reachable from this machine?"
        ) from last_error
