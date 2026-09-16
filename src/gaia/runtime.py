"""Application runtime.

Owns the database, the pipeline, and the adapter tasks. One instance per
process; the API reads from it and the ingestion loops write through it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from .config import Settings
from .config import settings as default_settings
from .db import Database, init_db
from .domain.enums import ProviderHealth
from .engine.bus import EventBus
from .engine.pipeline import Pipeline
from .providers import ADAPTERS, AdapterContext, seed_catalogue
from .store import (
    ObservationRepo,
    PollStateRepo,
    ProviderHealthRepo,
    RawStore,
    VolcanoRepo,
)
from .store.secrets import SecretStore, mask

log = logging.getLogger(__name__)

MANUAL_POLL_MIN_SECONDS = 30.0
FIRMS_KEY_SECRET = "firms_map_key"
OPENSKY_CLIENT_ID_SECRET = "opensky_client_id"
OPENSKY_CLIENT_SECRET_SECRET = "opensky_client_secret"
OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)
# OpenSky's daily credit quota, reset at UTC midnight: 10x higher once authenticated.
OPENSKY_ANONYMOUS_DAILY_CREDITS = 400
OPENSKY_AUTHENTICATED_DAILY_CREDITS = 4000


class Runtime:
    def __init__(self, settings: Settings | None = None, bus: EventBus | None = None) -> None:
        self.settings = settings or default_settings
        self.bus = bus or EventBus()
        self.settings.ensure_dirs()

        self.db: Database = init_db(self.settings.db_path)
        self.raw = RawStore(self.settings.data_dir)
        self.observations = ObservationRepo(self.db)
        self.health = ProviderHealthRepo(self.db)
        self.poll_state = PollStateRepo(self.db)
        self.volcanoes = VolcanoRepo(self.db)
        self.pipeline = Pipeline(self.db, self.settings, self.bus)

        self._tasks: list[asyncio.Task] = []
        self._adapters: list = []
        self._manual_poll_at: dict[str, float] = {}

        self.secrets = SecretStore(self.settings.data_dir / "secrets.json")
        self._apply_stored_secrets()
        self._opensky_token: str | None = None
        self._opensky_token_expiry: float = 0.0
        self._opensky_credits_used = 0
        self._opensky_credits_day = datetime.now(UTC).date()

    def _apply_stored_secrets(self) -> None:
        """An environment variable is an explicit override, so it wins."""
        firms = self.settings.providers.firms
        stored = self.secrets.get(FIRMS_KEY_SECRET)
        if stored and not firms.map_key:
            firms.map_key = stored
            firms.enabled = True

        opensky = self.settings.opensky
        stored_id = self.secrets.get(OPENSKY_CLIENT_ID_SECRET)
        stored_secret = self.secrets.get(OPENSKY_CLIENT_SECRET_SECRET)
        if stored_id and not opensky.client_id:
            opensky.client_id = stored_id
        if stored_secret and not opensky.client_secret:
            opensky.client_secret = stored_secret

    def refresh(self, provider: str | None = None) -> list[dict[str, Any]]:
        """Ask adapters to poll now.

        Rate limited per provider: the upstream feeds are public goods, and a
        button that can be held down is a way to get blocked by them.
        """
        results: list[dict[str, Any]] = []
        now = time.monotonic()

        for adapter in self._adapters:
            if provider and adapter.name != provider:
                continue

            last = self._manual_poll_at.get(adapter.name)
            if last is not None and now - last < MANUAL_POLL_MIN_SECONDS:
                results.append(
                    {
                        "provider": adapter.name,
                        "status": "COOLING_DOWN",
                        "retryAfterSeconds": round(MANUAL_POLL_MIN_SECONDS - (now - last), 1),
                    }
                )
                continue

            if not adapter.request_poll():
                results.append({"provider": adapter.name, "status": "NOT_APPLICABLE"})
                continue

            self._manual_poll_at[adapter.name] = now
            results.append({"provider": adapter.name, "status": "REQUESTED"})

        return results

    def seed(self) -> int:
        """Populate the volcano catalogue if it is empty."""
        if self.volcanoes.count() > 0:
            return 0
        catalogue = seed_catalogue()
        self.volcanoes.upsert_many(catalogue)
        return len(catalogue)

    def _context(self) -> AdapterContext:
        return AdapterContext(
            raw_store=self.raw,
            observations=self.observations,
            health=self.health,
            poll_state=self.poll_state,
            on_observation=self.pipeline.handle_observation,
        )

    def build_adapters(self) -> list:
        context = self._context()

        adapters = []
        was_disabled = {
            row["provider"]
            for row in self.health.all()
            if row["state"] == ProviderHealth.DISABLED.value
        }
        for key, adapter_class in ADAPTERS.items():
            provider_settings = getattr(self.settings.providers, key)
            if not provider_settings.enabled:
                self.health.set_state(adapter_class.name, ProviderHealth.DISABLED.value)
                continue
            # A provider switched back on must stop advertising itself as off.
            if adapter_class.name in was_disabled:
                self.health.set_state(adapter_class.name, ProviderHealth.DISCONNECTED.value)
            adapters.append(adapter_class(context, provider_settings))
        return adapters

    def firms_key_status(self) -> dict[str, Any]:
        firms = self.settings.providers.firms
        return {
            "configured": bool(firms.map_key),
            "hint": mask(firms.map_key) if firms.map_key else None,
            "fromEnvironment": bool(firms.map_key) and not self.secrets.get(FIRMS_KEY_SECRET),
            "enabled": firms.enabled,
        }

    async def set_firms_key(self, map_key: str) -> dict[str, Any]:
        """Store the key and bring the adapter up without a restart."""
        self.secrets.set(FIRMS_KEY_SECRET, map_key)
        firms = self.settings.providers.firms
        firms.map_key = map_key
        firms.enabled = True

        if not any(adapter.name == "FIRMS" for adapter in self._adapters):
            adapter = ADAPTERS["firms"](self._context(), firms)
            self._adapters.append(adapter)
            # Clear the DISABLED marker left by startup, when there was no key.
            self.health.set_state(adapter.name, ProviderHealth.DISCONNECTED.value)
            self._tasks.append(
                asyncio.create_task(adapter.run(), name=f"ingest-{adapter.name}")
            )
        return self.firms_key_status()

    async def clear_firms_key(self) -> dict[str, Any]:
        self.secrets.clear(FIRMS_KEY_SECRET)
        firms = self.settings.providers.firms
        firms.map_key = ""
        firms.enabled = False
        for task in [t for t in self._tasks if t.get_name() == "ingest-FIRMS"]:
            task.cancel()
            self._tasks.remove(task)
        self._adapters = [a for a in self._adapters if a.name != "FIRMS"]
        self.health.set_state("FIRMS", ProviderHealth.DISABLED.value)
        return self.firms_key_status()

    def opensky_status(self) -> dict[str, Any]:
        opensky = self.settings.opensky
        configured = bool(opensky.client_id and opensky.client_secret)
        return {
            "configured": configured,
            "hint": mask(opensky.client_id) if opensky.client_id else None,
            "fromEnvironment": configured and not self.secrets.get(OPENSKY_CLIENT_ID_SECRET),
        }

    def set_opensky_credentials(self, client_id: str, client_secret: str) -> dict[str, Any]:
        self.secrets.set(OPENSKY_CLIENT_ID_SECRET, client_id)
        self.secrets.set(OPENSKY_CLIENT_SECRET_SECRET, client_secret)
        self.settings.opensky.client_id = client_id
        self.settings.opensky.client_secret = client_secret
        self._opensky_token = None  # old token was minted for the previous credentials
        return self.opensky_status()

    def clear_opensky_credentials(self) -> dict[str, Any]:
        self.secrets.clear(OPENSKY_CLIENT_ID_SECRET)
        self.secrets.clear(OPENSKY_CLIENT_SECRET_SECRET)
        self.settings.opensky.client_id = ""
        self.settings.opensky.client_secret = ""
        self._opensky_token = None
        return self.opensky_status()

    def opensky_register_call(self, credits: int) -> bool:
        """Declines a call once the shared account's daily credit budget is spent.

        Every browser tab polling flights draws on the same account, so this
        is tracked globally rather than per-request.
        """
        today = datetime.now(UTC).date()
        if today != self._opensky_credits_day:
            self._opensky_credits_day = today
            self._opensky_credits_used = 0

        opensky = self.settings.opensky
        budget = (
            OPENSKY_AUTHENTICATED_DAILY_CREDITS
            if opensky.client_id and opensky.client_secret
            else OPENSKY_ANONYMOUS_DAILY_CREDITS
        )
        if self._opensky_credits_used + credits > budget:
            return False
        self._opensky_credits_used += credits
        return True

    async def opensky_bearer_token(self) -> str | None:
        """Cached OAuth2 client-credentials token; None means use anonymous access."""
        opensky = self.settings.opensky
        if not (opensky.client_id and opensky.client_secret):
            return None
        if self._opensky_token and time.monotonic() < self._opensky_token_expiry:
            return self._opensky_token

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    OPENSKY_TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": opensky.client_id,
                        "client_secret": opensky.client_secret,
                    },
                )
            except httpx.HTTPError as exc:
                raise RuntimeError(f"OpenSky auth request failed: {exc}") from exc

        if response.status_code != 200:
            raise RuntimeError(f"OpenSky auth returned {response.status_code}")

        body = response.json()
        self._opensky_token = body["access_token"]
        # Refresh a bit early rather than racing the server's own expiry.
        self._opensky_token_expiry = time.monotonic() + body.get("expires_in", 1800) - 30
        return self._opensky_token

    async def start_ingestion(self) -> None:
        if not self.settings.ingest_enabled:
            log.info("ingestion disabled by configuration")
            return

        self._adapters = self.build_adapters()
        for adapter in self._adapters:
            task = asyncio.create_task(adapter.run(), name=f"ingest-{adapter.name}")
            self._tasks.append(task)
        log.info("started %d ingestion adapters", len(self._tasks))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def replay(self, provider: str | None = None) -> dict[str, int]:
        """Rebuild canonical events from stored raw payloads.

        Notification side effects are suppressed: replay reconstructs history,
        it does not re-alert. Spec section 6.3.
        """
        adapters = {a.name: a for a in (self._adapters or self.build_adapters())}
        counts = {"payloads": 0, "observations": 0}

        self.bus.replay_mode = True
        try:
            for key in self.raw.iter_keys(provider):
                parts = key.split("/")
                if len(parts) < 2:
                    continue
                adapter = adapters.get(parts[1])
                if adapter is None:
                    continue

                payload = self.raw.get(key)
                if payload is None:
                    continue

                counts["payloads"] += 1
                counts["observations"] += await adapter.ingest(payload, source_hint="replay")
        finally:
            self.bus.replay_mode = False
        return counts

    def status(self) -> dict:
        from .store import EventRepo

        return {
            "events": EventRepo(self.db).count(),
            "observations": self.observations.count(),
            "volcanoes": self.volcanoes.count(),
            "providers": self.health.all(),
            "dataDir": str(self.settings.data_dir),
        }

    def close(self) -> None:
        self.db.close()
