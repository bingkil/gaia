"""Credentials pasted at runtime, held outside git and outside API responses.

Lives beside the database in the data directory, which is already ignored by
git. Values are only ever returned masked.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path

log = logging.getLogger(__name__)


def mask(value: str) -> str:
    """A tail short enough to identify a key without disclosing it."""
    if len(value) <= 4:
        return "•" * len(value)
    return "•" * 8 + value[-4:]


class SecretStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("secrets file unreadable, ignoring: %s", self.path)
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(k): v for k, v in raw.items() if isinstance(v, str)}

    def get(self, key: str) -> str:
        return self.load().get(key, "")

    def set(self, key: str, value: str) -> None:
        data = self.load()
        data[key] = value
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:  # noqa: S110 - best effort, Windows ACLs differ
            pass

    def clear(self, key: str) -> None:
        data = self.load()
        if data.pop(key, None) is None:
            return
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
