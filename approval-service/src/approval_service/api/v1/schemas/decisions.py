from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateDecisionBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    actor_id: UUID
    action: str = Field(..., pattern=r"^(approve|reject)$")
    comment: str = ""
