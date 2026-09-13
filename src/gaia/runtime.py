"""Application runtime.

Owns the database, the pipeline, and the adapter tasks. One instance per
process; the API reads from it and the ingestion loops write through it.
"""

from __future__ import annotations

import asyncio
import logging

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

log = logging.getLogger(__name__)


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

    def seed(self) -> int:
        """Populate the volcano catalogue if it is empty."""
        if self.volcanoes.count() > 0:
            return 0
        catalogue = seed_catalogue()
        self.volcanoes.upsert_many(catalogue)
        return len(catalogue)

    def build_adapters(self) -> list:
        context = AdapterContext(
            raw_store=self.raw,
            observations=self.observations,
            health=self.health,
            poll_state=self.poll_state,
            on_observation=self.pipeline.handle_observation,
        )

        adapters = []
        for key, adapter_class in ADAPTERS.items():
            provider_settings = getattr(self.settings.providers, key)
            if not provider_settings.enabled:
                self.health.set_state(adapter_class.name, ProviderHealth.DISABLED.value)
                continue
            adapters.append(adapter_class(context, provider_settings))
        return adapters

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
