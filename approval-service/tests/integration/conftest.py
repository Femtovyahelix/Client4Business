from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from approval_service.api.middleware.error_handler import (
    app_error_handler,
    unhandled_error_handler,
)
from approval_service.api.middleware.logging_ctx import LoggingContextMiddleware
from approval_service.api.v1.routers import audit, decisions, health, requests, rules
from approval_service.domain.exceptions import AppError
from approval_service.infrastructure.database.base import Base
from approval_service.infrastructure.database.models import (  # noqa: F401 — side-effect import
    ApprovalDecisionModel,
    ApprovalRequestModel,
    ApprovalRuleModel,
    ApprovalStepModel,
    AuditLogModel,
    IdempotencyKeyModel,
    OutboxModel,
    WorkspaceModel,
)


@compiles(JSONB, "sqlite")  # type: ignore[misc]
def _compile_jsonb_for_sqlite(element: JSONB, compiler: Any, **kw: Any) -> str:
    return compiler.visit_JSON(JSON(), **kw)


@compiles(BigInteger, "sqlite")  # type: ignore[misc]
def _compile_bigint_for_sqlite(element: BigInteger, compiler: Any, **kw: Any) -> str:
    return "INTEGER"


def _build_app(session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = FastAPI()
    app.state.session_factory = session_factory
    app.add_middleware(LoggingContextMiddleware)
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(rules.router, prefix=prefix)
    app.include_router(requests.router, prefix=prefix)
    app.include_router(decisions.router, prefix=prefix)
    app.include_router(audit.router, prefix=prefix)
    return app


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[Any, None]:
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: Any) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def app(session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
    return _build_app(session_factory)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def workspace_id(session_factory: async_sessionmaker[AsyncSession]) -> UUID:
    ws_id = uuid4()
    async with session_factory() as session, session.begin():
        session.add(WorkspaceModel(id=ws_id, name="Test Workspace"))
    return ws_id


@pytest_asyncio.fixture
async def other_workspace_id(session_factory: async_sessionmaker[AsyncSession]) -> UUID:
    ws_id = uuid4()
    async with session_factory() as session, session.begin():
        session.add(WorkspaceModel(id=ws_id, name="Other Workspace"))
    return ws_id


def _headers(workspace_id: UUID) -> dict[str, str]:
    return {"X-Workspace-Id": str(workspace_id)}


async def create_rule(
    client: AsyncClient,
    workspace_id: UUID,
    *,
    resource_type: str = "invoice",
    name: str = "Default Rule",
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": name,
        "resource_type": resource_type,
        "steps": steps or [{"order": 1, "approver_role": "manager", "required_count": 1}],
    }
    resp = await client.post("/api/v1/rules", json=body, headers=_headers(workspace_id))
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def create_approval_request(
    client: AsyncClient,
    workspace_id: UUID,
    rule_id: UUID | str,
    *,
    requester_id: UUID | None = None,
    external_resource_id: str = "RES-001",
    resource_type: str = "invoice",
    title: str = "Test Request",
) -> dict[str, Any]:
    body = {
        "external_resource_id": external_resource_id,
        "resource_type": resource_type,
        "title": title,
        "payload": {"amount": 100},
        "requester_id": str(requester_id or uuid4()),
        "rule_id": str(rule_id),
    }
    resp = await client.post("/api/v1/requests", json=body, headers=_headers(workspace_id))
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def approve_request(
    client: AsyncClient,
    workspace_id: UUID,
    request_id: str,
    *,
    actor_id: UUID | None = None,
    comment: str = "",
) -> dict[str, Any]:
    actor = actor_id or uuid4()
    body = {"actor_id": str(actor), "action": "approve", "comment": comment}
    resp = await client.post(
        f"/api/v1/requests/{request_id}/decisions",
        json=body,
        headers=_headers(workspace_id),
    )
    return resp.json()


async def reject_request(
    client: AsyncClient,
    workspace_id: UUID,
    request_id: str,
    *,
    actor_id: UUID | None = None,
    comment: str = "",
) -> dict[str, Any]:
    actor = actor_id or uuid4()
    body = {"actor_id": str(actor), "action": "reject", "comment": comment}
    resp = await client.post(
        f"/api/v1/requests/{request_id}/decisions",
        json=body,
        headers=_headers(workspace_id),
    )
    return resp.json()
