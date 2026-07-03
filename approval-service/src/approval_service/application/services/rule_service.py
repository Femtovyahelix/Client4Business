from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from approval_service.application.dto import CreateRuleDTO, UpdateRuleDTO
from approval_service.application.interfaces import OutboxWriter
from approval_service.application.services.audit_service import AuditService
from approval_service.domain.exceptions import OptimisticLockError, RuleNotFoundError
from approval_service.domain.models.enums import AuditAction, EntityType
from approval_service.infrastructure.database.models.approval_rule import ApprovalRuleModel
from approval_service.infrastructure.repositories.rule_repo import RuleRepository


class RuleService:
    """CRUD operations for approval rules with audit trail and outbox events."""

    def __init__(
        self,
        repo: RuleRepository,
        audit: AuditService,
        outbox: OutboxWriter,
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._outbox = outbox

    async def create_rule(self, dto: CreateRuleDTO) -> ApprovalRuleModel:
        rule_id = uuid4()
        steps_data: list[dict[str, Any]] = [
            {
                "order": s.order,
                "approver_role": s.approver_role,
                "required_count": s.required_count,
            }
            for s in dto.steps
        ]
        model = ApprovalRuleModel(
            id=rule_id,
            workspace_id=dto.workspace_id,
            name=dto.name,
            description=dto.description,
            resource_type=dto.resource_type,
            conditions=dto.conditions,
            steps=steps_data,
            is_active=True,
            version=1,
        )
        model = await self._repo.create(model)

        await self._audit.log(
            workspace_id=dto.workspace_id,
            entity_type=EntityType.APPROVAL_RULE,
            entity_id=rule_id,
            action=AuditAction.CREATED,
            new_state={
                "name": dto.name,
                "resource_type": dto.resource_type,
                "steps": steps_data,
            },
        )

        await self._outbox.write(
            event_type="approval.rule.created",
            aggregate_type="approval_rule",
            aggregate_id=rule_id,
            workspace_id=dto.workspace_id,
            payload={"rule_id": str(rule_id), "name": dto.name},
        )

        return model

    async def get_rule(self, rule_id: UUID, workspace_id: UUID) -> ApprovalRuleModel:
        model = await self._repo.get_by_id(rule_id, workspace_id)
        if model is None:
            raise RuleNotFoundError()
        return model

    async def list_rules(
        self,
        workspace_id: UUID,
        *,
        resource_type: str | None = None,
        is_active: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ApprovalRuleModel], int]:
        return await self._repo.list_rules(
            workspace_id,
            resource_type=resource_type,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )

    async def update_rule(self, dto: UpdateRuleDTO) -> ApprovalRuleModel:
        model = await self._repo.get_by_id(dto.rule_id, dto.workspace_id)
        if model is None:
            raise RuleNotFoundError()
        if model.version != dto.version:
            raise OptimisticLockError()

        old_state: dict[str, Any] = {
            "name": model.name,
            "description": model.description,
            "conditions": model.conditions,
            "steps": model.steps,
            "is_active": model.is_active,
            "version": model.version,
        }

        if dto.name is not None:
            model.name = dto.name
        if dto.description is not None:
            model.description = dto.description
        if dto.conditions is not None:
            model.conditions = dto.conditions
        if dto.steps is not None:
            model.steps = [
                {
                    "order": s.order,
                    "approver_role": s.approver_role,
                    "required_count": s.required_count,
                }
                for s in dto.steps
            ]
        if dto.is_active is not None:
            model.is_active = dto.is_active
        model.version += 1

        await self._repo.update(model)

        new_state: dict[str, Any] = {
            "name": model.name,
            "description": model.description,
            "conditions": model.conditions,
            "steps": model.steps,
            "is_active": model.is_active,
            "version": model.version,
        }

        audit_action = AuditAction.UPDATED
        if dto.is_active is False:
            audit_action = AuditAction.DEACTIVATED

        await self._audit.log(
            workspace_id=dto.workspace_id,
            entity_type=EntityType.APPROVAL_RULE,
            entity_id=dto.rule_id,
            action=audit_action,
            old_state=old_state,
            new_state=new_state,
        )

        await self._outbox.write(
            event_type=f"approval.rule.{audit_action}",
            aggregate_type="approval_rule",
            aggregate_id=dto.rule_id,
            workspace_id=dto.workspace_id,
            payload={"rule_id": str(dto.rule_id), "version": model.version},
        )

        return model

    async def deactivate_rule(self, rule_id: UUID, workspace_id: UUID) -> None:
        model = await self._repo.get_by_id(rule_id, workspace_id)
        if model is None:
            raise RuleNotFoundError()

        old_state: dict[str, Any] = {"is_active": model.is_active, "version": model.version}
        model.is_active = False
        model.version += 1
        await self._repo.update(model)

        await self._audit.log(
            workspace_id=workspace_id,
            entity_type=EntityType.APPROVAL_RULE,
            entity_id=rule_id,
            action=AuditAction.DEACTIVATED,
            old_state=old_state,
            new_state={"is_active": False, "version": model.version},
        )

        await self._outbox.write(
            event_type="approval.rule.deactivated",
            aggregate_type="approval_rule",
            aggregate_id=rule_id,
            workspace_id=workspace_id,
            payload={"rule_id": str(rule_id)},
        )
