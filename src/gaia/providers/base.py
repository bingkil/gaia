"""Adapter base classes.

An adapter owns transport and provider-specific parsing only. It must never
decide severity, deduplicate across providers, or send alerts — those belong to
the engine. Spec section 10.1.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import random
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..db import utcnow
from ..domain.enums import HazardType
from ..domain.models import Observation
from ..store import ObservationRepo, PollStateRepo, ProviderHealthRepo, RawStore

log = logging.getLogger(__name__)

USER_AGENT = "GAIA/0.1 (local-first geohazard awareness; personal use)"


class ParseFailure(Exception):
    """Raised after raw bytes are safely stored but parsing failed.

    The payload is retained so a parser fix can be replayed against it.
    """

    def __init__(self, provider: str, object_key: str, cause: Exception) -> None:
        super().__init__(f"{provider} parse failed; raw retained at {object_key}: {cause}")
        self.provider = provider
        self.object_key = object_key
        self.cause = cause


class AdapterContext:
    """Shared services handed to every adapter."""

    def __init__(
        self,
        raw_store: RawStore,
        observations: ObservationRepo,
        health: ProviderHealthRepo,
        poll_state: PollStateRepo,
        on_observation: Any,
    ) -> None:
        self.raw = raw_store
        self.observations = observations
        self.health = health
        self.poll_state = poll_state
        self.on_observation = on_observation


class HazardAdapter(abc.ABC):
    name: str
    hazard_type: HazardType
    parser_version: str
    attribution: str = ""
    raw_extension: str = "json"

    def __init__(self, ctx: AdapterContext, settings: Any) -> None:
        self.ctx = ctx
        self.settings = settings

    @abc.abstractmethod
    async def run(self) -> None:
        """Long-running loop. Must not return until cancelled."""

    @abc.abstractmethod
    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        """Provider bytes to a list of normalized dicts. Pure and replayable."""

    async def ingest(self, raw: bytes, source_hint: str = "batch") -> int:
        """Persist raw bytes, then parse, then emit observations.

        The ordering is deliberate: bytes reach durable storage before any
        parsing so a parser fix can be replayed without refetching.
        """
        key, sha256 = await asyncio.to_thread(
            self.ctx.raw.put, self.name, source_hint, raw, self.raw_extension
        )

        try:
            records = self.parse(raw)
        except Exception as exc:
            log.exception("%s parse failed; raw payload retained at %s", self.name, key)
            raise ParseFailure(self.name, key, exc) from exc

        accepted = 0
        for record in records:
            obs = self.to_observation(record, key, sha256)
            if obs is None:
                continue
            inserted = await asyncio.to_thread(self.ctx.observations.insert, obs)
            if not inserted:
                continue
            accepted += 1
            await self.ctx.on_observation(obs)
        return accepted

    def to_observation(
        self, record: dict[str, Any], raw_key: str, sha256: str
    ) -> Observation | None:
        from ..store import new_id

        source_id = record.get("source_id")
        if not source_id:
            return None
        return Observation(
            message_id=new_id("obs"),
            provider=self.name,
            source_id=str(source_id),
            source_revision=str(record.get("source_revision") or "1"),
            hazard_type=HazardType(record.get("hazard_type") or self.hazard_type),
            action=record.get("action", "UPSERT"),
            source_issued_at=record.get("source_issued_at"),
            observed_at=record.get("observed_at"),
            ingested_at=utcnow(),
            parser_version=self.parser_version,
            raw_object_key=raw_key,
            raw_sha256=sha256,
            normalized=record.get("normalized", {}),
            validation_warnings=record.get("warnings", []),
        )


class PollingAdapter(HazardAdapter):
    """HTTP polling with conditional requests, jitter, and backoff."""

    async def run(self) -> None:
        backoff = 1.0
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
        async with httpx.AsyncClient(
            timeout=30.0, headers=headers, follow_redirects=True
        ) as client:
            while True:
                try:
                    count = await self.poll_once(client)
                    await asyncio.to_thread(self.ctx.health.record_success, self.name, count)
                    backoff = 1.0
                    delay = self.settings.poll_seconds
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("%s poll failed: %s", self.name, exc)
                    await asyncio.to_thread(self.ctx.health.record_error, self.name, str(exc))
                    backoff = min(backoff * 2, 300.0)
                    delay = backoff
                # Jitter keeps repeated polls from synchronising on the provider.
                await asyncio.sleep(delay * random.uniform(0.95, 1.10))

    @abc.abstractmethod
    async def poll_once(self, client: httpx.AsyncClient) -> int: ...

    async def fetch_conditional(
        self, client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None
    ) -> bytes | None:
        """GET with ETag/If-Modified-Since. Returns None when unchanged."""
        etag, last_modified = await asyncio.to_thread(self.ctx.poll_state.get, self.name)
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        response = await client.get(url, params=params, headers=headers)
        if response.status_code == 304:
            return None
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "60"))
            raise RuntimeError(f"rate limited, retry after {retry_after}s")
        response.raise_for_status()

        await asyncio.to_thread(
            self.ctx.poll_state.set,
            self.name,
            response.headers.get("ETag"),
            response.headers.get("Last-Modified"),
        )
        return response.content


class StreamingAdapter(HazardAdapter):
    """Persistent connection with heartbeat and exponential reconnect."""

    async def run(self) -> None:
        backoff = 1.0
        max_backoff = float(getattr(self.settings, "reconnect_max_seconds", 60.0))
        while True:
            try:
                await self.connect_and_consume()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("%s stream dropped: %s", self.name, exc)
                await asyncio.to_thread(self.ctx.health.record_error, self.name, str(exc))
                await asyncio.to_thread(self.ctx.health.set_state, self.name, "DISCONNECTED")
                await asyncio.sleep(backoff * random.uniform(0.8, 1.2))
                backoff = min(backoff * 2, max_backoff)

    @abc.abstractmethod
    async def connect_and_consume(self) -> None: ...

    @abc.abstractmethod
    async def backfill(self, client: httpx.AsyncClient) -> int:
        """Close the gap created while the stream was down."""


async def stream_lines(raw: bytes) -> AsyncIterator[str]:
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if line.strip():
            yield line
