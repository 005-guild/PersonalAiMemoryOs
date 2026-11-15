"""Rebuildable, versioned theme synthesis, separate from user-authored notes."""
from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, new_id, utcnow


class TopicSummary(Base):
    __tablename__ = 'topic_summaries'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    topic: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    members: Mapped[list] = mapped_column(JSON, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON)
    job_id: Mapped[str] = mapped_column(ForeignKey('organization_jobs.id', ondelete='RESTRICT'), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
