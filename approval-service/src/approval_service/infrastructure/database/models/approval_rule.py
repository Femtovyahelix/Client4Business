from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from approval_service.infrastructure.database.base import (
    Base,
    MutableTimestampMixin,
    UUIDPrimaryKeyMixin,
)


class ApprovalRuleModel(Base, UUIDPrimaryKeyMixin, MutableTimestampMixin):
    __tablename__ = "approval_rules"
    __table_args__ = (
        Index("ix_approval_rules_workspace_resource", "workspace_id", "resource_type", "is_active"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    workspace: Mapped["WorkspaceModel"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="rules",
    )
    requests: Mapped[list["ApprovalRequestModel"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="rule",
        lazy="selectin",
    )
