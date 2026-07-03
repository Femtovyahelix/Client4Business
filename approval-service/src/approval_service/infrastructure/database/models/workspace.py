from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from approval_service.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class WorkspaceModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    rules: Mapped[list["ApprovalRuleModel"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="workspace",
        lazy="selectin",
    )
    requests: Mapped[list["ApprovalRequestModel"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="workspace",
        lazy="selectin",
    )
