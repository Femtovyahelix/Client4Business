from __future__ import annotations

import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ResponseMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    timestamp: datetime.datetime


class PaginationInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    limit: int
    offset: int
    has_more: bool


class SingleResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)

    data: T
    meta: ResponseMeta


class ListResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)

    data: list[T]
    meta: ResponseMeta
    pagination: PaginationInfo


class ErrorDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    error: ErrorDetail
    meta: ResponseMeta
