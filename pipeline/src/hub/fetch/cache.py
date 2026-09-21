"""Disk cache for raw nba_api responses, keyed by endpoint name and parameters.

Every response is written once and never refetched for the same key, which is
what makes the backfill resumable: rerunning it after an interruption just
skips every (endpoint, params) pair that already has a cache file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class RawCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, endpoint: str, params: dict[str, Any]) -> Path:
        key = json.dumps(params, sort_keys=True, default=str)
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]  # noqa: S324
        return self.root / endpoint / f"{digest}.json"

    def get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any] | None:
        path = self._path(endpoint, params)
        if not path.exists():
            return None
        with path.open("r") as f:
            return json.load(f)

    def put(self, endpoint: str, params: dict[str, Any], payload: dict[str, Any]) -> None:
        path = self._path(endpoint, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(payload, f)
        tmp.rename(path)

    def has(self, endpoint: str, params: dict[str, Any]) -> bool:
        return self._path(endpoint, params).exists()
