# Copyright (C) 2026 xiaoxvan
# Licensed under AGPL-3.0. See LICENSE for details.

import time
from typing import Any, Optional


class MemoryCache:
    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}
        self._ttl_map = {
            "running": 30,
            "not_started": 300,
            "finished": 3600,
            "tournament": 21600,
            "match_detail": 600,
            "events": 30,
        }

    def get(self, key: str, category: str = "default") -> Optional[Any]:
        ttl = self._ttl_map.get(category, 300)
        entry = self._store.get(key)
        if not entry:
            return None
        ts, data = entry
        if time.time() - ts > ttl:
            del self._store[key]
            return None
        return data

    def set(self, key: str, data: Any):
        self._store[key] = (time.time(), data)

    def clear(self):
        self._store.clear()