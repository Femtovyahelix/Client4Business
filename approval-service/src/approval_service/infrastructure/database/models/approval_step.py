import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from approval_service.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class ApprovalStepModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "approval_steps"
    __table_args__ = (
        UniqueConstraint("request_id", "step_order", name="uq_approval_steps_request_order"),
        Index("ix_approval_steps_request", "request_id", "step_order"),
    )

    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    step_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    approver_role: Mapped[str] = mapped_column(String(100), nullable=False)
    required_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    current_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'pending'")
    activated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    request: Mapped["ApprovalRequestModel"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="steps",
    )
    decisions: Mapped[list["ApprovalDecisionModel"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="step",
        lazy="selectin",
    )
