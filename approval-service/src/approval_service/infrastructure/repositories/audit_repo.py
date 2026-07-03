from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from approval_service.infrastructure.database.models.audit_log import AuditLogModel


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, model: AuditLogModel) -> AuditLogModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def list_entries(
        self,
        workspace_id: UUID,
        *,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        actor_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[AuditLogModel], int]:
        base = select(AuditLogModel).where(AuditLogModel.workspace_id == workspace_id)
        if entity_type is not None:
            base = base.where(AuditLogModel.entity_type == entity_type)
        if entity_id is not None:
            base = base.where(AuditLogModel.entity_id == entity_id)
        if actor_id is not None:
            base = base.where(AuditLogModel.actor_id == actor_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        items_stmt = base.order_by(AuditLogModel.created_at.desc()).limit(limit).offset(offset)
        items_result = await self._session.execute(items_stmt)
        items = list(items_result.scalars().all())
        return items, total
