import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from approval_service.infrastructure.database.base import (
    Base,
    MutableTimestampMixin,
    UUIDPrimaryKeyMixin,
)


class ApprovalRequestModel(Base, UUIDPrimaryKeyMixin, MutableTimestampMixin):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','in_review','approved','rejected','cancelled')",
            name="ck_approval_requests_status",
        ),
        Index(
            "ix_approval_requests_workspace_status",
            "workspace_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_approval_requests_unique_active",
            "workspace_id",
            "external_resource_id",
            "resource_type",
            unique=True,
            postgresql_where="status NOT IN ('cancelled')",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("approval_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'pending'")
    requester_id: Mapped[UUID] = mapped_column(nullable=False)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    workspace: Mapped["WorkspaceModel"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="requests",
    )
    rule: Mapped["ApprovalRuleModel"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="requests",
    )
    steps: Mapped[list["ApprovalStepModel"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="request",
        lazy="selectin",
        order_by="ApprovalStepModel.step_order",
    )
