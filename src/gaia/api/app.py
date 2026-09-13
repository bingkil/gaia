"""FastAPI application.

One process serves the API, the realtime socket, the ingestion loops, and the
built frontend.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..config import Settings
from ..config import settings as default_settings
from ..runtime import Runtime
from . import realtime, routes

log = logging.getLogger(__name__)

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app(settings: Settings | None = None, start_ingestion: bool = True) -> FastAPI:
    settings = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = Runtime(settings)
        seeded = runtime.seed()
        if seeded:
            log.info("seeded %d volcanoes", seeded)

        app.state.runtime = runtime
        if start_ingestion:
            await runtime.start_ingestion()
        try:
            yield
        finally:
            await runtime.stop()
            runtime.close()

    app = FastAPI(
        title="GAIA",
        description="Geohazard Awareness, Impact & Alerting",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(routes.router)
    app.include_router(realtime.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Process liveness only. Data freshness lives at /v1/provider-health."""
        return {"status": "ok"}

    if WEB_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            candidate = WEB_DIST / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(WEB_DIST / "index.html")

    return app
