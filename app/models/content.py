"""Original sources and separately editable knowledge notes."""

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, VersionedRecord


class Source(VersionedRecord):
    __tablename__ = "sources"

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")


class Knowledge(VersionedRecord):
    __tablename__ = "knowledge"

    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    concepts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_links: Mapped[list["KnowledgeSource"]] = relationship(
        back_populates="knowledge", cascade="all, delete-orphan", lazy="selectin",
        order_by="KnowledgeSource.position",
    )

    @property
    def source_ids(self) -> list[str]:
        return [link.source_id for link in self.source_links] or ([self.source_id] if self.source_id else [])


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        UniqueConstraint("knowledge_id", "position", name="uq_knowledge_source_position"),
        CheckConstraint("position >= 0 AND position < 20", name="ck_knowledge_source_position"),
    )

    knowledge_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge.id", ondelete="RESTRICT"), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="RESTRICT"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge: Mapped[Knowledge] = relationship(back_populates="source_links")
