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


class TestApproveDecision:
    async def test_approve_single_step_request(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(client, workspace_id, rule["id"])

        result = await approve_request(client, workspace_id, req["id"])
        assert result["data"]["status"] == "approved"
        assert result["data"]["resolved_at"] is not None

    async def test_approve_multi_step_request(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        steps = [
            {"order": 1, "approver_role": "manager", "required_count": 1},
            {"order": 2, "approver_role": "director", "required_count": 1},
        ]
        rule = await create_rule(client, workspace_id, steps=steps)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="MULTI-1"
        )

        result1 = await approve_request(client, workspace_id, req["id"])
        assert result1["data"]["status"] == "in_review"

        result2 = await approve_request(client, workspace_id, req["id"])
        assert result2["data"]["status"] == "approved"

    async def test_approve_with_quorum(self, client: AsyncClient, workspace_id: UUID) -> None:
        steps = [{"order": 1, "approver_role": "team", "required_count": 2}]
        rule = await create_rule(client, workspace_id, steps=steps)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="QUORUM-1"
        )

        actor1 = uuid4()
        result1 = await approve_request(client, workspace_id, req["id"], actor_id=actor1)
        assert result1["data"]["status"] == "in_review"
        assert result1["data"]["steps"][0]["current_count"] == 1

        actor2 = uuid4()
        result2 = await approve_request(client, workspace_id, req["id"], actor_id=actor2)
        assert result2["data"]["status"] == "approved"
        assert result2["data"]["steps"][0]["current_count"] == 2


class TestRejectDecision:
    async def test_reject_request(self, client: AsyncClient, workspace_id: UUID) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="REJ-1"
        )

        result = await reject_request(client, workspace_id, req["id"])
        assert result["data"]["status"] == "rejected"
        assert result["data"]["resolved_at"] is not None

    async def test_reject_at_second_step(self, client: AsyncClient, workspace_id: UUID) -> None:
        steps = [
            {"order": 1, "approver_role": "manager", "required_count": 1},
            {"order": 2, "approver_role": "director", "required_count": 1},
        ]
        rule = await create_rule(client, workspace_id, steps=steps)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="REJ-STEP2"
        )

        await approve_request(client, workspace_id, req["id"])
        result = await reject_request(client, workspace_id, req["id"])
        assert result["data"]["status"] == "rejected"

    async def test_decision_on_resolved_request_returns_409(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="TERM-1"
        )
        await approve_request(client, workspace_id, req["id"])

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/decisions",
            json={"actor_id": str(uuid4()), "action": "approve"},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] in ("ALREADY_RESOLVED", "INVALID_STATE_TRANSITION")

    async def test_decision_on_rejected_request_returns_409(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="REJ-TERM"
        )
        await reject_request(client, workspace_id, req["id"])

        resp = await client.post(
            f"/api/v1/requests/{req['id']}/decisions",
            json={"actor_id": str(uuid4()), "action": "approve"},
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] in ("ALREADY_RESOLVED", "INVALID_STATE_TRANSITION")


class TestListDecisions:
    async def test_list_decisions_after_approval(
        self, client: AsyncClient, workspace_id: UUID
    ) -> None:
        rule = await create_rule(client, workspace_id)
        req = await create_approval_request(
            client, workspace_id, rule["id"], external_resource_id="DEC-LIST"
        )
        actor = uuid4()
        await approve_request(client, workspace_id, req["id"], actor_id=actor)

        resp = await client.get(
            f"/api/v1/requests/{req['id']}/decisions",
            headers=_headers(workspace_id),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["actor_id"] == str(actor)
        assert data[0]["action"] == "approve"
