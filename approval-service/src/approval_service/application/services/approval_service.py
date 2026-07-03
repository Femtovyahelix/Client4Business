from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from approval_service.application.dto import CreateDecisionDTO, CreateRequestDTO
from approval_service.application.interfaces import OutboxWriter
from approval_service.application.services.audit_service import AuditService
from approval_service.common.clock import Clock
from approval_service.domain.events import (
    DecisionMadeEvent,
    RequestCreatedEvent,
    RequestStatusChangedEvent,
    StepActivatedEvent,
    event_to_payload,
)
from approval_service.domain.exceptions import (
    DuplicateActiveRequestError,
    RequestNotFoundError,
    RuleNotFoundError,
)
from approval_service.domain.models.approval_request import ApprovalRequest
from approval_service.domain.models.approval_step import ApprovalStep, Decision
from approval_service.domain.models.enums import (
    ActionType,
    AuditAction,
    EntityType,
    RequestStatus,
    StepStatus,
)
from approval_service.infrastructure.database.models.approval_decision import (
    ApprovalDecisionModel,
)
from approval_service.infrastructure.database.models.approval_request import (
    ApprovalRequestModel,
)
from approval_service.infrastructure.database.models.approval_step import ApprovalStepModel
from approval_service.infrastructure.repositories.approval_repo import ApprovalRepository
from approval_service.infrastructure.repositories.rule_repo import RuleRepository


