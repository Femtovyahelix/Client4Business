from __future__ import annotations

import datetime
from uuid import uuid4

import pytest

from approval_service.domain.exceptions import (
    DuplicateDecisionError,
    InvalidStateTransitionError,
    SelfApprovalError,
    StepNotActiveError,
)
from approval_service.domain.models.approval_request import ApprovalRequest
from approval_service.domain.models.approval_step import ApprovalStep, Decision
from approval_service.domain.models.enums import (
    ActionType,
    RequestStatus,
    StepStatus,
)

NOW = datetime.datetime.now(datetime.UTC)


def _make_step(
    order: int = 1,
    status: StepStatus = StepStatus.ACTIVE,
    required_count: int = 1,
    current_count: int = 0,
    request_id: uuid4 | None = None,
    workspace_id: uuid4 | None = None,
) -> ApprovalStep:
    return ApprovalStep(
        id=uuid4(),
        request_id=request_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        step_order=order,
        approver_role="manager",
        required_count=required_count,
        current_count=current_count,
        status=status,
    )


def _make_request_with_active_step(
    required_count: int = 1,
    num_steps: int = 1,
) -> tuple[ApprovalRequest, list[ApprovalStep]]:
    ws_id = uuid4()
    req_id = uuid4()
    requester_id = uuid4()
    steps = []
    for i in range(1, num_steps + 1):
        s = _make_step(
            order=i,
            status=StepStatus.ACTIVE if i == 1 else StepStatus.PENDING,
            required_count=required_count,
            request_id=req_id,
            workspace_id=ws_id,
        )
        steps.append(s)
    req = ApprovalRequest(
        id=req_id,
        workspace_id=ws_id,
        rule_id=uuid4(),
        external_resource_id="RES-001",
        resource_type="invoice",
        title="Test",
        payload={},
        requester_id=requester_id,
        status=RequestStatus.IN_REVIEW,
        steps=steps,
    )
    return req, steps


def _make_decision(
    step_id: uuid4 | None = None,
    workspace_id: uuid4 | None = None,
    actor_id: uuid4 | None = None,
    action: ActionType = ActionType.APPROVE,
) -> Decision:
    return Decision(
        id=uuid4(),
        step_id=step_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        actor_id=actor_id or uuid4(),
        action=action,
        comment="",
        created_at=NOW,
    )


class TestStepApproval:
    def test_step_approve_increments_count(self) -> None:
        step = _make_step(required_count=2)
        decision = _make_decision(step_id=step.id, workspace_id=step.workspace_id)
        step.record_decision(decision, NOW)
        assert step.current_count == 1
        assert step.status == StepStatus.ACTIVE

    def test_step_completes_when_threshold_met(self) -> None:
        step = _make_step(required_count=1)
        decision = _make_decision(step_id=step.id, workspace_id=step.workspace_id)
        step.record_decision(decision, NOW)
        assert step.current_count == 1
        assert step.status == StepStatus.APPROVED
        assert step.completed_at is not None

    def test_step_rejects_entire_request(self) -> None:
        req, steps = _make_request_with_active_step()
        actor = uuid4()
        decision = _make_decision(
            step_id=steps[0].id,
            workspace_id=req.workspace_id,
            actor_id=actor,
            action=ActionType.REJECT,
        )
        result = req.record_decision(decision, NOW)
        assert req.status == RequestStatus.REJECTED
        assert result == RequestStatus.IN_REVIEW

    def test_self_approval_rejected(self) -> None:
        req, steps = _make_request_with_active_step()
        decision = _make_decision(
            step_id=steps[0].id,
            workspace_id=req.workspace_id,
            actor_id=req.requester_id,
        )
        with pytest.raises(SelfApprovalError):
            req.record_decision(decision, NOW)

    def test_duplicate_decision_rejected(self) -> None:
        step = _make_step(required_count=3)
        actor = uuid4()
        d1 = _make_decision(
            step_id=step.id,
            workspace_id=step.workspace_id,
            actor_id=actor,
        )
        step.record_decision(d1, NOW)
        d2 = _make_decision(
            step_id=step.id,
            workspace_id=step.workspace_id,
            actor_id=actor,
        )
        with pytest.raises(DuplicateDecisionError):
            step.record_decision(d2, NOW)

    def test_decision_on_inactive_step_rejected(self) -> None:
        step = _make_step(status=StepStatus.PENDING)
        decision = _make_decision(step_id=step.id, workspace_id=step.workspace_id)
        with pytest.raises(StepNotActiveError):
            step.record_decision(decision, NOW)


class TestMultiStepApproval:
    def test_full_approval_flow_multi_step(self) -> None:
        req, steps = _make_request_with_active_step(num_steps=2)
        actor1 = uuid4()
        d1 = _make_decision(
            step_id=steps[0].id,
            workspace_id=req.workspace_id,
            actor_id=actor1,
        )
        result1 = req.record_decision(d1, NOW)
        assert result1 is None
        assert steps[0].status == StepStatus.APPROVED
        assert steps[1].status == StepStatus.ACTIVE

        actor2 = uuid4()
        d2 = _make_decision(
            step_id=steps[1].id,
            workspace_id=req.workspace_id,
            actor_id=actor2,
        )
        result2 = req.record_decision(d2, NOW)
        assert result2 == RequestStatus.IN_REVIEW
        assert req.status == RequestStatus.APPROVED

    def test_reject_at_second_step(self) -> None:
        req, steps = _make_request_with_active_step(num_steps=2)
        actor1 = uuid4()
        d1 = _make_decision(
            step_id=steps[0].id,
            workspace_id=req.workspace_id,
            actor_id=actor1,
        )
        req.record_decision(d1, NOW)
        assert steps[1].status == StepStatus.ACTIVE

        actor2 = uuid4()
        d2 = _make_decision(
            step_id=steps[1].id,
            workspace_id=req.workspace_id,
            actor_id=actor2,
            action=ActionType.REJECT,
        )
        result = req.record_decision(d2, NOW)
        assert req.status == RequestStatus.REJECTED
        assert result == RequestStatus.IN_REVIEW

    def test_no_active_step_raises(self) -> None:
        req = ApprovalRequest(
            id=uuid4(),
            workspace_id=uuid4(),
            rule_id=uuid4(),
            external_resource_id="RES-001",
            resource_type="invoice",
            title="Test",
            payload={},
            requester_id=uuid4(),
            status=RequestStatus.IN_REVIEW,
            steps=[],
        )
        decision = _make_decision()
        with pytest.raises(InvalidStateTransitionError):
            req.record_decision(decision, NOW)
