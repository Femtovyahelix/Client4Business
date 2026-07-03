from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_liveness_always_ok(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_readiness_checks_database(client: AsyncClient, workspace_id: UUID) -> None:
    resp = await client.get(
        "/api/v1/health/ready",
        headers={"X-Workspace-Id": str(workspace_id)},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
