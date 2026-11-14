"""Durable collection organization, explicit approval, and paid-call accounting."""

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, new_id, utcnow


class OrganizationControl(Base):
    __tablename__ = 'organization_control'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)


class OrganizationItem(Base):
    __tablename__ = 'organization_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    identity: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey('sources.id', ondelete='RESTRICT'))
    knowledge_id: Mapped[str | None] = mapped_column(ForeignKey('knowledge.id', ondelete='RESTRICT'), unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='discovered', index=True)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(100))
    export_path: Mapped[str | None] = mapped_column(Text)
    export_hash: Mapped[str | None] = mapped_column(String(64))
    exported_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)


class OrganizationJob(Base):
    __tablename__ = 'organization_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='pending', index=True)
    selection: Mapped[list] = mapped_column(JSON, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False)
    error: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
    finished_at: Mapped[str | None] = mapped_column(String(40))


class OrganizationCall(Base):
    __tablename__ = 'organization_calls'
    __table_args__ = (UniqueConstraint('fingerprint', 'attempt', name='uq_organization_call_attempt'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey('organization_jobs.id', ondelete='RESTRICT'))
    item_id: Mapped[str | None] = mapped_column(ForeignKey('organization_items.id', ondelete='RESTRICT'))
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='reserved')
    reserved_micros: Mapped[int] = mapped_column(Integer, nullable=False)
    accounted_micros: Mapped[int] = mapped_column(Integer, nullable=False)
    response: Mapped[str | None] = mapped_column(Text)
    usage: Mapped[dict | None] = mapped_column(JSON)
    price_snapshot: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
