from __future__ import annotations

import datetime
from uuid import uuid4

import pytest

from approval_service.domain.exceptions import (
    AlreadyResolvedError,
    InvalidStateTransitionError,
)
from approval_service.domain.models.approval_request import ApprovalRequest
from approval_service.domain.models.approval_step import ApprovalStep
from approval_service.domain.models.enums import RequestStatus, StepStatus


def _make_request(
    status: RequestStatus = RequestStatus.PENDING,
    steps: list[ApprovalStep] | None = None,
) -> ApprovalRequest:
    return ApprovalRequest(
        id=uuid4(),
        workspace_id=uuid4(),
        rule_id=uuid4(),
        external_resource_id="RES-001",
        resource_type="invoice",
        title="Test Request",
        payload={},
        requester_id=uuid4(),
        status=status,
        steps=steps or [],
    )


def _make_step(
    order: int = 1,
    status: StepStatus = StepStatus.PENDING,
    required_count: int = 1,
    current_count: int = 0,
) -> ApprovalStep:
    return ApprovalStep(
        id=uuid4(),
        request_id=uuid4(),
        workspace_id=uuid4(),
        step_order=order,
        approver_role="manager",
        required_count=required_count,
        current_count=current_count,
        status=status,
    )


NOW = datetime.datetime.now(datetime.UTC)


class TestFSMTransitions:
    def test_pending_to_in_review(self) -> None:
        step = _make_step()
        req = _make_request(steps=[step])
        old = req.start_review(NOW)
        assert old == RequestStatus.PENDING
        assert req.status == RequestStatus.IN_REVIEW
        assert step.status == StepStatus.ACTIVE

    def test_in_review_to_approved(self) -> None:
        req = _make_request(status=RequestStatus.IN_REVIEW)
        old = req.transition_to(RequestStatus.APPROVED, NOW)
        assert old == RequestStatus.IN_REVIEW
        assert req.status == RequestStatus.APPROVED
        assert req.resolved_at is not None

    def test_in_review_to_rejected(self) -> None:
        req = _make_request(status=RequestStatus.IN_REVIEW)
        old = req.transition_to(RequestStatus.REJECTED, NOW)
        assert old == RequestStatus.IN_REVIEW
        assert req.status == RequestStatus.REJECTED
        assert req.resolved_at is not None

    def test_pending_to_cancelled(self) -> None:
        req = _make_request()
        old = req.cancel(uuid4(), NOW)
        assert old == RequestStatus.PENDING
        assert req.status == RequestStatus.CANCELLED

    def test_in_review_to_cancelled(self) -> None:
        req = _make_request(status=RequestStatus.IN_REVIEW)
        old = req.cancel(uuid4(), NOW)
        assert old == RequestStatus.IN_REVIEW
        assert req.status == RequestStatus.CANCELLED

    def test_approved_is_terminal(self) -> None:
        req = _make_request(status=RequestStatus.APPROVED)
        with pytest.raises(AlreadyResolvedError):
            req.transition_to(RequestStatus.IN_REVIEW, NOW)

    def test_rejected_is_terminal(self) -> None:
        req = _make_request(status=RequestStatus.REJECTED)
        with pytest.raises(AlreadyResolvedError):
            req.transition_to(RequestStatus.PENDING, NOW)

    def test_cancelled_is_terminal(self) -> None:
        req = _make_request(status=RequestStatus.CANCELLED)
        with pytest.raises(AlreadyResolvedError):
            req.transition_to(RequestStatus.PENDING, NOW)

    def test_invalid_transition_raises(self) -> None:
        req = _make_request(status=RequestStatus.PENDING)
        with pytest.raises(InvalidStateTransitionError):
            req.transition_to(RequestStatus.APPROVED, NOW)
