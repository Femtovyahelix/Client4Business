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


class TestNotFound404:
    async def test_get_nonexistent_request(self, client: AsyncClient, workspace_id: UUID) -> None:
        resp = await client.get(
            f"/api/v1/requests/{uuid4()}",
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "REQUEST_NOT_FOUND"
        assert "meta" in body
        assert "timestamp" in body["meta"]

    async def test_get_nonexistent_rule(self, client: AsyncClient, workspace_id: UUID) -> None:
        resp = await client.get(
            f"/api/v1/rules/{uuid4()}",
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "RULE_NOT_FOUND"

    async def test_cancel_nonexistent_request(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        resp = await client.post(
            f"/api/v1/requests/{uuid4()}/cancel",
            json={"actor_id": str(uuid4())},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 404

    async def test_decision_on_nonexistent_request(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        resp = await client.post(
            f"/api/v1/requests/{uuid4()}/decisions",
            json={"actor_id": str(uuid4()), "action": "approve"},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "REQUEST_NOT_FOUND"


class TestConflict409:
    async def test_approve_already_approved_request(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="C409-1"
        )
        await approve_request(client, workspace_id, req["id"])

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/decisions",
            json={"actor_id": str(uuid4()), "action": "approve"},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] in ("ALREADY_RESOLVED", "INVALID_STATE_TRANSITION")

    async def test_cancel_already_cancelled_request(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="C409-2"
        )
        await client.post(
            f"/api/v1/requests/{req['id']}/cancel",
            json={"actor_id": str(uuid4())},
            headers=_headers(workspace_id),
        )

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/cancel",
            json={"actor_id": str(uuid4())},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "ALREADY_RESOLVED"


class TestSelfApproval422:
    async def test_requester_cannot_approve_own_request(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        requester = uuid4()
        req = await create_approval_request(
            client,
            workspace_id,
            rule["id"],
            requester_id=requester,
            external_resource_id="SELF-1",
        )

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/decisions",
            json={"actor_id": str(requester), "action": "approve"},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "SELF_APPROVAL"

    async def test_requester_cannot_reject_own_request(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        requester = uuid4()
        req = await create_approval_request(
            client,
            workspace_id,
            rule["id"],
            requester_id=requester,
            external_resource_id="SELF-2",
        )

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/decisions",
            json={"actor_id": str(requester), "action": "reject"},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "SELF_APPROVAL"


class TestDuplicateDecision:
    async def test_same_actor_cannot_decide_twice(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        steps = [{"order": 1, "approver_role": "team", "required_count": 3}]
        rule = await create_rule(client, workspace_id, steps=steps)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="DUP-DEC-1"
        )
        actor = uuid4()
        await approve_request(client, workspace_id, req["id"], actor_id=actor)

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/decisions",
            json={"actor_id": str(actor), "action": "approve"},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DUPLICATE_DECISION"


class TestMissingWorkspaceHeader:
    async def test_missing_workspace_header_returns_422(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/requests")
        assert resp.status_code == 422

    async def test_invalid_workspace_header_returns_400(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/v1/requests",
            headers={"X-Workspace-Id": "not-a-uuid"},
        )
        assert resp.status_code == 400


class TestErrorResponseFormat:
    async def test_error_response_has_unified_format(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        resp = await client.get(
            f"/api/v1/requests/{uuid4()}",
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "details" in body["error"]
        assert "meta" in body
        assert "timestamp" in body["meta"]
