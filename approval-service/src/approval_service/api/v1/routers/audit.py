from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict

from approval_service.api.middleware.workspace import get_workspace_id
from approval_service.api.v1.response import build_response_meta
from approval_service.api.v1.schemas.common import (
    ListResponse,
    PaginationInfo,
)
from approval_service.application.services.audit_service import AuditService
from approval_service.dependencies import get_audit_service

router = APIRouter(prefix="/audit-log", tags=["audit"])


class AuditEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    workspace_id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    actor_id: UUID | None = None
    old_state: dict[str, Any] | None = None
    new_state: dict[str, Any] | None = None
    created_at: datetime.datetime


@router.get("")
async def list_audit_entries(
    request: Request,
    workspace_id: UUID = Depends(get_workspace_id),
    service: AuditService = Depends(get_audit_service),
    entity_type: str | None = Query(default=None),
    entity_id: UUID | None = Query(default=None),
    actor_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ListResponse[AuditEntryResponse]:
    items, total = await service.list_entries(
        workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        limit=limit,
        offset=offset,
    )
    return ListResponse(
        data=[AuditEntryResponse.model_validate(i) for i in items],
        meta=build_response_meta(request),
        pagination=PaginationInfo(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
    )
