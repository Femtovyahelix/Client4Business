from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from approval_service.api.middleware.error_handler import (
    app_error_handler,
    unhandled_error_handler,
)
from approval_service.api.middleware.idempotency import IdempotencyMiddleware
from approval_service.api.middleware.logging_ctx import LoggingContextMiddleware
from approval_service.api.v1.routers import audit, decisions, health, requests, rules
from approval_service.domain.exceptions import AppError
from approval_service.infrastructure.database.models.workspace import WorkspaceModel

pytestmark = pytest.mark.asyncio


class _TestIdempotencyMiddleware(IdempotencyMiddleware):
    """Subclass that skips pg_advisory_xact_lock for SQLite."""

    async def _acquire_advisory_lock(self, session: AsyncSession, key: str) -> None:
        pass


def _build_idempotent_app(session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = FastAPI()
    app.state.session_factory = session_factory
    app.add_middleware(_TestIdempotencyMiddleware, session_factory=session_factory, ttl_hours=24)
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
async def idemp_workspace_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    ws_id = uuid4()
    async with session_factory() as session, session.begin():
        session.add(WorkspaceModel(id=ws_id, name="Idempotency WS"))
    return ws_id


@pytest_asyncio.fixture
async def idemp_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> Any:
    app = _build_idempotent_app(session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _headers(workspace_id: UUID, idemp_key: str | None = None) -> dict[str, str]:
    h: dict[str, str] = {"X-Workspace-Id": str(workspace_id)}
    if idemp_key is not None:
        h["Idempotency-Key"] = idemp_key
    return h


async def _create_rule(client: AsyncClient, workspace_id: UUID) -> dict[str, Any]:
    body = {
        "name": "Idemp Rule",
        "resource_type": "invoice",
        "steps": [{"order": 1, "approver_role": "manager", "required_count": 1}],
    }
    resp = await client.post("/api/v1/rules", json=body, headers=_headers(workspace_id))
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestIdempotency:
    async def test_idempotent_replay_returns_same_response(
        self, idemp_client: AsyncClient, idemp_workspace_id: UUID
    ) -> None:
        rule = await _create_rule(idemp_client, idemp_workspace_id)
        idemp_key = f"idemp-{uuid4()}"
        body = {
            "external_resource_id": "IDEMP-1",
            "resource_type": "invoice",
            "title": "Idempotent Request",
            "payload": {},
            "requester_id": str(uuid4()),
            "rule_id": rule["id"],
        }
        headers = _headers(idemp_workspace_id, idemp_key)

        resp1 = await idemp_client.post("/api/v1/requests", json=body, headers=headers)
        assert resp1.status_code == 201

        resp2 = await idemp_client.post("/api/v1/requests", json=body, headers=headers)
        assert resp2.status_code == 201
        assert resp1.json()["data"]["id"] == resp2.json()["data"]["id"]

    async def test_different_idempotency_keys_create_different_resources(
        self, idemp_client: AsyncClient, idemp_workspace_id: UUID
    ) -> None:
        rule = await _create_rule(idemp_client, idemp_workspace_id)
        body1 = {
            "external_resource_id": "IDEMP-DIFF-1",
            "resource_type": "invoice",
            "title": "Request A",
            "payload": {},
            "requester_id": str(uuid4()),
            "rule_id": rule["id"],
        }
        body2 = {
            "external_resource_id": "IDEMP-DIFF-2",
            "resource_type": "invoice",
            "title": "Request B",
            "payload": {},
            "requester_id": str(uuid4()),
            "rule_id": rule["id"],
        }

        resp1 = await idemp_client.post(
            "/api/v1/requests",
            json=body1,
            headers=_headers(idemp_workspace_id, f"key-{uuid4()}"),
        )
        resp2 = await idemp_client.post(
            "/api/v1/requests",
            json=body2,
            headers=_headers(idemp_workspace_id, f"key-{uuid4()}"),
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["data"]["id"] != resp2.json()["data"]["id"]

    async def test_idempotency_key_reused_for_different_path_returns_422(
        self, idemp_client: AsyncClient, idemp_workspace_id: UUID
    ) -> None:
        rule = await _create_rule(idemp_client, idemp_workspace_id)
        idemp_key = f"conflict-{uuid4()}"
        body = {
            "external_resource_id": "IDEMP-CONFLICT",
            "resource_type": "invoice",
            "title": "First",
            "payload": {},
            "requester_id": str(uuid4()),
            "rule_id": rule["id"],
        }
        headers = _headers(idemp_workspace_id, idemp_key)
        resp1 = await idemp_client.post("/api/v1/requests", json=body, headers=headers)
        assert resp1.status_code == 201

        rule_body = {
            "name": "Another Rule",
            "resource_type": "payment",
            "steps": [{"order": 1, "approver_role": "cfo", "required_count": 1}],
        }
        resp2 = await idemp_client.post("/api/v1/rules", json=rule_body, headers=headers)
        assert resp2.status_code == 422
        assert resp2.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    async def test_no_idempotency_header_passes_through(
        self, idemp_client: AsyncClient, idemp_workspace_id: UUID
    ) -> None:
        resp = await idemp_client.get(
            "/api/v1/health/ready",
            headers={"X-Workspace-Id": str(idemp_workspace_id)},
        )
        assert resp.status_code == 200
