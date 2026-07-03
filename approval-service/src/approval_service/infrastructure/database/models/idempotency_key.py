import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from approval_service.infrastructure.database.base import Base


class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (Index("ix_idempotency_keys_expires", "expires_at"),)

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_processing: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
