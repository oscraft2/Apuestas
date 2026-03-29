import json
import os
import time
from typing import Any, Optional


class CacheManager:
    def __init__(self, cache_dir: str, ttl_hours: int = 6):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_hours * 3600
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, key: str) -> str:
        safe = key.replace("/", "_").replace(":", "_")
        return os.path.join(self.cache_dir, f"{safe}.json")

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not os.path.exists(path):
            return None
        if time.time() - os.path.getmtime(path) > self.ttl_seconds:
            return None
        with open(path, "r") as f:
            return json.load(f)

    def set(self, key: str, data: Any) -> None:
        with open(self._path(key), "w") as f:
            json.dump(data, f)

    def invalidate(self, key: str) -> None:
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)
