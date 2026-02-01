"""Simple file based cache used to avoid hitting the SEC API repeatedly."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional


class DataCache:
    """Persist JSON-serialisable responses with a TTL.

    Each key is hashed to keep filenames filesystem-safe.
    """

    def __init__(self, base_path: str) -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.base_path / f"{digest}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._path_for_key(key)
        if not path.exists():
            return None

        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

        expires_at = payload.get("expires_at", 0)
        if expires_at and expires_at < time.time():
            # Expired cache entries are lazily removed.
            try:
                path.unlink()
            except OSError:
                pass
            return None

        return payload.get("value")

    def set(self, key: str, value: Any, ttl_hours: int) -> None:
        path = self._path_for_key(key)
        payload = {
            "expires_at": time.time() + (max(ttl_hours, 0) * 3600),
            "value": value,
        }

        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload))
        os.replace(tmp_path, path)
