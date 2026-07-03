from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from approval_service.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class ApprovalDecisionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        UniqueConstraint("step_id", "actor_id", name="uq_approval_decisions_step_actor"),
    )

    step_id: Mapped[UUID] = mapped_column(
        ForeignKey("approval_steps.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    actor_id: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    step: Mapped["ApprovalStepModel"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="decisions",
    )
