from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from approval_service.api.middleware.workspace import get_workspace_id
from approval_service.api.v1.response import build_response_meta
from approval_service.api.v1.schemas.common import (
    ListResponse,
    PaginationInfo,
    SingleResponse,
)
from approval_service.api.v1.schemas.decisions import CreateDecisionBody
from approval_service.api.v1.schemas.requests import DecisionResponse, RequestResponse
from approval_service.application.dto import CreateDecisionDTO
from approval_service.application.services.approval_service import ApprovalService
from approval_service.dependencies import get_approval_service

router = APIRouter(prefix="/requests/{request_id}/decisions", tags=["decisions"])


@router.post("", status_code=201)
async def create_decision(
    request: Request,
    request_id: UUID,
    body: CreateDecisionBody,
    workspace_id: UUID = Depends(get_workspace_id),
    service: ApprovalService = Depends(get_approval_service),
) -> SingleResponse[RequestResponse]:
    dto = CreateDecisionDTO(
        workspace_id=workspace_id,
        request_id=request_id,
        actor_id=body.actor_id,
        action=body.action,
        comment=body.comment,
    )
    model = await service.make_decision(dto)
    return SingleResponse(
        data=RequestResponse.model_validate(model),
        meta=build_response_meta(request),
    )


@router.get("")
async def list_decisions(
    request: Request,
    request_id: UUID,
    workspace_id: UUID = Depends(get_workspace_id),
    service: ApprovalService = Depends(get_approval_service),
) -> ListResponse[DecisionResponse]:
    decisions = await service.get_decisions(request_id, workspace_id)
    return ListResponse(
        data=[DecisionResponse.model_validate(d) for d in decisions],
        meta=build_response_meta(request),
        pagination=PaginationInfo(
            total=len(decisions),
            limit=len(decisions),
            offset=0,
            has_more=False,
        ),
    )
