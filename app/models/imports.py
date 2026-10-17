"""External content identity, independent of editable Source metadata."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class SourceOrigin(Base):
    __tablename__ = "source_origins"
    __table_args__ = (
        UniqueConstraint("provider", "resource_type", "external_id", name="uq_source_origin_identity"),
    )

    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="RESTRICT"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="zhihu")
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    imported_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
