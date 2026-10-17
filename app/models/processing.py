"""Durable AI drafts; remote responses never become notes without adoption."""

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class ProcessingRun(Base):
    __tablename__ = "processing_runs"
    __table_args__ = (CheckConstraint(
        "status IN ('running', 'ready', 'failed', 'interrupted', 'adopted')",
        name="ck_processing_run_status",
    ),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    protocol: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    config_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running", index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    proposal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    adopted_knowledge_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow, onupdate=utcnow)
    started_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_snapshots: Mapped[list | None] = mapped_column(JSON, nullable=True)
    prompt_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generation_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __mapper_args__ = {"version_id_col": version}
