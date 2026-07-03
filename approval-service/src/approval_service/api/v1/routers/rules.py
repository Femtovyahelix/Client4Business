from __future__ import annotations

import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from approval_service.api.middleware.workspace import get_workspace_id
from approval_service.api.v1.schemas.common import (
    ListResponse,
    PaginationInfo,
    ResponseMeta,
    SingleResponse,
)
from approval_service.api.v1.schemas.rules import (
    CreateRuleBody,
    RuleResponse,
    UpdateRuleBody,
)
from approval_service.application.dto import CreateRuleDTO, StepDefinitionDTO, UpdateRuleDTO
from approval_service.application.services.rule_service import RuleService
from approval_service.dependencies import get_rule_service

router = APIRouter(prefix="/rules", tags=["rules"])


@router.post("", status_code=201)
async def create_rule(
    body: CreateRuleBody,
    workspace_id: UUID = Depends(get_workspace_id),
    service: RuleService = Depends(get_rule_service),
) -> SingleResponse[RuleResponse]:
    dto = CreateRuleDTO(
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        resource_type=body.resource_type,
        conditions=body.conditions,
        steps=[
            StepDefinitionDTO(
                order=s.order,
                approver_role=s.approver_role,
                required_count=s.required_count,
            )
            for s in body.steps
        ],
    )
    model = await service.create_rule(dto)
    return SingleResponse(
        data=RuleResponse.model_validate(model),
        meta=ResponseMeta(
            request_id="",
            timestamp=datetime.datetime.now(datetime.UTC),
        ),
    )


@router.get("")
async def list_rules(
    workspace_id: UUID = Depends(get_workspace_id),
    service: RuleService = Depends(get_rule_service),
    resource_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ListResponse[RuleResponse]:
    items, total = await service.list_rules(
        workspace_id,
        resource_type=resource_type,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return ListResponse(
        data=[RuleResponse.model_validate(i) for i in items],
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


@router.get("/{rule_id}")
async def get_rule(
    rule_id: UUID,
    workspace_id: UUID = Depends(get_workspace_id),
    service: RuleService = Depends(get_rule_service),
) -> SingleResponse[RuleResponse]:
    model = await service.get_rule(rule_id, workspace_id)
    return SingleResponse(
        data=RuleResponse.model_validate(model),
        meta=ResponseMeta(
            request_id="",
            timestamp=datetime.datetime.now(datetime.UTC),
        ),
    )


@router.put("/{rule_id}")
async def update_rule(
    rule_id: UUID,
    body: UpdateRuleBody,
    workspace_id: UUID = Depends(get_workspace_id),
    service: RuleService = Depends(get_rule_service),
) -> SingleResponse[RuleResponse]:
    steps = None
    if body.steps is not None:
        steps = [
            StepDefinitionDTO(
                order=s.order,
                approver_role=s.approver_role,
                required_count=s.required_count,
            )
            for s in body.steps
        ]
    dto = UpdateRuleDTO(
        workspace_id=workspace_id,
        rule_id=rule_id,
        name=body.name,
        description=body.description,
        conditions=body.conditions,
        steps=steps,
        is_active=body.is_active,
        version=body.version,
    )
    model = await service.update_rule(dto)
    return SingleResponse(
        data=RuleResponse.model_validate(model),
        meta=ResponseMeta(
            request_id="",
            timestamp=datetime.datetime.now(datetime.UTC),
        ),
    )


@router.delete("/{rule_id}", status_code=204, response_class=Response)
async def delete_rule(
    rule_id: UUID,
    workspace_id: UUID = Depends(get_workspace_id),
    service: RuleService = Depends(get_rule_service),
) -> Response:
    await service.deactivate_rule(rule_id, workspace_id)
    return Response(status_code=204)
