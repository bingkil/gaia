"""In-process publish/subscribe.

Replaces NATS JetStream for the local-first build. Durability is provided by
SQLite: the append-only observation and revision tables are the real log, so
this bus only needs to fan out live updates and serve a short replay window to
reconnecting clients.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Message:
    sequence: int
    subject: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self, backlog: int = 512) -> None:
        self._subscribers: set[asyncio.Queue[Message]] = set()
        self._backlog: deque[Message] = deque(maxlen=backlog)
        self._sequence = 0
        self._lock = asyncio.Lock()
        # Set during replay so notification side effects can be suppressed.
        self.replay_mode = False

    @property
    def sequence(self) -> int:
        return self._sequence

    async def publish(self, subject: str, payload: dict[str, Any]) -> Message:
        async with self._lock:
            self._sequence += 1
            message = Message(sequence=self._sequence, subject=subject, payload=payload)
            self._backlog.append(message)
            subscribers = list(self._subscribers)

        for queue in subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # A slow client must never stall ingestion; it resynchronises
                # via the REST API after noticing a sequence gap.
                log.warning("subscriber queue full, dropping message %s", message.sequence)
        return message

    def subscribe(self, since: int | None = None) -> asyncio.Queue[Message]:
        queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=256)
        if since is not None:
            for message in self._backlog:
                if message.sequence > since:
                    try:
                        queue.put_nowait(message)
                    except asyncio.QueueFull:
                        break
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Message]) -> None:
        self._subscribers.discard(queue)

    def has_replay_from(self, sequence: int) -> bool:
        """False when the client is too far behind and must refresh state."""
        if sequence > self._sequence:
            # Ahead of us: a different or restarted server. Refresh, do not guess.
            return False
        if not self._backlog:
            return sequence == self._sequence
        return sequence >= self._backlog[0].sequence - 1

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Subjects, mirroring spec section 6.3.
RAW = "raw"
NORMALIZED = "normalized"
EVENT_CREATED = "canonical.event.created"
EVENT_UPDATED = "canonical.event.updated"
EVENT_CANCELLED = "canonical.event.cancelled"
IMPACT_UPDATED = "impact.updated"
NOTIFICATION_CREATED = "notification.created"
PROVIDER_HEALTH = "provider.health"
