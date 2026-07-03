from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from tests.integration.conftest import (
    _headers,
    create_approval_request,
    create_rule,
)

pytestmark = pytest.mark.asyncio


class TestWorkspaceIsolation:
    async def test_rule_invisible_across_workspaces(
        self,
        client: AsyncClient,
        workspace_id: UUID,
        other_workspace_id: UUID,
    ) -> None:
        rule = await create_rule(client, workspace_id, name="WS-A Rule")

        resp = await client.get(
            f"/api/v1/rules/{rule['id']}",
            headers=_headers(other_workspace_id),
        )
        assert resp.status_code == 404

    async def test_request_invisible_across_workspaces(
        self,
        client: AsyncClient,
        workspace_id: UUID,
        other_workspace_id: UUID,
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="ISO-1"
        )

        resp = await client.get(
            f"/api/v1/requests/{req['id']}",
            headers=_headers(other_workspace_id),
        )
        assert resp.status_code == 404

    async def test_list_requests_scoped_to_workspace(
        self,
        client: AsyncClient,
        workspace_id: UUID,
        other_workspace_id: UUID,
    ) -> None:
        rule_a = await create_rule(client, workspace_id, name="Rule A")
        rule_b = await create_rule(client, other_workspace_id, name="Rule B")

        await create_approval_request(
            client, workspace_id, rule_a["id"], external_resource_id="WS-A-REQ"
        )
        await create_approval_request(
            client, other_workspace_id, rule_b["id"], external_resource_id="WS-B-REQ"
        )

        resp_a = await client.get("/api/v1/requests", headers=_headers(workspace_id))
        resp_b = await client.get("/api/v1/requests", headers=_headers(other_workspace_id))

        ids_a = {r["external_resource_id"] for r in resp_a.json()["data"]}
        ids_b = {r["external_resource_id"] for r in resp_b.json()["data"]}

        assert "WS-A-REQ" in ids_a
        assert "WS-B-REQ" not in ids_a
        assert "WS-B-REQ" in ids_b
        assert "WS-A-REQ" not in ids_b

    async def test_list_rules_scoped_to_workspace(
        self,
        client: AsyncClient,
        workspace_id: UUID,
        other_workspace_id: UUID,
    ) -> None:
        await create_rule(client, workspace_id, name="WS-A Only Rule")
        await create_rule(client, other_workspace_id, name="WS-B Only Rule")

        resp_a = await client.get("/api/v1/rules", headers=_headers(workspace_id))
        resp_b = await client.get("/api/v1/rules", headers=_headers(other_workspace_id))

        names_a = {r["name"] for r in resp_a.json()["data"]}
        names_b = {r["name"] for r in resp_b.json()["data"]}

        assert "WS-A Only Rule" in names_a
        assert "WS-B Only Rule" not in names_a
        assert "WS-B Only Rule" in names_b
        assert "WS-A Only Rule" not in names_b

    async def test_cannot_cancel_request_from_another_workspace(
        self,
        client: AsyncClient,
        workspace_id: UUID,
        other_workspace_id: UUID,
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="CROSS-CANCEL"
        )

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/cancel",
            json={"actor_id": str(uuid4())},
            headers=_headers(other_workspace_id),
        )
        assert resp.status_code == 404

    async def test_cannot_decide_request_from_another_workspace(
        self,
        client: AsyncClient,
        workspace_id: UUID,
        other_workspace_id: UUID,
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="CROSS-DEC"
        )

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/decisions",
            json={"actor_id": str(uuid4()), "action": "approve"},
            headers=_headers(other_workspace_id),
        )
        assert resp.status_code == 404

    async def test_audit_log_scoped_to_workspace(
        self,
        client: AsyncClient,
        workspace_id: UUID,
        other_workspace_id: UUID,
    ) -> None:
        rule = await create_rule(client, workspace_id)
        await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="AUD-ISO"
        )

        resp_a = await client.get("/api/v1/audit-log", headers=_headers(workspace_id))
        resp_b = await client.get("/api/v1/audit-log", headers=_headers(other_workspace_id))

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert resp_a.json()["pagination"]["total"] >= 1
        assert resp_b.json()["pagination"]["total"] == 0
