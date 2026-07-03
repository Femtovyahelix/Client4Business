from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from approval_service.infrastructure.database.models.approval_decision import (
    ApprovalDecisionModel,
)
from approval_service.infrastructure.database.models.approval_request import (
    ApprovalRequestModel,
)
from approval_service.infrastructure.database.models.approval_step import ApprovalStepModel


class ApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_request(self, model: ApprovalRequestModel) -> ApprovalRequestModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_request_by_id(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> ApprovalRequestModel | None:
        stmt = (
            select(ApprovalRequestModel)
            .options(
                selectinload(ApprovalRequestModel.steps).selectinload(ApprovalStepModel.decisions),
            )
            .where(
                ApprovalRequestModel.id == request_id,
                ApprovalRequestModel.workspace_id == workspace_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

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
        base = select(ApprovalRequestModel).where(
            ApprovalRequestModel.workspace_id == workspace_id,
        )
        if status is not None:
            base = base.where(ApprovalRequestModel.status == status)
        if resource_type is not None:
            base = base.where(ApprovalRequestModel.resource_type == resource_type)
        if requester_id is not None:
            base = base.where(ApprovalRequestModel.requester_id == requester_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        items_stmt = (
            base.options(
                selectinload(ApprovalRequestModel.steps).selectinload(ApprovalStepModel.decisions),
            )
            .order_by(ApprovalRequestModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items_result = await self._session.execute(items_stmt)
        items = list(items_result.scalars().all())
        return items, total

    async def update_request(self, model: ApprovalRequestModel) -> None:
        await self._session.flush()

    async def create_step(self, model: ApprovalStepModel) -> ApprovalStepModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def create_decision(self, model: ApprovalDecisionModel) -> ApprovalDecisionModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_decisions_by_request(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> list[ApprovalDecisionModel]:
        stmt = (
            select(ApprovalDecisionModel)
            .join(ApprovalStepModel)
            .where(
                ApprovalStepModel.request_id == request_id,
                ApprovalDecisionModel.workspace_id == workspace_id,
            )
            .order_by(ApprovalDecisionModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
