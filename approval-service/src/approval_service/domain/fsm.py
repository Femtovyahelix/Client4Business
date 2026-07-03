from approval_service.domain.models.enums import RequestStatus

ALLOWED_TRANSITIONS: dict[RequestStatus, frozenset[RequestStatus]] = {
    RequestStatus.PENDING: frozenset(
        {
            RequestStatus.IN_REVIEW,
            RequestStatus.CANCELLED,
        }
    ),
    RequestStatus.IN_REVIEW: frozenset(
        {
            RequestStatus.APPROVED,
            RequestStatus.REJECTED,
            RequestStatus.CANCELLED,
        }
    ),
    RequestStatus.APPROVED: frozenset(),
    RequestStatus.REJECTED: frozenset(),
    RequestStatus.CANCELLED: frozenset(),
}
