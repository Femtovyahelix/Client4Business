from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class DomainEvent:
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

    @property
    def event_type(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class RequestCreatedEvent(DomainEvent):
    workspace_id: UUID = field(default_factory=uuid4)
    request_id: UUID = field(default_factory=uuid4)
    resource_type: str = ""
    external_resource_id: str = ""
    requester_id: UUID = field(default_factory=uuid4)

    @property
    def event_type(self) -> str:
        return "approval.request.created"


@dataclass(frozen=True)
class RequestStatusChangedEvent(DomainEvent):
    workspace_id: UUID = field(default_factory=uuid4)
    request_id: UUID = field(default_factory=uuid4)
    old_status: str = ""
    new_status: str = ""

    @property
    def event_type(self) -> str:
        return f"approval.request.{self.new_status}"


@dataclass(frozen=True)
class StepActivatedEvent(DomainEvent):
    workspace_id: UUID = field(default_factory=uuid4)
    request_id: UUID = field(default_factory=uuid4)
    step_id: UUID = field(default_factory=uuid4)
    step_order: int = 0
    approver_role: str = ""

    @property
    def event_type(self) -> str:
        return "approval.step.activated"


@dataclass(frozen=True)
class DecisionMadeEvent(DomainEvent):
    workspace_id: UUID = field(default_factory=uuid4)
    request_id: UUID = field(default_factory=uuid4)
    step_id: UUID = field(default_factory=uuid4)
    actor_id: UUID = field(default_factory=uuid4)
    action: str = ""

    @property
    def event_type(self) -> str:
        return "approval.decision.made"


def event_to_payload(event: DomainEvent) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in event.__dict__.items():
        if key in ("event_id", "timestamp"):
            continue
        if isinstance(value, UUID):
            result[key] = str(value)
        elif isinstance(value, datetime.datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result
