from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from dharmiq.db.base import Base


class StatuteRelationship(Base):
    __tablename__ = "statute_relationships"
    __table_args__ = (
        UniqueConstraint(
            "from_source_id",
            "to_source_id",
            "relationship",
            name="uq_statute_relationships_from_to_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    to_source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
