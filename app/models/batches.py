"""Durable user-authorized batches; never automatically resume after restart."""

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class ProcessingBatch(Base):
    __tablename__ = "processing_batches"
    __table_args__ = (CheckConstraint("mode IN ('individual', 'merged')", name="ck_batch_mode"),
        CheckConstraint("status IN ('pending','running','paused','completed','cancelling','cancelled')", name="ck_batch_status"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    client_request_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    profile_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    prompt_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    generation_settings: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_snapshots: Mapped[list] = mapped_column(JSON, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow, onupdate=utcnow)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    __mapper_args__ = {"version_id_col": version}


class ProcessingBatchItem(Base):
    __tablename__ = "processing_batch_items"
    __table_args__ = (UniqueConstraint("batch_id", "position", name="uq_batch_position"),
        CheckConstraint("position >= 0", name="ck_batch_position"),
        CheckConstraint("status IN ('pending','running','ready','failed','interrupted','cancelled')", name="ck_batch_item_status"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey("processing_batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    source_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("processing_runs.id", ondelete="RESTRICT"), nullable=True)
    run_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
