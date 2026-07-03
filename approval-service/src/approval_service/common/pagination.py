from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PaginationParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    limit: int = 20
    offset: int = 0


class PaginationMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    limit: int
    offset: int
    has_more: bool
