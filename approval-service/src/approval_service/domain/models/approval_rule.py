from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class StepDefinition:
    order: int
    approver_role: str
    required_count: int


@dataclass
class ApprovalRule:
    id: UUID
    workspace_id: UUID
    name: str
    resource_type: str
    conditions: dict[str, Any]
    steps: list[StepDefinition]
    is_active: bool = True
    version: int = 1
    description: str = ""
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.now)

    def matches(self, resource_type: str, payload: dict[str, Any]) -> bool:
        if self.resource_type != resource_type:
            return False
        for key, expected in self.conditions.items():
            actual = payload.get(key)
            if actual is None:
                return False
            if isinstance(expected, dict):
                op = expected.get("op")
                val = expected.get("value")
                if op == "gt" and not (actual > val):
                    return False
                if op == "gte" and not (actual >= val):
                    return False
                if op == "lt" and not (actual < val):
                    return False
                if op == "lte" and not (actual <= val):
                    return False
                if op == "eq" and actual != val:
                    return False
            elif actual != expected:
                return False
        return True
