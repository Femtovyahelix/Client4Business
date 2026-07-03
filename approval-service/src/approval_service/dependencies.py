from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from approval_service.application.services.approval_service import ApprovalService
from approval_service.application.services.audit_service import AuditService
from approval_service.application.services.rule_service import RuleService
from approval_service.common.clock import Clock
from approval_service.infrastructure.outbox.writer import DatabaseOutboxWriter
from approval_service.infrastructure.repositories.approval_repo import ApprovalRepository
from approval_service.infrastructure.repositories.audit_repo import AuditRepository
from approval_service.infrastructure.repositories.rule_repo import RuleRepository


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session, session.begin():
        yield session


async def get_approval_service(
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalService:
    approval_repo = ApprovalRepository(session)
    rule_repo = RuleRepository(session)
    audit_repo = AuditRepository(session)
    audit_service = AuditService(audit_repo)
    outbox_writer = DatabaseOutboxWriter(session)
    clock = Clock()
    return ApprovalService(
        approval_repo=approval_repo,
        rule_repo=rule_repo,
        audit=audit_service,
        outbox=outbox_writer,
        clock=clock,
    )


async def get_rule_service(
    session: AsyncSession = Depends(get_db_session),
) -> RuleService:
    rule_repo = RuleRepository(session)
    audit_repo = AuditRepository(session)
    audit_service = AuditService(audit_repo)
    outbox_writer = DatabaseOutboxWriter(session)
    return RuleService(
        repo=rule_repo,
        audit=audit_service,
        outbox=outbox_writer,
    )


async def get_audit_service(
    session: AsyncSession = Depends(get_db_session),
) -> AuditService:
    audit_repo = AuditRepository(session)
    return AuditService(audit_repo)
