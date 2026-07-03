from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from tests.integration.conftest import (
    _headers,
    approve_request,
    create_approval_request,
    create_rule,
    reject_request,
)

pytestmark = pytest.mark.asyncio


class TestAuditTrail:
    async def test_create_request_creates_audit_entry(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="AUD-CREATE"
        )

        resp = await client.get(
            "/api/v1/audit-log",
            params={"entity_id": req["id"]},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 200
        entries = resp.json()["data"]
        assert len(entries) >= 1
        actions = {e["action"] for e in entries}
        assert "created" in actions

    async def test_approve_decision_creates_audit_entry(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="AUD-APPR"
        )
        actor = uuid4()
        await approve_request(client, workspace_id, req["id"], actor_id=actor)

        resp = await client.get(
            "/api/v1/audit-log",
            params={"actor_id": str(actor)},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 200
        entries = resp.json()["data"]
        assert len(entries) >= 1
        decision_entries = [e for e in entries if e["action"] == "decision_made"]
        assert len(decision_entries) == 1
        assert decision_entries[0]["actor_id"] == str(actor)

    async def test_reject_creates_audit_entry(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="AUD-REJ"
        )
        actor = uuid4()
        await reject_request(client, workspace_id, req["id"], actor_id=actor)

        resp = await client.get(
            "/api/v1/audit-log",
            params={"actor_id": str(actor)},
            headers=_headers(workspace_id),
        )
        entries = resp.json()["data"]
        decision_entries = [e for e in entries if e["action"] == "decision_made"]
        assert len(decision_entries) == 1

    async def test_cancel_creates_audit_entry(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="AUD-CANCEL"
        )
        actor = uuid4()
        await client.post(
            f"/api/v1/requests/{req['id']}/cancel",
            json={"actor_id": str(actor)},
            headers=_headers(workspace_id),
        )

        resp = await client.get(
            "/api/v1/audit-log",
            params={"entity_id": req["id"]},
            headers=_headers(workspace_id),
        )
        entries = resp.json()["data"]
        actions = {e["action"] for e in entries}
        assert "cancelled" in actions

    async def test_audit_entries_have_old_and_new_state(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="AUD-STATE"
        )
        actor = uuid4()
        await client.post(
            f"/api/v1/requests/{req['id']}/cancel",
            json={"actor_id": str(actor)},
            headers=_headers(workspace_id),
        )

        resp = await client.get(
            "/api/v1/audit-log",
            params={"entity_id": req["id"]},
            headers=_headers(workspace_id),
        )
        cancel_entries = [e for e in resp.json()["data"] if e["action"] == "cancelled"]
        assert len(cancel_entries) == 1
        entry = cancel_entries[0]
        assert entry["old_state"] is not None
        assert entry["new_state"] is not None
        assert entry["new_state"]["status"] == "cancelled"

    async def test_audit_log_pagination(self, client: AsyncClient, workspace_id: UUID) -> None:
        rule = await create_rule(client, workspace_id)
        for i in range(3):
            await create_approval_request(
                client, workspace_id, rule["id"], external_resource_id=f"AUD-PAG-{i}"
            )

        resp = await client.get(
            "/api/v1/audit-log",
            params={"limit": 2, "offset": 0},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 2
        assert data["pagination"]["total"] >= 3

    async def test_audit_filter_by_entity_type(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="AUD-FTYPE"
        )
        await approve_request(client, workspace_id, req["id"])

        resp = await client.get(
            "/api/v1/audit-log",
            params={"entity_type": "approval_decision"},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 200
        for entry in resp.json()["data"]:
            assert entry["entity_type"] == "approval_decision"

    async def test_full_lifecycle_audit_trail(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="AUD-FULL"
        )
        await approve_request(client, workspace_id, req["id"])

        resp = await client.get(
            "/api/v1/audit-log",
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 200
        entries = resp.json()["data"]
        assert len(entries) >= 2
