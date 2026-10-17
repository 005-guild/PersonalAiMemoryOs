"""Shared persistence identity and UTC timestamps."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class VersionedRecord(Base):
    """Changes use SQLAlchemy's revision predicate, including soft deletion."""

    __abstract__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=utcnow)
    updated_at: Mapped[str] = mapped_column(
        String(40), nullable=False, default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return {"version_id_col": cls.version}
