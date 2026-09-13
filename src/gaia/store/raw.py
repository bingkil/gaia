"""Immutable raw payload storage.

Spec section 10.2 requires the exact provider bytes to be durable before any
parsing happens, so a parser fix can be replayed without refetching. Locally
that is a directory rather than a bucket; the key layout is unchanged.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from ..db import utcnow


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def key_for(
        self, provider: str, source_id: str, sha256: str, received: datetime, ext: str
    ) -> str:
        safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in source_id)[:80]
        stamp = received.strftime("%Y%m%dT%H%M%S%fZ")
        return (
            f"raw/{provider}/{received:%Y/%m/%d}/{safe_id or 'unknown'}/"
            f"{stamp}_{sha256[:16]}.{ext}"
        )

    def put(
        self, provider: str, source_id: str, payload: bytes, ext: str = "json"
    ) -> tuple[str, str]:
        """Write payload and return (object_key, sha256).

        Writing is idempotent: an identical payload for the same key is a no-op,
        so replay never duplicates bytes on disk.
        """
        sha256 = hashlib.sha256(payload).hexdigest()
        key = self.key_for(provider, source_id, sha256, utcnow(), ext)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(payload)
            tmp.replace(path)
        return key, sha256

    def get(self, key: str) -> bytes | None:
        if not key:
            return None
        path = self.root / key
        return path.read_bytes() if path.is_file() else None

    def iter_keys(self, provider: str | None = None):
        base = self.root / "raw"
        if provider:
            base = base / provider
        if not base.exists():
            return
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.name.endswith(".tmp"):
                yield str(path.relative_to(self.root)).replace("\\", "/")
