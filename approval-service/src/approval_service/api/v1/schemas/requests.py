from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateRequestBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_resource_id: str = Field(..., min_length=1, max_length=255)
    resource_type: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)
    requester_id: UUID
    rule_id: UUID | None = None


class StepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    step_order: int
    approver_role: str
    required_count: int
    current_count: int
    status: str
    activated_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    created_at: datetime.datetime


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    step_id: UUID
    actor_id: UUID
    action: str
    comment: str
    created_at: datetime.datetime


class RequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    workspace_id: UUID
    rule_id: UUID
    external_resource_id: str
    resource_type: str
    title: str
    payload: dict[str, Any]
    status: str
    requester_id: UUID
    resolved_at: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    steps: list[StepResponse] = []


class CancelRequestBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    actor_id: UUID
