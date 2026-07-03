"""Shared helpers for building API response envelopes."""

from __future__ import annotations

import datetime

from fastapi import Request

from approval_service.api.v1.schemas.common import ResponseMeta


def build_response_meta(request: Request) -> ResponseMeta:
    """Build a ResponseMeta populated with the correlation ID from middleware."""
    correlation_id: str = getattr(request.state, "correlation_id", "")
    return ResponseMeta(
        request_id=correlation_id,
        timestamp=datetime.datetime.now(datetime.UTC),
    )
