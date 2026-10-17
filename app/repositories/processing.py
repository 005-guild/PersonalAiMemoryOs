"""Session-bound lookups for generation records; no remote calls or commits."""

import json

from sqlalchemy import case, func, or_, select
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
        if source_id is not None:
            snapshots = func.json_each(ProcessingRun.source_snapshots).table_valued("value").alias("source_snapshots")
            linked = select(1).select_from(snapshots).where(func.json_extract(snapshots.c.value, "$.id") == source_id).exists()
            filters.append(or_(ProcessingRun.source_id == source_id, linked))
        for field, value in (("status", status), ("profile_id", profile_id)):
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

    def summary_page(self, *, source_id=None, status=None, profile_id=None, offset=0, limit=20):
        run = ProcessingRun
        snapshots = func.json_each(run.source_snapshots).table_valued("value").alias("run_sources")
        snapshot_id = func.json_extract(snapshots.c.value, "$.id")
        snapshot_version = func.json_extract(snapshots.c.value, "$.version")
        source_ids = select(func.json_group_array(snapshot_id)).select_from(snapshots).correlate(run).scalar_subquery()
        stale_sources = select(1).select_from(snapshots).outerjoin(Source, Source.id == snapshot_id).where(
            or_(Source.id.is_(None), Source.deleted_at.is_not(None), Source.version != snapshot_version)).correlate(run).exists()
        first_stale = select(1).where(Source.id == run.source_id, Source.deleted_at.is_(None),
                                      Source.version == run.source_version).correlate(run).exists()
        has_sources = func.json_array_length(run.source_snapshots) > 0
        where = []
        if source_id is not None:
            linked = select(1).select_from(snapshots).where(snapshot_id == source_id).correlate(run).exists()
            where.append(or_(run.source_id == source_id, linked))
        if status is not None:
            where.append(run.status == status)
        if profile_id is not None:
            where.append(run.profile_id == profile_id)
        from app.services.processing_records import SUMMARY_FIELDS
        columns = [getattr(run, key) for key in SUMMARY_FIELDS]
        columns += [case((has_sources, func.json_array_length(run.source_snapshots)), else_=1).label("source_count"),
                    case((has_sources, source_ids), else_=func.json_array(run.source_id)).label("source_ids"),
                    case((has_sources, stale_sources), else_=~first_stale).label("source_stale")]
        total = self.session.scalar(select(func.count()).select_from(run).where(*where)) or 0
        rows = self.session.execute(select(*columns).where(*where).order_by(
            run.created_at.desc(), run.id.desc()).offset(offset).limit(limit)).mappings()
        items = [dict(row) for row in rows]
        for item in items:
            item["source_ids"] = json.loads(item["source_ids"])
            item["source_stale"] = bool(item["source_stale"])
        return items, int(total)
