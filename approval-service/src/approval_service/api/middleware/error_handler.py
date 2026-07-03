from __future__ import annotations

import datetime
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from approval_service.domain.exceptions import (
    AlreadyResolvedError,
    AppError,
    ConcurrentProcessingError,
    ConflictError,
    DomainError,
    DuplicateActiveRequestError,
    DuplicateDecisionError,
    IdempotencyKeyConflictError,
    InsufficientPermissionsError,
    InvalidStateTransitionError,
    NotFoundError,
    OptimisticLockError,
    SelfApprovalError,
    StepNotActiveError,
    ValidationError,
    WorkspaceMismatchError,
)

logger = logging.getLogger(__name__)

ERROR_STATUS_MAP: dict[type[AppError], int] = {
    InvalidStateTransitionError: 409,
    AlreadyResolvedError: 409,
    DuplicateActiveRequestError: 409,
    DuplicateDecisionError: 409,
    SelfApprovalError: 422,
    StepNotActiveError: 422,
    NotFoundError: 404,
    OptimisticLockError: 409,
    IdempotencyKeyConflictError: 422,
    ConcurrentProcessingError: 409,
    WorkspaceMismatchError: 404,
    InsufficientPermissionsError: 403,
    ValidationError: 400,
    ConflictError: 409,
    DomainError: 422,
}


def _get_status_code(exc: AppError) -> int:
    for exc_type in type(exc).__mro__:
        if exc_type in ERROR_STATUS_MAP:
            return ERROR_STATUS_MAP[exc_type]
    return 500


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    status_code = _get_status_code(exc)
    correlation_id = getattr(request.state, "correlation_id", "")

    logger.warning(
        "Application error: %s",
        exc.error_code,
        extra={
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "status_code": status_code,
        },
    )

    headers: dict[str, str] = {}
    if isinstance(exc, ConcurrentProcessingError):
        headers["Retry-After"] = "1"

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.safe_message,
                "details": exc.details,
            },
            "meta": {
                "request_id": correlation_id,
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            },
        },
        headers=headers,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", "")

    logger.exception(
        "Unhandled exception",
        extra={"correlation_id": correlation_id},
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
                "details": {},
            },
            "meta": {
                "request_id": correlation_id,
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            },
        },
    )
