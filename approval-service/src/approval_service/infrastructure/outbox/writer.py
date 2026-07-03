from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from approval_service.application.interfaces import OutboxWriter
from approval_service.infrastructure.database.models.outbox import OutboxModel


class DatabaseOutboxWriter(OutboxWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        workspace_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        entry = OutboxModel(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            workspace_id=workspace_id,
            payload=payload,
        )
        self._session.add(entry)
        await self._session.flush()
