from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from approval_service.application.interfaces import EventPublisher
from approval_service.domain.events import DomainEvent
from approval_service.infrastructure.database.models.outbox import OutboxModel

logger = logging.getLogger(__name__)


class LoggingEventPublisher(EventPublisher):
    """Publishes events to structured logs.

    Suitable for development and as a base implementation.
    """

    async def publish(self, event: DomainEvent) -> None:
        logger.info(
            "Publishing event",
            extra={"event_type": event.event_type, "event_id": str(event.event_id)},
        )


class OutboxPoller:
    """Background worker that reads unpublished outbox entries and forwards them.

    Uses SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent polling.
    Failed entries are retried up to ``max_retries`` times before being dead-lettered.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: EventPublisher,
        *,
        batch_size: int = 100,
        poll_interval: float = 5.0,
        max_retries: int = 5,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._max_retries = max_retries
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            processed = await self._poll_batch()
            if not processed:
                await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False

    async def _poll_batch(self) -> bool:
        async with self._session_factory() as session, session.begin():
            stmt = (
                select(OutboxModel)
                .where(
                    OutboxModel.published_at.is_(None),
                    OutboxModel.retry_count < self._max_retries,
                )
                .order_by(OutboxModel.id)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            entries = list(result.scalars().all())

            if not entries:
                return False

            now = datetime.datetime.now(datetime.UTC)
            published_ids: list[int] = []
            failed_ids: list[int] = []

            for entry in entries:
                try:
                    event = self._to_domain_event(entry)
                    await self._publisher.publish(event)
                    published_ids.append(entry.id)
                except Exception:
                    logger.exception(
                        "Failed to publish outbox entry",
                        extra={"outbox_id": entry.id, "event_type": entry.event_type},
                    )
                    failed_ids.append(entry.id)

            if published_ids:
                await session.execute(
                    update(OutboxModel)
                    .where(OutboxModel.id.in_(published_ids))
                    .values(published_at=now)
                )

            if failed_ids:
                await session.execute(
                    update(OutboxModel)
                    .where(OutboxModel.id.in_(failed_ids))
                    .values(retry_count=OutboxModel.retry_count + 1)
                )

            return True

    @staticmethod
    def _to_domain_event(entry: OutboxModel) -> DomainEvent:
        """Reconstruct a DomainEvent from an outbox row, preserving event_type."""
        return _OutboxDomainEvent(
            event_id=entry.aggregate_id,
            timestamp=entry.created_at,
            _event_type=entry.event_type,
        )


@dataclass(frozen=True)
class _OutboxDomainEvent(DomainEvent):
    """Thin wrapper so the publisher receives the original event_type from the outbox row."""

    _event_type: str = ""

    @property
    def event_type(self) -> str:
        return self._event_type
