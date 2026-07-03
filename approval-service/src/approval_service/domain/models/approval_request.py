from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from approval_service.domain.exceptions import (
    AlreadyResolvedError,
    InvalidStateTransitionError,
    SelfApprovalError,
)
from approval_service.domain.fsm import ALLOWED_TRANSITIONS
from approval_service.domain.models.approval_step import ApprovalStep, Decision
from approval_service.domain.models.enums import RequestStatus, StepStatus

TERMINAL_STATUSES = frozenset(
    {
        RequestStatus.APPROVED,
        RequestStatus.REJECTED,
        RequestStatus.CANCELLED,
    }
)


@dataclass
class ApprovalRequest:
    id: UUID
    workspace_id: UUID
    rule_id: UUID
    external_resource_id: str
    resource_type: str
    title: str
    payload: dict[str, Any]
    requester_id: UUID
    status: RequestStatus = RequestStatus.PENDING
    resolved_at: datetime.datetime | None = None
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    steps: list[ApprovalStep] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def transition_to(self, target: RequestStatus, now: datetime.datetime) -> RequestStatus:
        if self.is_terminal:
            raise AlreadyResolvedError()
        allowed = ALLOWED_TRANSITIONS.get(self.status, frozenset())
        if target not in allowed:
            raise InvalidStateTransitionError(current=self.status.value, target=target.value)
        old_status = self.status
        self.status = target
        self.updated_at = now
        if target in TERMINAL_STATUSES:
            self.resolved_at = now
        return old_status

    def start_review(self, now: datetime.datetime) -> RequestStatus:
        old = self.transition_to(RequestStatus.IN_REVIEW, now)
        first_step = self._get_step_by_order(1)
        if first_step is not None:
            first_step.activate(now)
        return old

    def cancel(self, actor_id: UUID, now: datetime.datetime) -> RequestStatus:
        return self.transition_to(RequestStatus.CANCELLED, now)

    def record_decision(
        self,
        decision: Decision,
        now: datetime.datetime,
    ) -> RequestStatus | None:
        if decision.actor_id == self.requester_id:
            raise SelfApprovalError()

        active_step = self._get_active_step()
        active_step.record_decision(decision, now)

        if active_step.status == StepStatus.REJECTED:
            old = self.transition_to(RequestStatus.REJECTED, now)
            return old

        if active_step.status == StepStatus.APPROVED:
            next_step = self._get_step_by_order(active_step.step_order + 1)
            if next_step is not None:
                next_step.activate(now)
                return None
            old = self.transition_to(RequestStatus.APPROVED, now)
            return old

        return None

    def _get_active_step(self) -> ApprovalStep:
        for step in self.steps:
            if step.status == StepStatus.ACTIVE:
                return step
        raise InvalidStateTransitionError(
            current=self.status.value,
            target="decision",
        )

    def _get_step_by_order(self, order: int) -> ApprovalStep | None:
        for step in self.steps:
            if step.step_order == order:
                return step
        return None
