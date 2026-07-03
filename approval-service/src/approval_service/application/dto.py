from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CreateRequestDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: UUID
    external_resource_id: str
    resource_type: str
    title: str
    payload: dict[str, Any]
    requester_id: UUID
    rule_id: UUID | None = None


class CreateDecisionDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: UUID
    request_id: UUID
    actor_id: UUID
    action: str
    comment: str = ""


class CreateRuleDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: UUID
    name: str
    description: str
    resource_type: str
    conditions: dict[str, Any]
    steps: list[StepDefinitionDTO]


class StepDefinitionDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    order: int
    approver_role: str
    required_count: int = 1


class UpdateRuleDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: UUID
    rule_id: UUID
    name: str | None = None
    description: str | None = None
    conditions: dict[str, Any] | None = None
    steps: list[StepDefinitionDTO] | None = None
    is_active: bool | None = None
    version: int


CreateRuleDTO.model_rebuild()
UpdateRuleDTO.model_rebuild()
