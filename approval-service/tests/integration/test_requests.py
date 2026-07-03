from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from tests.integration.conftest import (
    _headers,
    approve_request,
    create_approval_request,
    create_rule,
)

pytestmark = pytest.mark.asyncio


class TestCreateRequest:
    async def test_create_request_returns_201(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(client, workspace_id, rule["id"])

        assert req["status"] == "in_review"
        assert req["resource_type"] == "invoice"
        assert req["workspace_id"] == str(workspace_id)
        assert len(req["steps"]) == 1
        assert req["steps"][0]["status"] == "active"

    async def test_create_request_with_payload(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        body = {
            "external_resource_id": "PAY-123",
            "resource_type": "invoice",
            "title": "Payment Request",
            "payload": {"amount": 9999, "currency": "USD"},
            "requester_id": str(uuid4()),
            "rule_id": rule["id"],
        }
        resp = await client.post("/api/v1/requests", json=body, headers=_headers(workspace_id))
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["payload"]["amount"] == 9999
        assert data["payload"]["currency"] == "USD"

    async def test_duplicate_active_request_returns_409(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="DUP-001"
        )

        body = {
            "external_resource_id": "DUP-001",
            "resource_type": "invoice",
            "title": "Duplicate",
            "payload": {},
            "requester_id": str(uuid4()),
            "rule_id": rule["id"],
        }
        resp = await client.post("/api/v1/requests", json=body, headers=_headers(workspace_id))
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DUPLICATE_ACTIVE_REQUEST"

    async def test_create_request_rule_not_found_returns_404(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        body = {
            "external_resource_id": "RES-404",
            "resource_type": "invoice",
            "title": "No Rule",
            "payload": {},
            "requester_id": str(uuid4()),
            "rule_id": str(uuid4()),
        }
        resp = await client.post("/api/v1/requests", json=body, headers=_headers(workspace_id))
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "RULE_NOT_FOUND"


class TestListRequests:
    async def test_list_returns_created_requests(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="LIST-1"
        )
        await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="LIST-2"
        )

        resp = await client.get("/api/v1/requests", headers=_headers(workspace_id))
        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["total"] >= 2
        ids = {r["external_resource_id"] for r in data["data"]}
        assert "LIST-1" in ids
        assert "LIST-2" in ids

    async def test_list_filter_by_status(self, client: AsyncClient, workspace_id: UUID) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="FILT-1"
        )
        await approve_request(client, workspace_id, req["id"])

        resp = await client.get(
            "/api/v1/requests",
            params={"status": "approved"},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 200
        for r in resp.json()["data"]:
            assert r["status"] == "approved"

    async def test_list_pagination(self, client: AsyncClient, workspace_id: UUID) -> None:
        rule = await create_rule(client, workspace_id)
        for i in range(3):
            await create_approval_request(
                client, workspace_id, rule["id"], external_resource_id=f"PAGE-{i}"
            )

        resp = await client.get(
            "/api/v1/requests",
            params={"limit": 2, "offset": 0},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 2
        assert data["pagination"]["has_more"] is True


class TestGetRequest:
    async def test_get_existing_request(self, client: AsyncClient, workspace_id: UUID) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(client, workspace_id, rule["id"])

        resp = await client.get(
            f"/api/v1/requests/{req['id']}",
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == req["id"]
        assert data["status"] == "in_review"

    async def test_get_nonexistent_request_returns_404(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        resp = await client.get(
            f"/api/v1/requests/{uuid4()}",
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "REQUEST_NOT_FOUND"


class TestCancelRequest:
    async def test_cancel_pending_or_in_review_request(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(client, workspace_id, rule["id"])
        actor = uuid4()

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/cancel",
            json={"actor_id": str(actor)},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"
        assert resp.json()["data"]["resolved_at"] is not None

    async def test_cancel_already_resolved_returns_409(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(client, workspace_id, rule["id"])
        await approve_request(client, workspace_id, req["id"])

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/cancel",
            json={"actor_id": str(uuid4())},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "ALREADY_RESOLVED"

    async def test_cancel_nonexistent_request_returns_404(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        resp = await client.post(
            f"/api/v1/requests/{uuid4()}/cancel",
            json={"actor_id": str(uuid4())},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 404