class ApprovalService:
    def __init__(
        self,
        approval_repo: ApprovalRepository,
        rule_repo: RuleRepository,
        audit: AuditService,
        outbox: OutboxWriter,
        clock: Clock,
    ) -> None:
        self._approval_repo = approval_repo
        self._rule_repo = rule_repo
        self._audit = audit
        self._outbox = outbox
        self._clock = clock

    async def create_request(self, dto: CreateRequestDTO) -> ApprovalRequestModel:
        if dto.rule_id is not None:
            rule = await self._rule_repo.get_by_id(dto.rule_id, dto.workspace_id)
        else:
            rule = await self._rule_repo.find_matching_rule(dto.workspace_id, dto.resource_type)
        if rule is None:
            raise RuleNotFoundError()

        now = self._clock.now()
        request_id = uuid4()

        request_model = ApprovalRequestModel(
            id=request_id,
            workspace_id=dto.workspace_id,
            rule_id=rule.id,
            external_resource_id=dto.external_resource_id,
            resource_type=dto.resource_type,
            title=dto.title,
            payload=dto.payload,
            status=RequestStatus.PENDING.value,
            requester_id=dto.requester_id,
        )

        try:
            request_model = await self._approval_repo.create_request(request_model)
        except Exception as exc:
            exc_str = str(exc).lower()
            if "ix_approval_requests_unique_active" in exc_str or (
                "unique constraint failed" in exc_str and "external_resource_id" in exc_str
            ):
                raise DuplicateActiveRequestError() from exc
            raise

        step_definitions: list[dict[str, Any]] = rule.steps
        step_models: list[ApprovalStepModel] = []
        for step_def in step_definitions:
            step_id = uuid4()
            step_model = ApprovalStepModel(
                id=step_id,
                request_id=request_id,
                workspace_id=dto.workspace_id,
                step_order=step_def["order"],
                approver_role=step_def["approver_role"],
                required_count=step_def.get("required_count", 1),
                current_count=0,
                status=StepStatus.PENDING.value,
            )
            step_model = await self._approval_repo.create_step(step_model)
            step_models.append(step_model)

        first_step = next((s for s in step_models if s.step_order == 1), None)
        if first_step is not None:
            first_step.status = StepStatus.ACTIVE.value
            first_step.activated_at = now

        request_model.status = RequestStatus.IN_REVIEW.value
        request_model.updated_at = now  # type: ignore[assignment]
        await self._approval_repo.update_request(request_model)

        await self._audit.log(
            workspace_id=dto.workspace_id,
            entity_type=EntityType.APPROVAL_REQUEST,
            entity_id=request_id,
            action=AuditAction.CREATED,
            actor_id=dto.requester_id,
            new_state={
                "status": RequestStatus.IN_REVIEW.value,
                "resource_type": dto.resource_type,
                "external_resource_id": dto.external_resource_id,
                "title": dto.title,
            },
        )

        created_event = RequestCreatedEvent(
            workspace_id=dto.workspace_id,
            request_id=request_id,
            resource_type=dto.resource_type,
            external_resource_id=dto.external_resource_id,
            requester_id=dto.requester_id,
        )
        await self._outbox.write(
            event_type=created_event.event_type,
            aggregate_type="approval_request",
            aggregate_id=request_id,
            workspace_id=dto.workspace_id,
            payload=event_to_payload(created_event),
        )

        if first_step is not None:
            step_event = StepActivatedEvent(
                workspace_id=dto.workspace_id,
                request_id=request_id,
                step_id=first_step.id,
                step_order=first_step.step_order,
                approver_role=first_step.approver_role,
            )
            await self._outbox.write(
                event_type=step_event.event_type,
                aggregate_type="approval_request",
                aggregate_id=request_id,
                workspace_id=dto.workspace_id,
                payload=event_to_payload(step_event),
            )

        request_model = await self._approval_repo.get_request_by_id(request_id, dto.workspace_id)
        assert request_model is not None
        return request_model

    async def get_request(self, request_id: UUID, workspace_id: UUID) -> ApprovalRequestModel:
        model = await self._approval_repo.get_request_by_id(request_id, workspace_id)
        if model is None:
            raise RequestNotFoundError()
        return model

    async def list_requests(
        self,
        workspace_id: UUID,
        *,
        status: str | None = None,
        resource_type: str | None = None,
        requester_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ApprovalRequestModel], int]:
        return await self._approval_repo.list_requests(
            workspace_id,
            status=status,
            resource_type=resource_type,
            requester_id=requester_id,
            limit=limit,
            offset=offset,
        )

    async def cancel_request(
        self, request_id: UUID, workspace_id: UUID, actor_id: UUID
    ) -> ApprovalRequestModel:
        model = await self._approval_repo.get_request_by_id(request_id, workspace_id)
        if model is None:
            raise RequestNotFoundError()

        domain_request = self._to_domain_request(model)
        old_status = domain_request.cancel(actor_id, self._clock.now())

        now = self._clock.now()
        model.status = RequestStatus.CANCELLED.value
        model.resolved_at = now
        model.updated_at = now  # type: ignore[assignment]
        await self._approval_repo.update_request(model)

        await self._audit.log(
            workspace_id=workspace_id,
            entity_type=EntityType.APPROVAL_REQUEST,
            entity_id=request_id,
            action=AuditAction.CANCELLED,
            actor_id=actor_id,
            old_state={"status": old_status},
            new_state={"status": RequestStatus.CANCELLED.value},
        )

        event = RequestStatusChangedEvent(
            workspace_id=workspace_id,
            request_id=request_id,
            old_status=old_status,
            new_status=RequestStatus.CANCELLED.value,
        )
        await self._outbox.write(
            event_type=event.event_type,
            aggregate_type="approval_request",
            aggregate_id=request_id,
            workspace_id=workspace_id,
            payload=event_to_payload(event),
        )

        model = await self._approval_repo.get_request_by_id(request_id, workspace_id)
        assert model is not None
        return model

    async def make_decision(self, dto: CreateDecisionDTO) -> ApprovalRequestModel:
        model = await self._approval_repo.get_request_by_id(dto.request_id, dto.workspace_id)
        if model is None:
            raise RequestNotFoundError()

        domain_request = self._to_domain_request(model)

        decision_id = uuid4()
        now = self._clock.now()
        action_type = ActionType(dto.action)
        domain_decision = Decision(
            id=decision_id,
            step_id=uuid4(),
            workspace_id=dto.workspace_id,
            actor_id=dto.actor_id,
            action=action_type,
            comment=dto.comment,
            created_at=now,
        )

        active_step = domain_request._get_active_step()
        domain_decision.step_id = active_step.id

        old_request_status = domain_request.status.value
        status_change = domain_request.record_decision(domain_decision, now)

        decision_model = ApprovalDecisionModel(
            id=decision_id,
            step_id=active_step.id,
            workspace_id=dto.workspace_id,
            actor_id=dto.actor_id,
            action=dto.action,
            comment=dto.comment,
        )
        await self._approval_repo.create_decision(decision_model)

        db_step = next(s for s in model.steps if s.id == active_step.id)
        db_step.current_count = active_step.current_count
        db_step.status = active_step.status.value
        db_step.completed_at = active_step.completed_at
        db_step.activated_at = active_step.activated_at

        if status_change is not None:
            model.status = domain_request.status.value
            model.resolved_at = domain_request.resolved_at
            model.updated_at = now  # type: ignore[assignment]

        next_active_domain_step = next(
            (
                s
                for s in domain_request.steps
                if s.status == StepStatus.ACTIVE and s.id != active_step.id
            ),
            None,
        )
        if next_active_domain_step is not None:
            next_db_step = next(s for s in model.steps if s.id == next_active_domain_step.id)
            next_db_step.status = StepStatus.ACTIVE.value
            next_db_step.activated_at = now

        await self._approval_repo.update_request(model)

        await self._audit.log(
            workspace_id=dto.workspace_id,
            entity_type=EntityType.APPROVAL_DECISION,
            entity_id=decision_id,
            action=AuditAction.DECISION_MADE,
            actor_id=dto.actor_id,
            new_state={
                "action": dto.action,
                "step_id": str(active_step.id),
                "request_id": str(dto.request_id),
                "comment": dto.comment,
            },
        )

        decision_event = DecisionMadeEvent(
            workspace_id=dto.workspace_id,
            request_id=dto.request_id,
            step_id=active_step.id,
            actor_id=dto.actor_id,
            action=dto.action,
        )
        await self._outbox.write(
            event_type=decision_event.event_type,
            aggregate_type="approval_request",
            aggregate_id=dto.request_id,
            workspace_id=dto.workspace_id,
            payload=event_to_payload(decision_event),
        )

        if status_change is not None:
            status_event = RequestStatusChangedEvent(
                workspace_id=dto.workspace_id,
                request_id=dto.request_id,
                old_status=old_request_status,
                new_status=domain_request.status.value,
            )
            await self._outbox.write(
                event_type=status_event.event_type,
                aggregate_type="approval_request",
                aggregate_id=dto.request_id,
                workspace_id=dto.workspace_id,
                payload=event_to_payload(status_event),
            )

        if next_active_domain_step is not None:
            step_event = StepActivatedEvent(
                workspace_id=dto.workspace_id,
                request_id=dto.request_id,
                step_id=next_active_domain_step.id,
                step_order=next_active_domain_step.step_order,
                approver_role=next_active_domain_step.approver_role,
            )
            await self._outbox.write(
                event_type=step_event.event_type,
                aggregate_type="approval_request",
                aggregate_id=dto.request_id,
                workspace_id=dto.workspace_id,
                payload=event_to_payload(step_event),
            )

        result = await self._approval_repo.get_request_by_id(dto.request_id, dto.workspace_id)
        assert result is not None
        return result

    async def get_decisions(
        self, request_id: UUID, workspace_id: UUID
    ) -> list[ApprovalDecisionModel]:
        model = await self._approval_repo.get_request_by_id(request_id, workspace_id)
        if model is None:
            raise RequestNotFoundError()
        return await self._approval_repo.get_decisions_by_request(request_id, workspace_id)

    def _to_domain_request(self, model: ApprovalRequestModel) -> ApprovalRequest:
        steps: list[ApprovalStep] = []
        for s in model.steps:
            decisions = [
                Decision(
                    id=d.id,
                    step_id=d.step_id,
                    workspace_id=d.workspace_id,
                    actor_id=d.actor_id,
                    action=ActionType(d.action),
                    comment=d.comment,
                    created_at=d.created_at,
                )
                for d in s.decisions
            ]
            steps.append(
                ApprovalStep(
                    id=s.id,
                    request_id=s.request_id,
                    workspace_id=s.workspace_id,
                    step_order=s.step_order,
                    approver_role=s.approver_role,
                    required_count=s.required_count,
                    current_count=s.current_count,
                    status=StepStatus(s.status),
                    activated_at=s.activated_at,
                    completed_at=s.completed_at,
                    created_at=s.created_at,
                    decisions=decisions,
                )
            )
        return ApprovalRequest(
            id=model.id,
            workspace_id=model.workspace_id,
            rule_id=model.rule_id,
            external_resource_id=model.external_resource_id,
            resource_type=model.resource_type,
            title=model.title,
            payload=model.payload,
            requester_id=model.requester_id,
            status=RequestStatus(model.status),
            resolved_at=model.resolved_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
            steps=steps,
        )
