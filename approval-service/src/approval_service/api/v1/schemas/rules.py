from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StepDefinitionBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    order: int = Field(..., ge=1)
    approver_role: str = Field(..., min_length=1, max_length=100)
    required_count: int = Field(default=1, ge=1)


class CreateRuleBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    resource_type: str = Field(..., min_length=1, max_length=100)
    conditions: dict[str, Any] = Field(default_factory=dict)
    steps: list[StepDefinitionBody] = Field(..., min_length=1)


class UpdateRuleBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    conditions: dict[str, Any] | None = None
    steps: list[StepDefinitionBody] | None = None
    is_active: bool | None = None
    version: int = Field(..., ge=1)


class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str
    resource_type: str
    conditions: dict[str, Any]
    steps: list[dict[str, Any]]
    is_active: bool
    version: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
