from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from uuid import UUID

from approval_service.domain.exceptions import (
    DuplicateDecisionError,
    StepNotActiveError,
)
from approval_service.domain.models.enums import ActionType, StepStatus


@dataclass
class Decision:
    id: UUID
    step_id: UUID
    workspace_id: UUID
    actor_id: UUID
    action: ActionType
    comment: str
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class ApprovalStep:
    id: UUID
    request_id: UUID
    workspace_id: UUID
    step_order: int
    approver_role: str
    required_count: int
    current_count: int = 0
    status: StepStatus = StepStatus.PENDING
    activated_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    decisions: list[Decision] = field(default_factory=list)

    def activate(self, now: datetime.datetime) -> None:
        self.status = StepStatus.ACTIVE
        self.activated_at = now

    def record_decision(
        self,
        decision: Decision,
        now: datetime.datetime,
    ) -> None:
        if self.status != StepStatus.ACTIVE:
            raise StepNotActiveError(step_id=self.id, current_status=self.status)
        existing_actor_ids = {d.actor_id for d in self.decisions}
        if decision.actor_id in existing_actor_ids:
            raise DuplicateDecisionError(step_id=self.id, actor_id=decision.actor_id)
        self.decisions.append(decision)
        if decision.action == ActionType.REJECT:
            self.status = StepStatus.REJECTED
            self.completed_at = now
            return
        self.current_count += 1
        if self.current_count >= self.required_count:
            self.status = StepStatus.APPROVED
            self.completed_at = now

    @property
    def is_terminal(self) -> bool:
        return self.status in (StepStatus.APPROVED, StepStatus.REJECTED)
