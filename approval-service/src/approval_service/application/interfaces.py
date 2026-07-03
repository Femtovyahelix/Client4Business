from __future__ import annotations

import abc
from typing import Any
from uuid import UUID

from approval_service.domain.events import DomainEvent


class EventPublisher(abc.ABC):
    @abc.abstractmethod
    async def publish(self, event: DomainEvent) -> None: ...


class OutboxWriter(abc.ABC):
    @abc.abstractmethod
    async def write(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        workspace_id: UUID,
        payload: dict[str, Any],
    ) -> None: ...
