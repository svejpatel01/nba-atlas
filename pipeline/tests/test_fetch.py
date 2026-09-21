import time

import pytest

from hub.fetch.cache import RawCache
from hub.fetch.client import FetchError, NbaFetcher, Throttle


class TestRawCache:
    def test_miss_returns_none(self, tmp_path):
        cache = RawCache(tmp_path)
        assert cache.get("endpoint", {"a": 1}) is None
        assert cache.has("endpoint", {"a": 1}) is False

    def test_put_then_get_round_trips(self, tmp_path):
        cache = RawCache(tmp_path)
        cache.put("endpoint", {"a": 1}, {"rows": [1, 2, 3]})
        assert cache.get("endpoint", {"a": 1}) == {"rows": [1, 2, 3]}
        assert cache.has("endpoint", {"a": 1}) is True

    def test_different_params_are_different_keys(self, tmp_path):
        cache = RawCache(tmp_path)
        cache.put("endpoint", {"season": "2023-24"}, {"v": 1})
        cache.put("endpoint", {"season": "2024-25"}, {"v": 2})
        assert cache.get("endpoint", {"season": "2023-24"}) == {"v": 1}
        assert cache.get("endpoint", {"season": "2024-25"}) == {"v": 2}


class TestThrottle:
    def test_first_call_does_not_sleep(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
        Throttle(min_interval=1.0, jitter=0.0).wait()
        assert sleeps == []

    def test_second_call_sleeps_for_remaining_interval(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
        clock = [100.0]
        monkeypatch.setattr(time, "monotonic", lambda: clock[0])

        throttle = Throttle(min_interval=1.0, jitter=0.0)
        throttle.wait()  # t=100.0, no sleep
        clock[0] = 100.3  # only 0.3s elapsed
        throttle.wait()
        assert sleeps == [pytest.approx(0.7, abs=1e-6)]


class TestNbaFetcher:
    def test_cache_hit_skips_network(self, tmp_path):
        cache = RawCache(tmp_path)
        cache.put("ep", {"a": 1}, {"result": [1]})
        fetcher = NbaFetcher(cache, throttle=Throttle(min_interval=0))
        calls = []
        result = fetcher.fetch("ep", {"a": 1}, lambda: calls.append(1), lambda e: {})
        assert result == {"result": [1]}
        assert calls == []

    def test_cache_miss_calls_network_and_caches(self, tmp_path):
        cache = RawCache(tmp_path)
        fetcher = NbaFetcher(cache, throttle=Throttle(min_interval=0))
        result = fetcher.fetch("ep", {"a": 1}, lambda: object(), lambda e: {"result": [42]})
        assert result == {"result": [42]}
        assert cache.get("ep", {"a": 1}) == {"result": [42]}

    def test_retries_then_succeeds(self, tmp_path, monkeypatch):
        monkeypatch.setattr(time, "sleep", lambda s: None)
        cache = RawCache(tmp_path)
        fetcher = NbaFetcher(cache, throttle=Throttle(min_interval=0), max_retries=3)
        attempts = {"n": 0}

        def make_endpoint():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ConnectionError("boom")
            return object()

        result = fetcher.fetch("ep", {}, make_endpoint, lambda e: {"ok": True})
        assert result == {"ok": True}
        assert attempts["n"] == 3

    def test_exhausts_retries_and_raises_fetch_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(time, "sleep", lambda s: None)
        cache = RawCache(tmp_path)
        fetcher = NbaFetcher(cache, throttle=Throttle(min_interval=0), max_retries=2)

        def always_fails():
            raise TimeoutError("unreachable")

        with pytest.raises(FetchError, match="unreachable"):
            fetcher.fetch("ep", {}, always_fails, lambda e: {})
        assert cache.has("ep", {}) is False
