"""
CopilotLens - JSON Cache Layer
Caches analysis results to disk so repeated queries are fast.
"""

import json
import os
import time
from pathlib import Path


CACHE_FILE = ".copilotlens_cache.json"
CACHE_TTL_SECONDS = 300  # 5 minutes


class AnalysisCache:
    def __init__(self, repo_path: str):
        self.cache_path = Path(repo_path) / CACHE_FILE
        self._data: dict = {}
        self._timestamps: dict = {}
        self._load()

    def get(self, key: str):
        if key in self._data:
            age = time.time() - self._timestamps.get(key, 0)
            if age < CACHE_TTL_SECONDS:
                return self._data[key]
        return None

    def set(self, key: str, value):
        self._data[key] = value
        self._timestamps[key] = time.time()
        self._save()

    def invalidate(self):
        self._data = {}
        self._timestamps = {}
        self._save()

    def _load(self):
        try:
            if self.cache_path.exists():
                raw = json.loads(self.cache_path.read_text())
                self._data = raw.get("data", {})
                self._timestamps = raw.get("timestamps", {})
        except Exception:
            pass

    def _save(self):
        try:
            self.cache_path.write_text(
                json.dumps({"data": self._data, "timestamps": self._timestamps}, indent=2)
            )
        except Exception:
            pass
