"""Versioned prompt resources; every published revision remains immutable."""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (CheckConstraint("output_schema_version IN (1, 2)", name="ck_prompt_schema"),
        CheckConstraint("purpose IN ('knowledge', 'rag_qa')", name="ck_prompt_purpose"),
        Index("uq_prompt_default", "purpose", unique=True, sqlite_where=text("is_default = 1")))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, default="knowledge", server_default="knowledge")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow, onupdate=utcnow)
    __mapper_args__ = {"version_id_col": version}


class PromptRevision(Base):
    __tablename__ = "prompt_revisions"
    __table_args__ = (CheckConstraint("purpose IN ('knowledge', 'rag_qa')", name="ck_prompt_revision_purpose"),)
    template_id: Mapped[str] = mapped_column(String(36), ForeignKey("prompt_templates.id", ondelete="RESTRICT"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, default="knowledge", server_default="knowledge")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
