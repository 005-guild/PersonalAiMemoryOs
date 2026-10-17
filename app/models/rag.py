"""Durable vector generations, publication manifests, and embedding intentions."""

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class RagIndexGeneration(Base):
    __tablename__ = "rag_index_generations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_id)
    collection: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)


class RagNoteIndexState(Base):
    __tablename__ = "rag_note_index_states"

    generation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rag_index_generations.id", ondelete="RESTRICT"), primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge.id", ondelete="RESTRICT"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    published_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    pending_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)


class RagIndexJob(Base):
    __tablename__ = "rag_index_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    generation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rag_index_generations.id", ondelete="RESTRICT"), nullable=False, index=True)
    knowledge_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    chunks: Mapped[list] = mapped_column(JSON, nullable=False)
    vectors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    intents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cleanup_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
