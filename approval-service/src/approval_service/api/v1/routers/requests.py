from __future__ import annotations

import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from approval_service.api.middleware.workspace import get_workspace_id
from approval_service.api.v1.schemas.common import (
    ListResponse,
    PaginationInfo,
    ResponseMeta,
    SingleResponse,
)
from approval_service.api.v1.schemas.requests import (
    CancelRequestBody,
    CreateRequestBody,
    RequestResponse,
)
from approval_service.application.dto import CreateRequestDTO
from approval_service.application.services.approval_service import ApprovalService
from approval_service.dependencies import get_approval_service

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", status_code=201)
async def create_request(
    body: CreateRequestBody,
    workspace_id: UUID = Depends(get_workspace_id),
    service: ApprovalService = Depends(get_approval_service),
) -> SingleResponse[RequestResponse]:
    dto = CreateRequestDTO(
        workspace_id=workspace_id,
        external_resource_id=body.external_resource_id,
        resource_type=body.resource_type,
        title=body.title,
        payload=body.payload,
        requester_id=body.requester_id,
        rule_id=body.rule_id,
    )
    model = await service.create_request(dto)
    return SingleResponse(
        data=RequestResponse.model_validate(model),
        meta=ResponseMeta(
            request_id="",
            timestamp=datetime.datetime.now(datetime.UTC),
        ),
    )


@router.get("")
async def list_requests(
    workspace_id: UUID = Depends(get_workspace_id),
    service: ApprovalService = Depends(get_approval_service),
    status: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    requester_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ListResponse[RequestResponse]:
    items, total = await service.list_requests(
        workspace_id,
        status=status,
        resource_type=resource_type,
        requester_id=requester_id,
        limit=limit,
        offset=offset,
    )
    return ListResponse(
        data=[RequestResponse.model_validate(i) for i in items],
        meta=ResponseMeta(
            request_id="",
            timestamp=datetime.datetime.now(datetime.UTC),
        ),
        pagination=PaginationInfo(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


@router.get("/{request_id}")
async def get_request(
    request_id: UUID,
    workspace_id: UUID = Depends(get_workspace_id),
    service: ApprovalService = Depends(get_approval_service),
) -> SingleResponse[RequestResponse]:
    model = await service.get_request(request_id, workspace_id)
    return SingleResponse(
        data=RequestResponse.model_validate(model),
        meta=ResponseMeta(
            request_id="",
            timestamp=datetime.datetime.now(datetime.UTC),
        ),
    )


@router.post("/{request_id}/cancel")
async def cancel_request(
    request_id: UUID,
    body: CancelRequestBody,
    workspace_id: UUID = Depends(get_workspace_id),
    service: ApprovalService = Depends(get_approval_service),
) -> SingleResponse[RequestResponse]:
    model = await service.cancel_request(request_id, workspace_id, body.actor_id)
    return SingleResponse(
        data=RequestResponse.model_validate(model),
        meta=ResponseMeta(
            request_id="",
            timestamp=datetime.datetime.now(datetime.UTC),
        ),
    )
