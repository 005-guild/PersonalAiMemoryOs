"""Durable synchronization baselines, conflicts and filesystem intentions."""

from sqlalchemy import JSON, Boolean, CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class SyncVault(Base):
    __tablename__ = "sync_vault"
    __table_args__ = (CheckConstraint("id = 1", name="ck_sync_vault_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    token: Mapped[str] = mapped_column(String(36), nullable=False, default=new_id)
    initialized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SyncState(Base):
    __tablename__ = "sync_states"

    knowledge_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge.id", ondelete="RESTRICT"), primary_key=True
    )
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    base: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    base_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    missing_since: Mapped[float | None] = mapped_column(Float, nullable=True)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SyncConflict(Base):
    __tablename__ = "sync_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    base: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    db_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    file_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    file_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    db_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SyncOperation(Base):
    __tablename__ = "sync_operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    expected_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
