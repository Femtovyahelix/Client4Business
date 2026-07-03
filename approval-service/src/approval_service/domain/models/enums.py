from enum import StrEnum


class RequestStatus(StrEnum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class EntityType(StrEnum):
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RULE = "approval_rule"
    APPROVAL_STEP = "approval_step"
    APPROVAL_DECISION = "approval_decision"


class AuditAction(StrEnum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    DECISION_MADE = "decision_made"
    STEP_COMPLETED = "step_completed"
    STEP_ACTIVATED = "step_activated"
    UPDATED = "updated"
    DEACTIVATED = "deactivated"
    CANCELLED = "cancelled"
