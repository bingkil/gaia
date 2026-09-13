"""Realtime gateway.

Clients reconnect with the last sequence they saw. If the gap cannot be
replayed from the in-memory backlog the client is told to resynchronise
rather than being silently left with a hole in its state. Spec section 15.4.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, Query, WebSocket

from ..db import to_iso, utcnow
from ..engine.bus import EventBus

log = logging.getLogger(__name__)
router = APIRouter()

HEARTBEAT_SECONDS = 20.0


@router.websocket("/v1/realtime")
async def realtime(websocket: WebSocket, since: int | None = Query(default=None)) -> None:
    await websocket.accept()
    bus: EventBus = websocket.app.state.runtime.bus

    resync_required = since is not None and not bus.has_replay_from(since)
    queue = bus.subscribe(since=None if resync_required else since)

    await websocket.send_json(
        {
            "type": "hello",
            "sequence": bus.sequence,
            "resyncRequired": resync_required,
            "serverTime": to_iso(utcnow()),
        }
    )

    async def pump() -> None:
        """Forward bus messages, emitting a heartbeat during quiet periods."""
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                await websocket.send_json(
                    {
                        "type": "heartbeat",
                        "sequence": bus.sequence,
                        "serverTime": to_iso(utcnow()),
                    }
                )
                continue

            await websocket.send_json(
                {
                    "type": message.subject,
                    "sequence": message.sequence,
                    "payload": message.payload,
                }
            )

    pump_task = asyncio.create_task(pump())
    try:
        # The client sends nothing meaningful; reading is how we notice a close.
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    except Exception:
        log.debug("realtime socket closed", exc_info=True)
    finally:
        pump_task.cancel()
        with contextlib.suppress(BaseException):
            await pump_task
        bus.unsubscribe(queue)
