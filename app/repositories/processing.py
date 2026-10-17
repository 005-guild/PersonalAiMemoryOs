"""Session-bound lookups for generation records; no remote calls or commits."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ProcessingRun, Source


class ProcessingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run(self, run_id: str) -> ProcessingRun | None:
        return self.session.get(ProcessingRun, run_id)

    def source(self, source_id: str) -> Source | None:
        return self.session.get(Source, source_id)

    def page(self, *, source_id: str | None, status: str | None,
             profile_id: str | None, offset: int, limit: int) -> tuple[list[ProcessingRun], int]:
        filters = []
        for field, value in (("source_id", source_id), ("status", status), ("profile_id", profile_id)):
            if value is not None:
                filters.append(getattr(ProcessingRun, field) == value)
        total = self.session.scalar(select(func.count()).select_from(ProcessingRun).where(*filters))
        records = self.session.scalars(
            select(ProcessingRun).where(*filters)
            .order_by(ProcessingRun.created_at.desc(), ProcessingRun.id.desc())
            .offset(offset).limit(limit)
        ).all()
        return list(records), total or 0

    def running(self) -> list[ProcessingRun]:
        return list(self.session.scalars(select(ProcessingRun).where(ProcessingRun.status == "running")))
