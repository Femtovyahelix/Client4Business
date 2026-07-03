from __future__ import annotations

from typing import Any
from uuid import UUID

from approval_service.infrastructure.database.models.audit_log import AuditLogModel
from approval_service.infrastructure.repositories.audit_repo import AuditRepository


class AuditService:
    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    async def log(
        self,
        *,
        workspace_id: UUID,
        entity_type: str,
        entity_id: UUID,
        action: str,
        actor_id: UUID | None = None,
        old_state: dict[str, Any] | None = None,
        new_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry = AuditLogModel(
            workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            old_state=old_state,
            new_state=new_state,
            metadata_=metadata or {},
        )
        await self._repo.create(entry)

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
        return await self._repo.list_entries(
            workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            limit=limit,
            offset=offset,
        )
