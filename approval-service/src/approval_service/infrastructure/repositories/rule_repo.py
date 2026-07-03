from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from approval_service.infrastructure.database.models.approval_rule import ApprovalRuleModel


class RuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, model: ApprovalRuleModel) -> ApprovalRuleModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_by_id(
        self,
        rule_id: UUID,
        workspace_id: UUID,
    ) -> ApprovalRuleModel | None:
        stmt = select(ApprovalRuleModel).where(
            ApprovalRuleModel.id == rule_id,
            ApprovalRuleModel.workspace_id == workspace_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_rules(
        self,
        workspace_id: UUID,
        *,
        resource_type: str | None = None,
        is_active: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ApprovalRuleModel], int]:
        base = select(ApprovalRuleModel).where(
            ApprovalRuleModel.workspace_id == workspace_id,
        )
        if resource_type is not None:
            base = base.where(ApprovalRuleModel.resource_type == resource_type)
        if is_active is not None:
            base = base.where(ApprovalRuleModel.is_active == is_active)

        count_stmt = select(func.count()).select_from(base.subquery())
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        items_stmt = base.order_by(ApprovalRuleModel.created_at.desc()).limit(limit).offset(offset)
        items_result = await self._session.execute(items_stmt)
        items = list(items_result.scalars().all())
        return items, total

    async def update(self, model: ApprovalRuleModel) -> None:
        await self._session.flush()

    async def find_matching_rule(
        self,
        workspace_id: UUID,
        resource_type: str,
    ) -> ApprovalRuleModel | None:
        stmt = (
            select(ApprovalRuleModel)
            .where(
                ApprovalRuleModel.workspace_id == workspace_id,
                ApprovalRuleModel.resource_type == resource_type,
                ApprovalRuleModel.is_active.is_(True),
            )
            .order_by(ApprovalRuleModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
