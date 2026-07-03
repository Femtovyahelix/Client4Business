from __future__ import annotations

from uuid import UUID


class AppError(Exception):
    error_code: str = "APP_ERROR"
    safe_message: str = "An application error occurred."

    def __init__(self, *, details: dict[str, object] | None = None) -> None:
        self.details = details or {}
        super().__init__(self.safe_message)


class DomainError(AppError):
    error_code = "DOMAIN_ERROR"


class InvalidStateTransitionError(DomainError):
    error_code = "INVALID_STATE_TRANSITION"

    def __init__(self, *, current: str, target: str) -> None:
        self.safe_message = f"Cannot transition from '{current}' to '{target}'."
        super().__init__(details={"current_status": current, "target_status": target})


class AlreadyResolvedError(DomainError):
    error_code = "ALREADY_RESOLVED"
    safe_message = "This approval request has already been resolved."


class DuplicateActiveRequestError(DomainError):
    error_code = "DUPLICATE_ACTIVE_REQUEST"
    safe_message = "An active approval request already exists for this resource."


class SelfApprovalError(DomainError):
    error_code = "SELF_APPROVAL"
    safe_message = "The requester cannot approve or reject their own request."


class StepNotActiveError(DomainError):
    error_code = "STEP_NOT_ACTIVE"

    def __init__(self, *, step_id: UUID, current_status: str | object) -> None:
        self.safe_message = "The targeted approval step is not currently active."
        status_str = (
            current_status.value if hasattr(current_status, "value") else str(current_status)
        )
        super().__init__(details={"step_id": str(step_id), "current_status": status_str})


class DuplicateDecisionError(DomainError):
    error_code = "DUPLICATE_DECISION"

    def __init__(self, *, step_id: UUID, actor_id: UUID) -> None:
        self.safe_message = "This actor has already made a decision on this step."
        super().__init__(details={"step_id": str(step_id), "actor_id": str(actor_id)})


class NotFoundError(AppError):
    error_code = "NOT_FOUND"
    safe_message = "The requested resource was not found."


class RequestNotFoundError(NotFoundError):
    error_code = "REQUEST_NOT_FOUND"
    safe_message = "Approval request not found."


class RuleNotFoundError(NotFoundError):
    error_code = "RULE_NOT_FOUND"
    safe_message = "Approval rule not found."


class ConflictError(AppError):
    error_code = "CONFLICT"
    safe_message = "A conflict occurred."


class OptimisticLockError(ConflictError):
    error_code = "OPTIMISTIC_LOCK_FAILURE"
    safe_message = "The resource was modified by another request. Retry with the latest version."


class IdempotencyKeyConflictError(AppError):
    error_code = "IDEMPOTENCY_KEY_CONFLICT"
    safe_message = "This idempotency key was already used for a different request."


class ConcurrentProcessingError(ConflictError):
    error_code = "CONCURRENT_PROCESSING"
    safe_message = "This request is currently being processed. Please retry shortly."


class WorkspaceMismatchError(NotFoundError):
    error_code = "NOT_FOUND"
    safe_message = "The requested resource was not found."


class InsufficientPermissionsError(AppError):
    error_code = "INSUFFICIENT_PERMISSIONS"
    safe_message = "You do not have permission to perform this action."


class ValidationError(AppError):
    error_code = "VALIDATION_ERROR"
    safe_message = "Request validation failed."
